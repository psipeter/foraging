using System;
using System.Collections.Generic;
using UnityEngine;

/*
Tree Prefab Setup (local space under this `Tree` object):

Canopy:
  - Sphere GameObject (mesh replaced at runtime with Unity default sphere)
  - Code sets: position (0, 0, 0), local rotation identity
  - No colliders on prefab children; Tree adds a canopy trigger collider via code
  - MeshRenderer material instance; the highlight (set each frame by HarvestManager) is canopy emission:
    graded while approaching and distinct when selected; look depends on SessionConfig.highlightStyle

Fruits:
  - Fruits are fully runtime-generated in `ApplyAttributes()` (no fruit children required in the prefab).
  - No colliders on fruits; Tree removes the default primitive collider as part of generation.
*/
public class Tree : MonoBehaviour
{
    public TreeAttributes attributes;
    public int treeId;
    public SessionConfig sessionConfig;
    public Material rimMaterial;
    public Material ringMaterial;

    [SerializeField] private TerrainManager terrainManager;

    [SerializeField] private GameObject canopy;

    [SerializeField] public int fruitCount = 10;
    [SerializeField] public float fruitRadius = 0.15f;
    [SerializeField] public int fruitSeed;
    // Reward of the k-th fruit taken from this bush (from the world file); null falls back to a fresh draw.
    public int[] fruitRewards;

    private MeshRenderer _canopyRenderer;
    private Material _canopyMaterial;
    [SerializeField] private Color highlightEmissionColor = new Color(1f, 0.95f, 0.7f);
    [SerializeField] private float highlightPulseSpeed = 1.5f;
    [Tooltip("Emission at glow level 1 while the bush is not yet harvestable (steady, no pulse).")]
    [SerializeField] private float highlightSteadyMaxIntensity = 0.45f;
    [Tooltip("Peak emission of the harvestable pulse. The pulse never drops below 1.25x the steady maximum, so it is always brighter than any approach glow.")]
    [SerializeField] private float highlightMaxIntensity = 1.3f;

    private float _highlightLevel;
    private bool _highlightSelected;
    private GameObject _rimObject;
    private Material _rimInstance;
    private float _softCurrent;
    private float _crispCurrent;
    private bool _rimActive;
    private bool _emissionCleared = true;
    private float _selectedBlend;
    private bool _vanishing;
    private GameObject _ringObject;
    private Material _ringInstance;
    private static Mesh _quadMesh;
    private bool[] _collected;

    private List<GameObject> _fruits = new List<GameObject>();

    private static readonly Color ColorLow = new Color(0.2f, 0.4f, 1.0f);
    private static readonly Color ColorHigh = new Color(1.0f, 0.5f, 0.1f);

    private static Mesh _sphereMesh;

    public bool isHarvested = false;

    private Vector3 _terrainNormal = Vector3.up;

    public int FruitCount => _fruits.Count;
    public float CanopyRadius { get; private set; }

    // Seconds already spent on the fruit currently being picked; kept here so a bush left mid-fruit resumes
    // where it was (and the progress ring does not jump back up).
    public float PartialProgress { get; set; }

    public int FruitsRemaining
    {
        get
        {
            int remaining = 0;
            for (int i = 0; i < _fruits.Count; i++)
            {
                if (_collected == null || !_collected[i])
                {
                    remaining++;
                }
            }

            return remaining;
        }
    }

    public TerrainManager TerrainManager
    {
        get => terrainManager;
        set => terrainManager = value;
    }

    private void Awake()
    {
        gameObject.tag = "Interactable";

        if (canopy != null)
        {
            _canopyRenderer = canopy.GetComponent<MeshRenderer>();
            if (_canopyRenderer != null)
            {
                _canopyMaterial = new Material(_canopyRenderer.sharedMaterial);
                _canopyRenderer.material = _canopyMaterial;
                _canopyMaterial.EnableKeyword("_EMISSION");
                _canopyMaterial.SetColor("_EmissionColor", Color.black);
            }
        }
    }

    private void Update()
    {
        if (_vanishing)
        {
            return;
        }

        if (_rimInstance != null && sessionConfig != null && sessionConfig.HighlightStyle == HighlightStyle.RimLight)
        {
            UpdateRim();
        }
        else
        {
            UpdateEmissionWash();
        }
    }

