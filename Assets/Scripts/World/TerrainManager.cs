using UnityEngine;

[DefaultExecutionOrder(-10)]
public class TerrainManager : MonoBehaviour
{
    public SessionConfig sessionConfig;
    [SerializeField] private GameObject groundObject;
    [SerializeField] private Material terrainMaterial;
    [SerializeField] private SunController sunController;

    private static readonly Color Arid = new Color(0.76f, 0.65f, 0.42f);
    private static readonly Color Grassland = new Color(0.44f, 0.56f, 0.24f);
    private static readonly Color Swampy = new Color(0.22f, 0.29f, 0.18f);

    public GameObject GroundObject => groundObject;

    private Color[] _baseColors;

    private void Start()
    {
        if (groundObject == null)
        {
            return;
        }

        int res = sessionConfig != null ? Mathf.Max(2, sessionConfig.TerrainMeshResolution) : 64;
        float maxElevation = sessionConfig != null ? sessionConfig.TerrainMaxElevation : 3f;

        var mesh = new Mesh
        {
            name = $"ForagingTerrain_{res}",
            indexFormat = res * res > 65535
                ? UnityEngine.Rendering.IndexFormat.UInt32
                : UnityEngine.Rendering.IndexFormat.UInt16
        };

        // Vertex layout: i across X (worldX), j across Z (worldZ).
        int vertexCount = res * res;
        var vertices = new Vector3[vertexCount];
        var uvs = new Vector2[vertexCount];
        var uvs2 = new Vector2[vertexCount];
        var uvs3 = new Vector2[vertexCount];
        var colors = new Color[vertexCount];

        float inv = 1f / (res - 1);

        float halfExtent = sessionConfig != null ? sessionConfig.WorldHalfExtent : 50f;

        for (int i = 0; i < res; i++)
        {
            float worldX = Mathf.Lerp(-halfExtent, halfExtent, i * inv);
            for (int j = 0; j < res; j++)
            {
                float worldZ = Mathf.Lerp(-halfExtent, halfExtent, j * inv);

                float m = SampleMoisture(worldX, worldZ);
                float elevation = SampleElevation(worldX, worldZ);

                int idx = i * res + j;
                vertices[idx] = new Vector3(worldX, elevation, worldZ);
                uvs[idx] = new Vector2(i * inv, j * inv);
                uvs2[idx] = new Vector2(m, 0f);
                uvs3[idx] = MountainWeights(worldX, worldZ, elevation);
                colors[idx] = MoistureToColor(m);
            }
        }

        // Two triangles per grid cell, consistent winding order.
        int quadCount = (res - 1) * (res - 1);
        var triangles = new int[quadCount * 6];

        int t = 0;
        for (int i = 0; i < res - 1; i++)
        {
            for (int j = 0; j < res - 1; j++)
            {
                int v00 = i * res + j;
                int v10 = (i + 1) * res + j;
                int v01 = i * res + (j + 1);
                int v11 = (i + 1) * res + (j + 1);

                // Upward facing triangles.
                triangles[t++] = v00;
                triangles[t++] = v01;
                triangles[t++] = v10;

                triangles[t++] = v10;
                triangles[t++] = v01;
                triangles[t++] = v11;
            }
        }

        mesh.vertices = vertices;
        mesh.uv = uvs;
        mesh.uv2 = uvs2;
        mesh.SetUVs(2, uvs3);
        mesh.colors = colors;
        mesh.triangles = triangles;
        mesh.RecalculateNormals();
        mesh.RecalculateTangents();

        MeshFilter meshFilter = groundObject.GetComponent<MeshFilter>();
        if (meshFilter == null)
        {
            meshFilter = groundObject.AddComponent<MeshFilter>();
        }
        meshFilter.sharedMesh = mesh;

        MeshRenderer meshRenderer = groundObject.GetComponent<MeshRenderer>();
        if (meshRenderer == null)
        {
            meshRenderer = groundObject.AddComponent<MeshRenderer>();
        }

        if (terrainMaterial != null)
        {
            meshRenderer.sharedMaterial = terrainMaterial;
        }
        else
        {
            Shader shader = Shader.Find("Universal Render Pipeline/Unlit/VertexColor");
            if (shader == null)
            {
                Debug.LogWarning("VertexColor shader not found. Falling back to Unlit/Color.");
                shader = Shader.Find("Unlit/Color");
            }
            meshRenderer.sharedMaterial = new Material(shader);
        }

        if (sessionConfig != null)
        {
            // Instance the material so per-session mountain settings do not modify the shared asset.
            Material material = meshRenderer.material;
            material.SetColor("_RockColor", sessionConfig.MountainRockColor);
            material.SetColor("_SnowColor", sessionConfig.MountainSnowColor);
            material.SetFloat("_MountainFogStrength", sessionConfig.MountainFogStrength);
        }

        meshRenderer.shadowCastingMode = UnityEngine.Rendering.ShadowCastingMode.TwoSided;
        meshRenderer.receiveShadows = true;

        MeshCollider meshCollider = groundObject.GetComponent<MeshCollider>();
        if (meshCollider == null)
        {
            meshCollider = groundObject.AddComponent<MeshCollider>();
        }
        meshCollider.sharedMesh = mesh;

        _baseColors = colors;

        UpdateTerrainLighting();
    }

