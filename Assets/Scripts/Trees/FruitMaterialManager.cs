using System.Collections.Generic;
using UnityEngine;

public static class FruitMaterialManager
{
    private static readonly Dictionary<Color, Material> Cache = new Dictionary<Color, Material>();
    private static SessionConfig _sessionConfig;

    public static void SetSessionConfig(SessionConfig config)
    {
        _sessionConfig = config;
        float preservation = config != null ? config.FruitColorPreservation : 0.5f;
        foreach (Material mat in Cache.Values)
        {
            if (mat != null)
            {
                mat.SetFloat("_ColorPreservation", preservation);
            }
        }
    }

    public static Material GetMaterial(Color color)
    {
        if (Cache.TryGetValue(color, out Material cached) && cached != null)
        {
            return cached;
        }

        Shader shader = Shader.Find("Foraging/FruitUnlit");
        if (shader == null)
        {
            Debug.LogError("Foraging/FruitUnlit shader not found. Using default material.");
            return new Material(Shader.Find("Universal Render Pipeline/Unlit"));
        }

        Material mat = new Material(shader)
        {
            color = color
        };

        Texture2D mainTex = Resources.Load<Texture2D>("Textures/Fruits/PaintedPlaster017_Color");
        Texture2D normalTex = Resources.Load<Texture2D>("Textures/Fruits/PaintedPlaster017_NormalGL");
        if (mainTex != null)
        {
            mat.SetTexture("_MainTex", mainTex);
        }
        else
        {
            Debug.LogWarning("FruitMaterialManager: Textures/Fruits/PaintedPlaster017_Color not found in Resources.");
        }

        if (normalTex != null)
        {
            mat.SetTexture("_NormalMap", normalTex);
        }
        else
        {
            Debug.LogWarning("FruitMaterialManager: Textures/Fruits/PaintedPlaster017_NormalGL not found in Resources.");
        }

        mat.SetFloat("_ColorPreservation", _sessionConfig != null ? _sessionConfig.FruitColorPreservation : 0.5f);

        Cache[color] = mat;
        return mat;
    }
}
