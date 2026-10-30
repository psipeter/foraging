using TMPro;
using UnityEngine;

// The look shared by every piece of text in the game: one typeface and one set of sizes, in pixels of the 1920 x 1080 reference
// canvas that every canvas scales from. Runtime-built screens take their font and sizes from here; the scene's canvases are
// set to the same values (Inter, see Assets/Fonts/README.txt).
public static class UiStyle
{
    public const float Title = 64f;
    public const float Body = 40f;
    public const float Small = 30f;
    public const float Hint = 28f;

    public static readonly Vector2 ReferenceResolution = new Vector2(1920f, 1080f);
    public static readonly Color Ink = new Color(0.93f, 0.94f, 0.96f);
    public static readonly Color Muted = new Color(0.62f, 0.66f, 0.72f);
    public static readonly Color Accent = new Color(0.36f, 0.62f, 0.95f);
    public static readonly Color Panel = new Color(0.10f, 0.11f, 0.14f);
    public static readonly Color Field = new Color(0.17f, 0.19f, 0.23f);

    private static TMP_FontAsset _font;

    // Null when the font asset is missing, which leaves TextMeshPro's default.
    public static TMP_FontAsset Font => _font != null ? _font : (_font = Resources.Load<TMP_FontAsset>("Fonts/Inter SDF"));

    public static void Apply(TMP_Text text, float size)
    {
        if (Font != null)
        {
            text.font = Font;
        }

        text.fontSize = size;
    }
}
