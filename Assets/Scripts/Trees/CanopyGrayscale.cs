using UnityEngine;

// Greyed copies of the canopy texture, for fading the world's bushes to grayscale during a ranking break (Tree.SetGray). The canopy is URP/Lit, which has no saturation
// control, so the texture is stepped through a few progressively desaturated copies (the tint, a colour, is faded smoothly beside it) instead of changing the shader.
// Made once, on first use, at half the texture's size from a GPU copy of it (the canopy texture is not readable).
public static class CanopyGrayscale
{
    public const int Levels = 5;                         // level 0 is the original, level Levels - 1 fully grey
    private const int Size = 512;

    private static Texture _source;
    private static Texture2D[] _textures;

    // The texture at `level` (0 to Levels - 1) of `source`; level 0 is `source` itself.
    public static Texture Texture(Texture source, int level)
    {
        level = Mathf.Clamp(level, 0, Levels - 1);
        if (level == 0 || source == null)
        {
            return source;
        }

        if (_textures == null || _source != source)
        {
            Build(source);
        }

        return _textures[level];
    }

    private static void Build(Texture source)
    {
        _source = source;
        RenderTexture target = RenderTexture.GetTemporary(Size, Size, 0, RenderTextureFormat.ARGB32, RenderTextureReadWrite.sRGB);
        Graphics.Blit(source, target);
        RenderTexture previous = RenderTexture.active;
        RenderTexture.active = target;
        var original = new Texture2D(Size, Size, TextureFormat.RGBA32, false, false);
        original.ReadPixels(new Rect(0, 0, Size, Size), 0, 0);
        RenderTexture.active = previous;
        RenderTexture.ReleaseTemporary(target);
        Color32[] pixels = original.GetPixels32();
        Object.Destroy(original);

        _textures = new Texture2D[Levels];
        for (int level = 1; level < Levels; level++)
        {
            float amount = level / (float)(Levels - 1);
            var grey = new Color32[pixels.Length];
            for (int i = 0; i < pixels.Length; i++)
            {
                Color32 p = pixels[i];
                float luminance = 0.299f * p.r + 0.587f * p.g + 0.114f * p.b;
                grey[i] = new Color32((byte)Mathf.RoundToInt(Mathf.Lerp(p.r, luminance, amount)), (byte)Mathf.RoundToInt(Mathf.Lerp(p.g, luminance, amount)),
                    (byte)Mathf.RoundToInt(Mathf.Lerp(p.b, luminance, amount)), p.a);
            }

            var texture = new Texture2D(Size, Size, TextureFormat.RGBA32, true, false) { wrapMode = source.wrapMode, filterMode = FilterMode.Bilinear, name = $"CanopyGrey{level}" };
            texture.SetPixels32(grey);
            texture.Apply(true, true);
            _textures[level] = texture;
        }
    }
}