    public float SampleMoisture(float worldX, float worldZ)
    {
        return Mathf.Clamp01(ComputeMoisture(worldX, worldZ));
    }

    // Valley elevation (coupled to moisture) plus the mountain term, which is exactly 0 inside the valley.
    public float SampleElevation(float worldX, float worldZ)
    {
        float maxElevation = sessionConfig != null ? sessionConfig.TerrainMaxElevation : 3f;
        return (1f - SampleMoisture(worldX, worldZ)) * maxElevation + SampleMountainElevation(worldX, worldZ);
    }

    // Mountain ramp: 0 across the valley, rising to 1 at the map edge. The foot of the ramp is irregular.
    public float SampleMountain(float worldX, float worldZ)
    {
        return MountainRamp(worldX, worldZ, 0f);
    }

    public float SampleMountainElevation(float worldX, float worldZ)
    {
        float u = MountainRamp(worldX, worldZ, 0f);
        if (u <= 0f)
        {
            return 0f;
        }

        float height = sessionConfig.MountainHeight;
        return height * Mathf.Pow(u, 1.5f) * (0.55f + 0.45f * Ridged(worldX, worldZ));
    }

    // False on mountain slopes and at the world edge; the player cannot move there.
    public bool IsWalkable(float worldX, float worldZ)
    {
        float halfExtent = sessionConfig != null ? sessionConfig.WorldHalfExtent : 50f;
        if (Mathf.Abs(worldX) > halfExtent - 1f || Mathf.Abs(worldZ) > halfExtent - 1f)
        {
            return false;
        }

        float threshold = sessionConfig != null ? sessionConfig.MountainBlockThreshold : 1f;
        return MountainRamp(worldX, worldZ, 0f) < threshold;
    }

    // True where a tree may stand: in the valley and at least treeEdgeMargin back from the mountain foot.
    public bool IsTreeSite(float worldX, float worldZ)
    {
        float margin = sessionConfig != null ? sessionConfig.TreeEdgeMargin : 0f;
        return MountainRamp(worldX, worldZ, margin) <= 0f;
    }

    private float MountainRamp(float worldX, float worldZ, float inset)
    {
        if (sessionConfig == null || sessionConfig.MountainBandWidth <= 0f)
        {
            return 0f;
        }

        float band = sessionConfig.MountainBandWidth;
        float edgeDist = sessionConfig.WorldHalfExtent - Mathf.Max(Mathf.Abs(worldX), Mathf.Abs(worldZ)) - inset;

        // Jitter the band's inner boundary only: edgeDist 0 always gives ramp 1, so the crest is never
        // lowered where the mesh ends.
        float jitterNoise = Mathf.PerlinNoise(worldX / 70f + SeedX + 53.1f, worldZ / 70f + SeedZ + 11.7f);
        float effectiveBand = Mathf.Max(10f, band + (jitterNoise - 0.5f) * 2f * sessionConfig.MountainBoundaryJitter);
        return Mathf.Clamp01(1f - edgeDist / effectiveBand);
    }

    // Ridged multifractal noise in [0, 1]: sharp crests, so the skyline reads as rock, not rolling hills.
    private float Ridged(float worldX, float worldZ)
    {
        float scale = Mathf.Max(1f, sessionConfig.MountainNoiseScale);
        float value = 0f;
        float amplitude = 1f;
        float total = 0f;
        float freq = 1f / scale;

        for (int o = 0; o < 3; o++)
        {
            float n = Mathf.PerlinNoise(worldX * freq + SeedX + o * 23.9f, worldZ * freq + SeedZ + o * 41.3f);
            value += (1f - Mathf.Abs(2f * n - 1f)) * amplitude;
            total += amplitude;
            amplitude *= 0.5f;
            freq *= 2.1f;
        }

        return value / total;
    }