    // RimLight style: soft edge glow scaled by the glow level; a thin crisp edge line only on the selected bush.
    // Both ease toward their targets so the cues fade in and out instead of popping.
    private void UpdateRim()
    {
        if (_canopyMaterial != null && !_emissionCleared)
        {
            _canopyMaterial.SetColor("_EmissionColor", Color.black);
            _emissionCleared = true;
        }

        float softTarget = _highlightLevel * sessionConfig.RimApproachIntensity;
        float crispTarget = _highlightSelected ? sessionConfig.RimSelectedIntensity : 0f;
        float ease = 1f - Mathf.Exp(-12f * Time.deltaTime);
        _softCurrent = Mathf.Lerp(_softCurrent, softTarget, ease);
        _crispCurrent = Mathf.Lerp(_crispCurrent, crispTarget, ease);

        bool visible = _softCurrent > 0.002f || _crispCurrent > 0.002f;
        if (visible != _rimActive)
        {
            _rimActive = visible;
            _rimObject.SetActive(visible);
        }

        if (!visible)
        {
            return;
        }

        // Slightly different rim color once the bush is selected (harvestable).
        _selectedBlend = Mathf.Lerp(_selectedBlend, _highlightSelected ? 1f : 0f, ease);
        _rimInstance.SetColor("_RimColor", Color.Lerp(sessionConfig.RimColor, sessionConfig.RimSelectedColor, _selectedBlend));
        _rimInstance.SetFloat("_SoftIntensity", _softCurrent);
        _rimInstance.SetFloat("_SoftPower", sessionConfig.RimApproachPower);
        _rimInstance.SetFloat("_CrispIntensity", _crispCurrent);
        _rimInstance.SetFloat("_CrispPower", sessionConfig.RimSelectedPower);
    }

    // EmissionWash style: whole-canopy emission, steady and graded while approaching, pulsing when selected.
    private void UpdateEmissionWash()
    {
        if (_rimActive && _rimObject != null)
        {
            _rimActive = false;
            _rimObject.SetActive(false);
        }

        if (_canopyMaterial == null || (_highlightLevel <= 0f && !_highlightSelected))
        {
            if (_canopyMaterial != null && _emissionCleared == false)
            {
                _canopyMaterial.SetColor("_EmissionColor", Color.black);
                _emissionCleared = true;
            }

            return;
        }

        _emissionCleared = false;
        float intensity;
        if (_highlightSelected)
        {
            float t = (Mathf.Sin(Time.time * highlightPulseSpeed * Mathf.PI * 2f) + 1f) * 0.5f;
            intensity = Mathf.Lerp(highlightSteadyMaxIntensity * 1.25f, highlightMaxIntensity, t);
        }
        else
        {
            intensity = _highlightLevel * highlightSteadyMaxIntensity;
        }

        _canopyMaterial.SetColor("_EmissionColor", highlightEmissionColor * intensity);
    }

    public void SetTerrainNormal(Vector3 normal)
    {
        _terrainNormal = normal.sqrMagnitude > 1e-8f ? normal.normalized : Vector3.up;
    }

