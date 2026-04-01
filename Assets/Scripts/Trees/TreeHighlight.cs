using UnityEngine;

public class TreeHighlight : MonoBehaviour
{
    [SerializeField] public TerrainManager terrainManager;
    [SerializeField] private float ringRadius = 2.0f;
    [SerializeField] private int ringSegments = 48;
    [SerializeField] private float yOffset = 0.15f;
    [SerializeField] private LayerMask terrainMask;
    [SerializeField] private float pulseSpeed = 1.5f;
    [SerializeField] private float pulseMinAlpha = 0.4f;
    [SerializeField] private float pulseMaxAlpha = 0.9f;
    [SerializeField] private Color discColor = new Color(1f, 1f, 1f, 0.08f);

    private GameObject _discObject;
    private Mesh _discMesh;
    private MeshRenderer _discRenderer;
    private float _currentDiscRadius;

    private void Awake()
    {
        Shader shader = Shader.Find("Foraging/RingUnlit");

        // Create filled disc object.
        _discObject = new GameObject("HighlightDisc");
        _discObject.transform.SetParent(transform, false);

        MeshFilter discMf = _discObject.AddComponent<MeshFilter>();
        _discRenderer = _discObject.AddComponent<MeshRenderer>();

        _discMesh = new Mesh
        {
            name = "TreeHighlightDisc"
        };
        discMf.sharedMesh = _discMesh;

        Material discMat;
        if (shader != null)
        {
            discMat = new Material(shader);
            discMat.SetColor("_Color", discColor);
        }
        else
        {
            discMat = new Material(Shader.Find("Unlit/Color"));
            discMat.color = discColor;
        }

        _discRenderer.sharedMaterial = discMat;
        _discObject.SetActive(false);

        _currentDiscRadius = ringRadius;
    }

    public void SetVisible(bool visible)
    {
        if (visible)
        {
            UpdateDiscMesh();
            if (_discObject != null)
            {
                _discObject.SetActive(true);
            }
        }
        else
        {
            if (_discObject != null)
            {
                _discObject.SetActive(false);
            }
        }
    }

    public void SetRingRadius(float radius)
    {
        ringRadius = radius;
        _currentDiscRadius = radius;
    }

    private void UpdateDiscMesh()
    {
        if (_discMesh == null)
        {
            return;
        }

        int segments = Mathf.Max(3, ringSegments);
        // center + outer ring
        Vector3[] vertices = new Vector3[segments + 1];
        int[] triangles = new int[segments * 3];

        Vector3 centerWorld = transform.position;
        float centerHeight = SampleTerrainHeight(centerWorld.x, centerWorld.z);
        vertices[0] = new Vector3(0f, centerHeight - centerWorld.y, 0f);

        for (int i = 0; i < segments; i++)
        {
            float angle = (i / (float)segments) * Mathf.PI * 2f;
            float cos = Mathf.Cos(angle);
            float sin = Mathf.Sin(angle);

            float x = centerWorld.x + cos * _currentDiscRadius;
            float z = centerWorld.z + sin * _currentDiscRadius;
            float h = SampleTerrainHeight(x, z);

            vertices[i + 1] = new Vector3(x - centerWorld.x, h - centerWorld.y, z - centerWorld.z);
        }

        int tri = 0;
        for (int i = 0; i < segments; i++)
        {
            int current = i + 1;
            int next = ((i + 1) % segments) + 1;
            triangles[tri++] = 0;
            triangles[tri++] = next;
            triangles[tri++] = current;
        }

        _discMesh.Clear();
        _discMesh.vertices = vertices;
        _discMesh.triangles = triangles;
        _discMesh.RecalculateNormals();
        _discMesh.RecalculateBounds();
    }

    private float SampleTerrainHeight(float x, float z)
    {
        float defaultHeight = transform.position.y + yOffset;

        if (terrainManager != null)
        {
            // Use terrain mesh sampling if available as a fallback.
            defaultHeight = terrainManager.SampleElevation(x, z) + yOffset;
        }

        Vector3 origin = new Vector3(x, transform.position.y + 10f, z);
        if (Physics.Raycast(origin, Vector3.down, out RaycastHit hit, 50f, terrainMask, QueryTriggerInteraction.Ignore))
        {
            return hit.point.y + yOffset;
        }

        return defaultHeight;
    }

    private void Update()
    {
        if (_discObject != null && _discObject.activeSelf)
        {
            float t = (Mathf.Sin(Time.time * pulseSpeed * Mathf.PI * 2f) + 1f) * 0.5f;
            float alpha = Mathf.Lerp(pulseMinAlpha, pulseMaxAlpha, t);

            if (_discRenderer != null && _discRenderer.material != null)
            {
                Color c = discColor;
                c.a = alpha;
                _discRenderer.material.color = c;
            }

            _currentDiscRadius = Mathf.Lerp(ringRadius * 0.9f, ringRadius * 1.1f, t);
            UpdateDiscMesh();
        }
    }
}

