using System;
using System.Collections.Generic;
using UnityEngine;

/*
Tree Prefab Setup (local space under this `Tree` object):

Canopy:
  - Sphere GameObject (mesh replaced at runtime with Unity default sphere)
  - Code sets: position (0, 0, 0), rotation aligns canopy up with terrain normal
  - No colliders on prefab children; Tree adds a canopy trigger collider via code

Fruits:
  - Fruits are fully runtime-generated in `ApplyAttributes()` (no fruit children required in the prefab).
  - No colliders on fruits; Tree removes the default primitive collider as part of generation.
*/
public class Tree : MonoBehaviour
{
    public TreeAttributes attributes;
    public int treeId;
    public SessionConfig sessionConfig;

    [SerializeField] private TerrainManager terrainManager;

    [SerializeField] private GameObject canopy;

    [SerializeField] private TreeHighlight highlight;

    [SerializeField] public int fruitCount = 10;
    [SerializeField] public float fruitRadius = 0.15f;
    [SerializeField] public int fruitSeed;

    private List<GameObject> _fruits = new List<GameObject>();

    private static readonly Color ColorLow = new Color(0.2f, 0.4f, 1.0f);
    private static readonly Color ColorHigh = new Color(1.0f, 0.5f, 0.1f);

    private static Mesh _sphereMesh;

    public bool isHarvested = false;

    private Vector3 _terrainNormal = Vector3.up;

    public int FruitCount => _fruits.Count;

    public TerrainManager TerrainManager
    {
        get => terrainManager;
        set => terrainManager = value;
    }

    private void Awake()
    {
        gameObject.tag = "Interactable";
    }

    private void Start()
    {
        ApplyAttributes();
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

        Quaternion normalRotation = Quaternion.FromToRotation(Vector3.up, _terrainNormal);
        canopy.transform.localRotation = normalRotation;

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

        // Adjust trigger radius to match bush size in world space, using a collider on the root.
        float maxScaleXZ = Mathf.Max(canopyScale.x, canopyScale.z);
        float padding = sessionConfig != null ? sessionConfig.HighlightRadiusPadding : 1.2f;
        float worldRadius = maxScaleXZ * 0.5f + padding;

        // Ensure no collider remains on the canopy child.
        SphereCollider canopyCollider = canopy.GetComponent<SphereCollider>();
        if (canopyCollider != null)
        {
            Destroy(canopyCollider);
        }

        SphereCollider rootCollider = GetComponent<SphereCollider>();
        if (rootCollider == null)
        {
            rootCollider = gameObject.AddComponent<SphereCollider>();
        }

        rootCollider.isTrigger = true;
        rootCollider.center = Vector3.zero;
        rootCollider.radius = worldRadius;

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

        if (highlight != null)
        {
            highlight.SetRingRadius(worldRadius);
        }

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

            GameObject fruit = GameObject.CreatePrimitive(PrimitiveType.Sphere);
            fruit.name = $"Fruit_{placed}";
            fruit.transform.SetParent(canopy.transform, false);
            fruit.transform.localScale = compensatedScale;
            fruit.transform.localPosition = new Vector3(x, y, z);

            SphereCollider collider = fruit.GetComponent<SphereCollider>();
            if (collider != null)
            {
                Destroy(collider);
            }

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

            GameObject fruit = GameObject.CreatePrimitive(PrimitiveType.Sphere);
            fruit.name = $"Fruit_{placed}";
            fruit.transform.SetParent(canopy.transform, false);
            fruit.transform.localScale = compensatedScale;
            fruit.transform.localPosition = apexLocal;

            SphereCollider collider = fruit.GetComponent<SphereCollider>();
            if (collider != null)
            {
                Destroy(collider);
            }

            MeshRenderer renderer = fruit.GetComponent<MeshRenderer>();
            if (renderer != null)
            {
                renderer.sharedMaterial = FruitMaterialManager.GetMaterial(fruitColor);
            }

            _fruits.Add(fruit);
            placed++;
        }
    }

    public float Evaluate(RewardFunction rf)
    {
        return rf.Evaluate(attributes);
    }

    public void SetHarvested(bool harvested)
    {
        foreach (GameObject fruit in _fruits)
        {
            if (fruit != null)
            {
                fruit.SetActive(!harvested);
            }
        }
    }

    public void HideFruit(int index)
    {
        if (index < 0 || index >= _fruits.Count)
        {
            return;
        }

        GameObject fruit = _fruits[index];
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
        if (highlight != null)
        {
            highlight.terrainManager = tm;
        }
    }

    public void SetHighlight(bool active)
    {
        if (highlight != null)
        {
            highlight.SetVisible(active);
        }
    }
}
