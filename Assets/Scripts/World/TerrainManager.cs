using UnityEngine;

[DefaultExecutionOrder(-10)]
public class TerrainManager : MonoBehaviour
{
    public SessionConfig sessionConfig;
    public WorldData world;
    [SerializeField] private GameObject groundObject;
    [SerializeField] private Material terrainMaterial;

    private static readonly Color Arid = new Color(0.76f, 0.65f, 0.42f);
    private static readonly Color Grassland = new Color(0.44f, 0.56f, 0.24f);
    private static readonly Color Swampy = new Color(0.22f, 0.29f, 0.18f);

    public GameObject GroundObject => groundObject;

    private void Start()
    {
        if (groundObject == null || world == null)
        {
            return;
        }

        int res = world.Res;

        var mesh = new Mesh
        {
            name = $"ForagingTerrain_{res}",
            indexFormat = res * res > 65535
                ? UnityEngine.Rendering.IndexFormat.UInt32
                : UnityEngine.Rendering.IndexFormat.UInt16
        };

        // Vertex layout: i across X (worldX), j across Z (worldZ); the world file's grids use the same layout.
        int vertexCount = res * res;
        var vertices = new Vector3[vertexCount];
        var uvs = new Vector2[vertexCount];
        var uvs2 = new Vector2[vertexCount];
        var uvs3 = new Vector2[vertexCount];
        var colors = new Color[vertexCount];

        float inv = 1f / (res - 1);
        float halfExtent = world.HalfExtent;

        for (int i = 0; i < res; i++)
        {
            float worldX = Mathf.Lerp(-halfExtent, halfExtent, i * inv);
            for (int j = 0; j < res; j++)
            {
                float worldZ = Mathf.Lerp(-halfExtent, halfExtent, j * inv);

                int idx = i * res + j;
                float m = world.MoistureGrid[idx];
                vertices[idx] = new Vector3(worldX, world.ElevationGrid[idx], worldZ);
                uvs[idx] = new Vector2(i * inv, j * inv);
                uvs2[idx] = new Vector2(m, 0f);
                uvs3[idx] = new Vector2(world.RockGrid[idx], world.SnowGrid[idx]);
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

    }

    // Terrain fields are bilinear samples of the world file's mesh grids (the mesh interpolates the same way).
    // Valley elevation (coupled to moisture) plus the mountain term, which is exactly 0 inside the valley.
    public float SampleElevation(float worldX, float worldZ)
    {
        return world != null ? world.Sample(world.ElevationGrid, worldX, worldZ) : 0f;
    }

    // Mountain ramp: 0 across the valley, rising to 1 at the map edge. The foot of the ramp is irregular.
    public float SampleMountain(float worldX, float worldZ)
    {
        return world != null ? world.Sample(world.RampGrid, worldX, worldZ) : 0f;
    }

    // False on mountain slopes and at the world edge; the player cannot move there.
    public bool IsWalkable(float worldX, float worldZ)
    {
        float halfExtent = world != null ? world.HalfExtent : 50f;
        if (Mathf.Abs(worldX) > halfExtent - 1f || Mathf.Abs(worldZ) > halfExtent - 1f)
        {
            return false;
        }

        float threshold = sessionConfig != null ? sessionConfig.MountainBlockThreshold : 1f;
        return SampleMountain(worldX, worldZ) < threshold;
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
