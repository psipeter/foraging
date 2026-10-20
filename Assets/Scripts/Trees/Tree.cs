using System;
using System.Collections.Generic;
using UnityEngine;

/*
Tree Prefab Setup (local space under this `Tree` object):

Canopy:
  - Sphere GameObject (mesh replaced at runtime with Unity default sphere)
  - Code sets: position (0, 0, 0), local rotation identity
  - No colliders on prefab children; harvest availability comes from HarvestManager (distance + bearing)
  - MeshRenderer material instance; the highlight is a fresnel rim overlay (CanopyRim shader) set each frame by
    HarvestManager: soft glow while approaching, plus a crisp edge line on the selected bush

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

    private float _highlightLevel;
    private bool _highlightSelected;
    private GameObject _rimObject;
    private Material _rimInstance;
    private float _softCurrent;
    private float _crispCurrent;
    private bool _rimActive;
    private float _selectedBlend;
    private bool _spent;
    private Color _canopyBaseColor = Color.white;
    private GameObject _ringObject;
    private Material _ringInstance;
    private static Mesh _quadMesh;
    private bool[] _collected;

    private List<GameObject> _fruits = new List<GameObject>();

    private static readonly Color ColorLow = new Color(0.2f, 0.4f, 1.0f);
    private static readonly Color ColorHigh = new Color(1.0f, 0.5f, 0.1f);

    private static Mesh _sphereMesh;

    public bool isHarvested = false;

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
                if (_canopyMaterial.HasProperty("_BaseColor"))
                {
                    _canopyBaseColor = _canopyMaterial.GetColor("_BaseColor");
                }
            }
        }
    }

    private void Update()
    {
        if (_rimInstance != null && sessionConfig != null)
        {
            UpdateRim();
        }
    }

    // Soft edge glow scaled by the glow level; a thin crisp edge line only on the selected bush.
    // Both ease toward their targets so the cues fade in and out instead of popping.
    private void UpdateRim()
    {
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
        if (!visible || ringMaterial == null || canopy == null || cameraTransform == null || sessionConfig == null)
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

    // Exhausted bush: stays as a landmark and obstacle, easing into a spent look (uniformly shrunk, drab tint).
    // The blocking collider is resized to match the smaller canopy.
    public void MarkSpent()
    {
        if (_spent)
        {
            return;
        }

        _spent = true;
        isHarvested = true;
        SetRing(false, 0f, null);
        StartCoroutine(EaseToSpent());
    }

    private System.Collections.IEnumerator EaseToSpent()
    {
        Transform canopyTransform = canopy.transform;
        Vector3 startScale = canopyTransform.localScale;
        Vector3 endScale = startScale * sessionConfig.SpentScale;
        Color endColor = _canopyBaseColor * sessionConfig.SpentTint;
        float duration = Mathf.Max(sessionConfig.SpentTransitionDuration, 0.0001f);

        CapsuleCollider blocker = GetComponent<CapsuleCollider>();
        float startRadius = blocker != null ? blocker.radius : 0f;
        float startHeight = blocker != null ? blocker.height : 0f;

        float elapsed = 0f;
        while (elapsed < duration)
        {
            elapsed += Time.deltaTime;
            float t = Mathf.SmoothStep(0f, 1f, Mathf.Clamp01(elapsed / duration));
            canopyTransform.localScale = Vector3.Lerp(startScale, endScale, t);
            if (_canopyMaterial != null)
            {
                _canopyMaterial.SetColor("_BaseColor", Color.Lerp(_canopyBaseColor, endColor, t));
            }

            if (blocker != null)
            {
                blocker.radius = Mathf.Lerp(startRadius, startRadius * sessionConfig.SpentScale, t);
                blocker.height = Mathf.Lerp(startHeight, startHeight * sessionConfig.SpentScale, t);
            }

            yield return null;
        }
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
            SpawnBurst(fruit);
            StartCoroutine(PopFruit(fruit, popDuration));
        }
    }

    // A few small spheres in the fruit's own (unlit) material fly outward and shrink away.
    private void SpawnBurst(GameObject fruit)
    {
        int count = sessionConfig != null ? sessionConfig.BurstCount : 0;
        MeshRenderer source = fruit.GetComponent<MeshRenderer>();
        if (count <= 0 || source == null || _sphereMesh == null)
        {
            return;
        }

        float size = sessionConfig.BurstSize;
        Vector3 origin = fruit.transform.position;
        var pieces = new Transform[count];
        var velocities = new Vector3[count];
        for (int i = 0; i < count; i++)
        {
            var piece = new GameObject("FruitBurst");
            piece.transform.position = origin;
            piece.transform.localScale = Vector3.one * size;
            piece.AddComponent<MeshFilter>().sharedMesh = _sphereMesh;
            MeshRenderer r = piece.AddComponent<MeshRenderer>();
            r.sharedMaterial = source.sharedMaterial;
            r.shadowCastingMode = UnityEngine.Rendering.ShadowCastingMode.Off;
            r.receiveShadows = false;
            pieces[i] = piece.transform;
            Vector3 dir = UnityEngine.Random.onUnitSphere;
            dir.y = Mathf.Abs(dir.y) * 0.6f + 0.3f;
            velocities[i] = dir.normalized * sessionConfig.BurstSpeed * UnityEngine.Random.Range(0.6f, 1.2f);
        }

        StartCoroutine(RunBurst(pieces, velocities, size, sessionConfig.BurstDuration));
    }

    private System.Collections.IEnumerator RunBurst(Transform[] pieces, Vector3[] velocities, float size, float duration)
    {
        float elapsed = 0f;
        duration = Mathf.Max(duration, 0.0001f);
        while (elapsed < duration)
        {
            elapsed += Time.deltaTime;
            float t = Mathf.Clamp01(elapsed / duration);
            for (int i = 0; i < pieces.Length; i++)
            {
                if (pieces[i] == null)
                {
                    continue;
                }

                velocities[i].y -= 6f * Time.deltaTime;
                pieces[i].position += velocities[i] * Time.deltaTime;
                pieces[i].localScale = Vector3.one * size * (1f - t * t);
            }

            yield return null;
        }

        for (int i = 0; i < pieces.Length; i++)
        {
            if (pieces[i] != null)
            {
                Destroy(pieces[i].gameObject);
            }
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