    public void ApplyAttributes()
    {
        if (canopy == null)
        {
            return;
        }

        Vector2 shapeRange = sessionConfig != null ? sessionConfig.ShapeRange : new Vector2(0f, 1f);
        float shapeT = Mathf.InverseLerp(shapeRange.x, shapeRange.y, attributes.shape);

        Vector2 widthRange = sessionConfig != null ? sessionConfig.CanopyWidthRange : new Vector2(1.0f, 2.5f);
        Vector2 heightRange = sessionConfig != null ? sessionConfig.CanopyHeightRange : new Vector2(0.6f, 1.4f);

        // Bush silhouette: squat/wide (shape=0) to tall/narrow (shape=1).
        float sx = Mathf.Lerp(widthRange.y, widthRange.x, shapeT);
        float sy = Mathf.Lerp(heightRange.x, heightRange.y, shapeT);
        float sz = Mathf.Lerp(widthRange.y, widthRange.x, shapeT);

        canopy.transform.localScale = new Vector3(sx, sy, sz);
        canopy.transform.localPosition = new Vector3(0f, 0f, 0f);

        Vector3 canopyScale = canopy.transform.localScale;

        canopy.transform.localRotation = Quaternion.identity;

        MeshFilter meshFilter = canopy.GetComponent<MeshFilter>();
        if (meshFilter == null)
        {
            meshFilter = canopy.AddComponent<MeshFilter>();
        }

        if (_sphereMesh == null)
        {
            GameObject primitive = GameObject.CreatePrimitive(PrimitiveType.Sphere);
            _sphereMesh = primitive.GetComponent<MeshFilter>().sharedMesh;
            Destroy(primitive);
        }

        meshFilter.sharedMesh = _sphereMesh;
        BuildRimOverlay();

        float maxScaleXZ = Mathf.Max(canopyScale.x, canopyScale.z);
        CanopyRadius = maxScaleXZ * 0.5f;

        // Ensure no collider remains on the canopy child, and no proximity trigger on the root
        // (harvest availability comes from HarvestManager's distance + bearing test).
        SphereCollider canopyCollider = canopy.GetComponent<SphereCollider>();
        if (canopyCollider != null)
        {
            Destroy(canopyCollider);
        }

        SphereCollider rootCollider = GetComponent<SphereCollider>();
        if (rootCollider != null)
        {
            Destroy(rootCollider);
        }

        // Add a capsule collider for physical blocking.
        CapsuleCollider cap = GetComponent<CapsuleCollider>();
        if (cap == null)
        {
            cap = gameObject.AddComponent<CapsuleCollider>();
        }
        cap.isTrigger = false;
        cap.direction = 1; // Y axis
        cap.center = new Vector3(0f, 0f, 0f);
        cap.radius = maxScaleXZ * 0.5f;
        cap.height = canopyScale.y;

        // Rebuild fruits procedurally.
        // Destroy existing runtime fruits first.
        for (int i = 0; i < _fruits.Count; i++)
        {
            if (_fruits[i] != null)
            {
                Destroy(_fruits[i]);
            }
        }
        _fruits.Clear();

        int count = Mathf.Max(0, fruitCount);
        _collected = new bool[count];
        if (count == 0)
        {
            return;
        }

        // Fruit scale compensation: keep fruits as configurable world-space spheres.
        Vector3 compensatedScale = new Vector3(
            fruitRadius / Mathf.Max(canopyScale.x, 0.0001f),
            fruitRadius / Mathf.Max(canopyScale.y, 0.0001f),
            fruitRadius / Mathf.Max(canopyScale.z, 0.0001f));

        // Deterministic distribution per tree.
        Color lowColor = sessionConfig != null ? sessionConfig.FruitColorLow : ColorLow;
        Color highColor = sessionConfig != null ? sessionConfig.FruitColorHigh : ColorHigh;
        Color fruitColor = Color.Lerp(lowColor, highColor, attributes.color);
        System.Random rng = new System.Random(fruitSeed);
        float goldenAngle = Mathf.PI * (3f - Mathf.Sqrt(5f));

        const int maxFibonacciAttempts = 5000;
        int placed = 0;
        int attempt = 0;
        while (placed < count && attempt < maxFibonacciAttempts)
        {
            float t = (attempt + 0.5f) / Mathf.Max(count, attempt + 1);
            t = Mathf.Clamp01(t);
            float theta = Mathf.Acos(1f - t);
            theta = Mathf.Min(theta, Mathf.PI * 0.5f);

            float phi = goldenAngle * attempt;
            phi += (float)(rng.NextDouble() * 0.3f);

            float x = Mathf.Sin(theta) * Mathf.Cos(phi) * 0.5f;
            float y = Mathf.Cos(theta) * 0.5f;
            float z = Mathf.Sin(theta) * Mathf.Sin(phi) * 0.5f;

            Vector3 worldFruitPos = canopy.transform.TransformPoint(new Vector3(x, y, z));
            float terrainY = terrainManager != null
                ? terrainManager.SampleElevation(worldFruitPos.x, worldFruitPos.z)
                : 0f;

            if (worldFruitPos.y <= terrainY)
            {
                attempt++;
                continue;
            }

            GameObject fruit = new GameObject();
            MeshFilter mf = fruit.AddComponent<MeshFilter>();
            mf.sharedMesh = _sphereMesh;
            fruit.AddComponent<MeshRenderer>();
            fruit.name = $"Fruit_{placed}";
            fruit.transform.SetParent(canopy.transform, false);
            fruit.transform.localScale = compensatedScale;
            fruit.transform.localPosition = new Vector3(x, y, z);

            MeshRenderer renderer = fruit.GetComponent<MeshRenderer>();
            if (renderer != null)
            {
                renderer.sharedMaterial = FruitMaterialManager.GetMaterial(fruitColor);
            }

            _fruits.Add(fruit);
            placed++;
            attempt++;
        }

        while (placed < count)
        {
            Vector3 apexLocal = new Vector3(0f, 0.5f, 0f);

            GameObject fruit = new GameObject();
            MeshFilter mf = fruit.AddComponent<MeshFilter>();
            mf.sharedMesh = _sphereMesh;
            fruit.AddComponent<MeshRenderer>();
            fruit.name = $"Fruit_{placed}";
            fruit.transform.SetParent(canopy.transform, false);
            fruit.transform.localScale = compensatedScale;
            fruit.transform.localPosition = apexLocal;

            MeshRenderer renderer = fruit.GetComponent<MeshRenderer>();
            if (renderer != null)
            {
                renderer.sharedMaterial = FruitMaterialManager.GetMaterial(fruitColor);
            }

            _fruits.Add(fruit);
            placed++;
        }
    }