    // (rock weight, snow weight) for the terrain shader; (0, 0) in the valley.
    private Vector2 MountainWeights(float worldX, float worldZ, float elevation)
    {
        if (sessionConfig == null)
        {
            return Vector2.zero;
        }

        float u = SampleMountain(worldX, worldZ);
        if (u <= 0f)
        {
            return Vector2.zero;
        }

        // Noise on the ramp makes the grass-to-rock transition irregular.
        float rockNoise = Mathf.PerlinNoise(worldX / 9f + SeedX, worldZ / 9f + SeedZ + 97.3f);
        float rock = Mathf.SmoothStep(0f, 1f, (u + (rockNoise - 0.5f) * 0.12f) / 0.25f);

        float snowLine = sessionConfig.TerrainMaxElevation + sessionConfig.SnowLineFraction * sessionConfig.MountainHeight;
        float snowNoise = (Mathf.PerlinNoise(worldX / 14f + SeedX + 7.7f, worldZ / 14f + SeedZ + 3.1f) - 0.5f) * 12f;
        float snow = Mathf.SmoothStep(0f, 1f, (elevation + snowNoise - (snowLine - 4f)) / 8f);
        return new Vector2(rock, snow * rock);
    }

    private float SeedX => sessionConfig != null ? sessionConfig.WorldSeed * 127.3f : 0f;
    private float SeedZ => sessionConfig != null ? sessionConfig.WorldSeed * 311.7f : 0f;

    public Vector3 SampleNormal(float worldX, float worldZ)
    {
        float hL = SampleElevation(worldX - 0.5f, worldZ);
        float hR = SampleElevation(worldX + 0.5f, worldZ);
        float hD = SampleElevation(worldX, worldZ - 0.5f);
        float hU = SampleElevation(worldX, worldZ + 0.5f);
        Vector3 normal = new Vector3(hL - hR, 1f, hD - hU);
        return normal.normalized;
    }

    public void UpdateTerrainLighting()
    {
        if (groundObject == null)
        {
            return;
        }

        Color ambient = sunController != null ? sunController.CurrentAmbientColor : RenderSettings.ambientLight;

        MeshFilter meshFilter = groundObject.GetComponent<MeshFilter>();
        if (meshFilter == null || meshFilter.sharedMesh == null || _baseColors == null)
        {
            return;
        }

        Mesh mesh = meshFilter.sharedMesh;
        Color[] tintedColors = mesh.colors;
        if (tintedColors == null || tintedColors.Length != _baseColors.Length)
        {
            tintedColors = new Color[_baseColors.Length];
        }

        Color ambientScaled = ambient * 2f;

        for (int i = 0; i < _baseColors.Length; i++)
        {
            tintedColors[i] = _baseColors[i] * ambientScaled;
        }

        mesh.colors = tintedColors;
        mesh.UploadMeshData(false);
    }

    private float ComputeMoisture(float worldX, float worldZ)
    {
        float frequency = sessionConfig != null ? sessionConfig.TerrainNoiseFrequency : 4f;
        int octaves = sessionConfig != null ? Mathf.Max(1, sessionConfig.TerrainNoiseOctaves) : 1;
        float seedX = sessionConfig != null ? sessionConfig.WorldSeed * 127.3f : 0f;
        float seedZ = sessionConfig != null ? sessionConfig.WorldSeed * 311.7f : 0f;

        float value = 0f;
        float amplitude = 1f;
        float maxAccum = 0f;
        float freq = frequency * 0.01f;

        for (int o = 0; o < octaves; o++)
        {
            float nx = worldX * freq + seedX + o * 17.3f;
            float nz = worldZ * freq + seedZ + o * 31.7f;
            value += Mathf.PerlinNoise(nx, nz) * amplitude;
            maxAccum += amplitude;
            amplitude *= 0.5f;
            freq *= 2f;
        }

        if (maxAccum <= 0f)
        {
            return 0f;
        }

        return value / maxAccum;
    }

    private Color MoistureToColor(float moisture)
    {
        Color arid = Arid;
        Color grassland = Grassland;
        Color swampy = Swampy;

        float m = Mathf.Clamp01(moisture);

        // Apply contrast curve before mapping to the gradient.
        float contrast = 1.5f;
        contrast = Mathf.Max(0.0001f, contrast);

        if (m <= 0.5f)
        {
            float t = m * 2f;
            t = Mathf.Pow(t, 1f / contrast);
            m = t * 0.5f;
        }
        else
        {
            float t = (1f - m) * 2f;
            t = Mathf.Pow(t, 1f / contrast);
            m = 1f - t * 0.5f;
        }

        if (m <= 0.5f)
        {
            return Color.Lerp(arid, grassland, m / 0.5f);
        }

        return Color.Lerp(grassland, swampy, (m - 0.5f) / 0.5f);
    }
}
