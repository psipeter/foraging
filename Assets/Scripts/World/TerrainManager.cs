using UnityEngine;

[DefaultExecutionOrder(-10)]
public class TerrainManager : MonoBehaviour
{
    [SerializeField] private SessionConfig sessionConfig;
    [SerializeField] private MeshRenderer groundRenderer;
    [SerializeField] private int textureResolution = 256;
    [SerializeField] private float noiseFrequency = 4f;
    [SerializeField] private int noiseOctaves = 1;

    private const float WorldHalfExtent = 50f;

    private static readonly Color Arid = new Color(0.85f, 0.72f, 0.35f);
    private static readonly Color Grassland = new Color(0.35f, 0.55f, 0.15f);
    private static readonly Color Swampy = new Color(0.1f, 0.2f, 0.08f);

    private void Start()
    {
        if (groundRenderer == null)
        {
            return;
        }

        int res = Mathf.Max(2, textureResolution);
        var texture = new Texture2D(res, res, TextureFormat.RGBA32, false)
        {
            wrapMode = TextureWrapMode.Clamp,
            filterMode = FilterMode.Bilinear
        };

        for (int py = 0; py < res; py++)
        {
            for (int px = 0; px < res; px++)
            {
                float wx = Mathf.Lerp(-WorldHalfExtent, WorldHalfExtent, px / (float)(res - 1));
                float wz = Mathf.Lerp(-WorldHalfExtent, WorldHalfExtent, py / (float)(res - 1));
                float m = SampleMoisture(wx, wz);
                texture.SetPixel(px, py, MoistureToColor(m));
            }
        }

        texture.Apply();
        groundRenderer.material.mainTexture = texture;
    }

    public float SampleMoisture(float worldX, float worldZ)
    {
        return Mathf.Clamp01(ComputeMoisture(worldX, worldZ));
    }

    private float ComputeMoisture(float worldX, float worldZ)
    {
        float frequency = sessionConfig != null ? sessionConfig.TerrainNoiseFrequency : noiseFrequency;
        int octaves = sessionConfig != null ? Mathf.Max(1, sessionConfig.TerrainNoiseOctaves) : Mathf.Max(1, noiseOctaves);
        float seedX = sessionConfig != null ? sessionConfig.WorldSeed * 0.0012345f : 0f;
        float seedZ = sessionConfig != null ? sessionConfig.WorldSeed * 0.006789f : 0f;

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
        Color arid = sessionConfig != null ? sessionConfig.TerrainArid : Arid;
        Color grassland = sessionConfig != null ? sessionConfig.TerrainGrassland : Grassland;
        Color swampy = sessionConfig != null ? sessionConfig.TerrainSwampy : Swampy;

        float m = Mathf.Clamp01(moisture);
        if (m <= 0.5f)
        {
            return Color.Lerp(arid, grassland, m / 0.5f);
        }

        return Color.Lerp(grassland, swampy, (m - 0.5f) / 0.5f);
    }
}