    // A slightly enlarged copy of the canopy sphere with the additive fresnel rim material. Built once; the
    // canopy's own material is left alone. Inactive unless the rim is visible.
    private void BuildRimOverlay()
    {
        if (_rimObject != null || rimMaterial == null || canopy == null)
        {
            return;
        }

        _rimObject = new GameObject("Rim");
        _rimObject.transform.SetParent(canopy.transform, false);
        _rimObject.transform.localScale = Vector3.one * 1.03f;
        _rimObject.AddComponent<MeshFilter>().sharedMesh = _sphereMesh;

        MeshRenderer rimRenderer = _rimObject.AddComponent<MeshRenderer>();
        _rimInstance = new Material(rimMaterial);
        rimRenderer.sharedMaterial = _rimInstance;
        rimRenderer.shadowCastingMode = UnityEngine.Rendering.ShadowCastingMode.Off;
        rimRenderer.receiveShadows = false;
        _rimObject.SetActive(false);
    }

    // Clock-style harvest progress ring above the crown, facing the camera at a constant apparent size.
    // fill = remaining fraction of the bush (1 untouched, 0 empty).
    public void SetRing(bool visible, float fill, Transform cameraTransform)
    {
        if (!visible || _vanishing || ringMaterial == null || canopy == null || cameraTransform == null || sessionConfig == null)
        {
            if (_ringObject != null && _ringObject.activeSelf)
            {
                _ringObject.SetActive(false);
            }

            return;
        }

        if (_ringObject == null)
        {
            BuildRing();
        }

        if (!_ringObject.activeSelf)
        {
            _ringObject.SetActive(true);
        }

        Vector3 crown = GetWorldCenter() + Vector3.up * (canopy.transform.lossyScale.y * 0.5f);
        float dist = Vector3.Distance(cameraTransform.position, crown);
        float size = 2f * dist * Mathf.Tan(sessionConfig.HarvestRingSizeDeg * 0.5f * Mathf.Deg2Rad);

        Transform ring = _ringObject.transform;
        ring.position = crown + Vector3.up * (0.4f + size * 0.5f);
        ring.rotation = cameraTransform.rotation;
        ring.localScale = Vector3.one * (size / Mathf.Max(transform.lossyScale.x, 0.0001f));

        _ringInstance.SetFloat("_Fill", Mathf.Clamp01(fill));
        _ringInstance.SetColor("_Color", sessionConfig.RimSelectedColor);
    }

    private void BuildRing()
    {
        if (_quadMesh == null)
        {
            GameObject primitive = GameObject.CreatePrimitive(PrimitiveType.Quad);
            _quadMesh = primitive.GetComponent<MeshFilter>().sharedMesh;
            Destroy(primitive);
        }

        _ringObject = new GameObject("HarvestRing");
        _ringObject.transform.SetParent(transform, false);
        _ringObject.AddComponent<MeshFilter>().sharedMesh = _quadMesh;

        MeshRenderer ringRenderer = _ringObject.AddComponent<MeshRenderer>();
        _ringInstance = new Material(ringMaterial);
        ringRenderer.sharedMaterial = _ringInstance;
        ringRenderer.shadowCastingMode = UnityEngine.Rendering.ShadowCastingMode.Off;
        ringRenderer.receiveShadows = false;
        _ringObject.SetActive(false);
    }

