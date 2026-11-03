using TMPro;
using UnityEngine;
using UnityEngine.UI;

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

    // A key or mouse name on a highlighted chip (TextMeshPro rich text).
    public static string Chip(string key)
    {
        return $"<mark=#FFFFFF55 padding=\"18,18,6,6\"><b>{key}</b></mark>";
    }

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

    // A full-screen overlay canvas, scaled from the reference resolution, drawn above everything of a lower `sortingOrder`.
    public static Canvas Canvas(string name, Transform parent, int sortingOrder)
    {
        var root = new GameObject(name, typeof(RectTransform), typeof(Canvas), typeof(CanvasScaler));
        root.transform.SetParent(parent, false);
        var canvas = root.GetComponent<Canvas>();
        canvas.renderMode = RenderMode.ScreenSpaceOverlay;
        canvas.sortingOrder = sortingOrder;
        var scaler = root.GetComponent<CanvasScaler>();
        scaler.uiScaleMode = CanvasScaler.ScaleMode.ScaleWithScreenSize;
        scaler.referenceResolution = ReferenceResolution;
        return canvas;
    }

    // Such a canvas, optionally on black, with one centred title-size message; returns the message.
    public static TextMeshProUGUI MessageScreen(string name, Transform parent, int sortingOrder, bool black)
    {
        Transform root = Canvas(name, parent, sortingOrder).transform;
        if (black)
        {
            Image(root, "Dim", Color.black, Vector2.zero, Vector2.one, Vector2.zero, Vector2.zero);
        }

        return Label(root, "Message", "", Title, TextAlignmentOptions.Center, new Vector2(0.2f, 0.3f), new Vector2(0.8f, 0.7f), Color.white);
    }

    // A HUD readout (timer, score): bold centred text on a translucent plate of `plateSize` at `position`, drawn just behind it.
    public static void HudPlate(TextMeshProUGUI text, Vector2 position, Vector2 plateSize, float fontSize, Color plateColor, string name)
    {
        RectTransform rect = text.rectTransform;
        rect.anchoredPosition = position;
        rect.sizeDelta = plateSize - new Vector2(20f, 10f);
        text.fontSize = fontSize;
        text.fontStyle = FontStyles.Bold;
        text.alignment = TextAlignmentOptions.Center;

        Image plate = Image(rect.parent, name, plateColor, rect.anchorMin, rect.anchorMax, Vector2.zero, Vector2.zero);
        plate.raycastTarget = false;
        plate.rectTransform.pivot = rect.pivot;
        plate.rectTransform.anchoredPosition = position;
        plate.rectTransform.sizeDelta = plateSize;
        plate.rectTransform.SetSiblingIndex(rect.GetSiblingIndex());
    }

    // A text field that shows which one has focus (an accent outline and a lighter fill) and where the cursor is (a thick white caret,
    // a visible selection); TextMeshPro's defaults are a hairline caret in the text colour and no focus cue.
    public static void StyleInput(TMP_InputField input, Image background)
    {
        // The field creates its caret in OnEnable, which ran at AddComponent, before its text component was assigned: no caret was ever made.
        // Enabling it again, now that it is wired, creates it.
        input.enabled = false;
        input.enabled = true;
        input.customCaretColor = true;
        input.caretColor = Color.white;
        input.caretWidth = 3;
        input.caretBlinkRate = 1.1f;
        input.selectionColor = new Color(Accent.r, Accent.g, Accent.b, 0.5f);
        var outline = background.gameObject.AddComponent<Outline>();
        outline.effectColor = Accent;
        outline.effectDistance = new Vector2(3f, -3f);
        outline.enabled = false;
        Color focused = new Color(0.23f, 0.27f, 0.34f);
        input.onSelect.AddListener(_ => { outline.enabled = true; background.color = focused; });
        input.onDeselect.AddListener(_ => { outline.enabled = false; background.color = Field; });
    }

    public static void SetAnchors(RectTransform rect, Vector2 min, Vector2 max, Vector2 offsetMin, Vector2 offsetMax)
    {
        rect.anchorMin = min;
        rect.anchorMax = max;
        rect.offsetMin = offsetMin;
        rect.offsetMax = offsetMax;
    }

    public static Image Image(Transform parent, string name, Color color, Vector2 min, Vector2 max, Vector2 offsetMin, Vector2 offsetMax)
    {
        var go = new GameObject(name, typeof(RectTransform), typeof(Image));
        go.transform.SetParent(parent, false);
        SetAnchors(go.GetComponent<RectTransform>(), min, max, offsetMin, offsetMax);
        var image = go.GetComponent<Image>();
        image.color = color;
        return image;
    }

    public static TextMeshProUGUI Label(Transform parent, string name, string text, float size, TextAlignmentOptions alignment,
        Vector2 min, Vector2 max, Color? color = null)
    {
        var go = new GameObject(name, typeof(RectTransform), typeof(TextMeshProUGUI));
        go.transform.SetParent(parent, false);
        SetAnchors(go.GetComponent<RectTransform>(), min, max, Vector2.zero, Vector2.zero);
        var label = go.GetComponent<TextMeshProUGUI>();
        Apply(label, size);
        label.alignment = alignment;
        label.color = color ?? Ink;
        label.raycastTarget = false;
        label.text = text;
        return label;
    }
}
