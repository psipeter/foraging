using System.Collections.Generic;
using UnityEngine;

public static class FruitMaterialManager
{
    private static readonly Dictionary<Color, Material> Cache = new Dictionary<Color, Material>();

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

        Cache[color] = mat;
        return mat;
    }
}