    // Exhausted bush: shrinks to nothing (same linear shrink as a collected fruit), then disappears and stops
    // blocking the player.
    public void Vanish(float duration)
    {
        if (_vanishing)
        {
            return;
        }

        _vanishing = true;
        isHarvested = true;
        SetRing(false, 0f, null);
        if (_rimObject != null)
        {
            _rimObject.SetActive(false);
        }

        CapsuleCollider blocker = GetComponent<CapsuleCollider>();
        if (blocker != null)
        {
            blocker.enabled = false;
        }

        StartCoroutine(ShrinkAndHide(duration));
    }

    private System.Collections.IEnumerator ShrinkAndHide(float duration)
    {
        Transform canopyTransform = canopy.transform;
        Vector3 startScale = canopyTransform.localScale;
        float elapsed = 0f;
        while (elapsed < duration)
        {
            elapsed += Time.deltaTime;
            canopyTransform.localScale = startScale * (1f - Mathf.Clamp01(elapsed / Mathf.Max(duration, 0.0001f)));
            yield return null;
        }

        canopy.SetActive(false);
    }

    // Pre-drawn reward for the next fruit to be taken, or -1 when none is stored for it.
    public int NextFruitReward()
    {
        int taken = FruitCount - FruitsRemaining;
        return fruitRewards != null && taken >= 0 && taken < fruitRewards.Length ? fruitRewards[taken] : -1;
    }

    public float Evaluate(RewardFunction rf)
    {
        return rf.Evaluate(attributes);
    }

    public void SetHarvested(bool harvested)
    {
        if (_collected != null)
        {
            for (int i = 0; i < _collected.Length; i++)
            {
                _collected[i] = harvested;
            }
        }

        foreach (GameObject fruit in _fruits)
        {
            if (fruit != null)
            {
                fruit.SetActive(!harvested);
            }
        }
    }

    // Marks the fruit collected and plays a short shrink-out before hiding it.
    public void CollectFruit(int index, float popDuration)
    {
        if (index < 0 || index >= _fruits.Count || _collected[index])
        {
            return;
        }

        _collected[index] = true;
        GameObject fruit = _fruits[index];
        if (fruit != null)
        {
            StartCoroutine(PopFruit(fruit, popDuration));
        }
    }

    // Index of the uncollected fruit nearest to the given world point (the camera), or -1 if none remain.
    public int NextFruitIndexTowards(Vector3 worldPoint)
    {
        int best = -1;
        float bestDist = float.MaxValue;
        for (int i = 0; i < _fruits.Count; i++)
        {
            if (_collected[i] || _fruits[i] == null)
            {
                continue;
            }

            float d = (_fruits[i].transform.position - worldPoint).sqrMagnitude;
            if (d < bestDist)
            {
                bestDist = d;
                best = i;
            }
        }

        return best;
    }

    private System.Collections.IEnumerator PopFruit(GameObject fruit, float duration)
    {
        Vector3 startScale = fruit.transform.localScale;
        float elapsed = 0f;
        while (elapsed < duration && fruit != null)
        {
            elapsed += Time.deltaTime;
            fruit.transform.localScale = startScale * (1f - Mathf.Clamp01(elapsed / Mathf.Max(duration, 0.0001f)));
            yield return null;
        }

        if (fruit != null)
        {
            fruit.SetActive(false);
        }
    }

    public Vector3 GetWorldCenter()
    {
        return canopy != null ? canopy.transform.position : transform.position;
    }

    public Vector3 GetFruitWorldPosition(int index)
    {
        if (index < 0 || index >= _fruits.Count || _fruits[index] == null)
        {
            return GetWorldCenter();
        }

        return _fruits[index].transform.position;
    }

    public void SetTerrainManager(TerrainManager tm)
    {
        terrainManager = tm;
    }

    // level: 0-1 graded cue while approaching; selected: this is the bush Space would harvest (or is harvesting).
    public void SetHighlight(float level, bool selected)
    {
        _highlightLevel = Mathf.Clamp01(level);
        _highlightSelected = selected;
    }
}
