using UnityEngine;

public class BorderWalls : MonoBehaviour
{
    public SessionConfig sessionConfig;
    public TerrainManager terrainManager;
    [SerializeField] private SunController sunController;

    private Material _wallMaterial;
    private Color _borderWallColor;

    private void Start()
    {
        Generate();
    }

    public void Generate()
    {
        if (sessionConfig == null)
        {
            return;
        }

        float worldHalfExtent = sessionConfig.WorldHalfExtent;
        _borderWallColor = sessionConfig.BorderWallColor;

        float thickness = worldHalfExtent * 0.1f;
        float avgEdgeElevation = ComputeMaxBoundaryElevation(worldHalfExtent);
        float bottomY = -(sessionConfig.TerrainMaxElevation);
        float topY = avgEdgeElevation + sessionConfig.BorderWallHeight;
        float wallTotalHeight = topY - bottomY;
        float yCenter = bottomY + wallTotalHeight * 0.5f;

        Shader litShader = Shader.Find("Universal Render Pipeline/Lit");
        if (litShader == null)
        {
            litShader = Shader.Find("Standard");
        }

        _wallMaterial = new Material(litShader);
        _wallMaterial.color = _borderWallColor;

        int treeLayer = LayerMask.NameToLayer("Tree");

        SpawnWall("BorderWall_North", new Vector3(0f, yCenter, worldHalfExtent + thickness * 0.5f),
            new Vector3(worldHalfExtent * 2f + thickness * 2f, wallTotalHeight, thickness), treeLayer);

        SpawnWall("BorderWall_South", new Vector3(0f, yCenter, -(worldHalfExtent + thickness * 0.5f)),
            new Vector3(worldHalfExtent * 2f + thickness * 2f, wallTotalHeight, thickness), treeLayer);

        SpawnWall("BorderWall_East", new Vector3(worldHalfExtent + thickness * 0.5f, yCenter, 0f),
            new Vector3(thickness, wallTotalHeight, worldHalfExtent * 2f), treeLayer);

        SpawnWall("BorderWall_West", new Vector3(-(worldHalfExtent + thickness * 0.5f), yCenter, 0f),
            new Vector3(thickness, wallTotalHeight, worldHalfExtent * 2f), treeLayer);
    }

    private float ComputeMaxBoundaryElevation(float e)
    {
        if (terrainManager == null)
        {
            return 0f;
        }

        float maxH = float.NegativeInfinity;
        Vector2[] samples =
        {
            new Vector2(-e, -e),
            new Vector2(e, -e),
            new Vector2(-e, e),
            new Vector2(e, e),
            new Vector2(0f, -e),
            new Vector2(0f, e),
            new Vector2(-e, 0f),
            new Vector2(e, 0f)
        };

        for (int i = 0; i < samples.Length; i++)
        {
            float h = terrainManager.SampleElevation(samples[i].x, samples[i].y);
            if (h > maxH)
            {
                maxH = h;
            }
        }

        return maxH;
    }

    private void SpawnWall(string name, Vector3 localPosition, Vector3 localScale, int treeLayer)
    {
        GameObject wall = GameObject.CreatePrimitive(PrimitiveType.Cube);
        wall.name = name;
        wall.transform.SetParent(transform, false);
        wall.transform.localPosition = localPosition;
        wall.transform.localScale = localScale;

        BoxCollider oldCol = wall.GetComponent<BoxCollider>();
        if (oldCol != null)
        {
            Destroy(oldCol);
        }

        BoxCollider box = wall.AddComponent<BoxCollider>();
        box.isTrigger = false;

        if (treeLayer >= 0)
        {
            wall.layer = treeLayer;
        }

        MeshRenderer renderer = wall.GetComponent<MeshRenderer>();
        if (renderer != null)
        {
            renderer.sharedMaterial = _wallMaterial;
        }
    }

    public void UpdateLighting(Color ambientColor)
    {
        if (_wallMaterial == null)
        {
            return;
        }

        _wallMaterial.color = _borderWallColor;
    }
}
