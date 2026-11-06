using TMPro;
using UnityEngine;
using UnityEngine.UI;

// The look shared by every piece of text in the game: one typeface and one set of sizes, in pixels of the 1920 x 1080 reference
// canvas that every canvas scales from. Runtime-built screens take their font and sizes from here; the scene's canvases are
// set to the same values (Nunito ExtraBold for titles, Nunito Sans for the rest, see Assets/Fonts/README.txt).
public static class UiStyle
{
    public const float Title = 72f;
    public const float Heading = 44f;
    public const float Body = 38f;
    public const float Small = 28f;
    public const float Hint = 28f;
    public const float EyebrowSize = 26f;
    public const float ButtonText = 36f;
    public const float PanelRadius = 28f;

    public static readonly Vector2 ReferenceResolution = new Vector2(1920f, 1080f);
    public static readonly Color Ink = new Color(0.93f, 0.94f, 0.96f);
    public static readonly Color Muted = new Color(0.62f, 0.66f, 0.72f);
    public static readonly Color Accent = new Color(0.36f, 0.62f, 0.95f);
    public static readonly Color Panel = new Color(0.10f, 0.11f, 0.14f);
    public static readonly Color Field = new Color(0.17f, 0.19f, 0.23f);
    public static readonly Color Glass = new Color(0.078f, 0.086f, 0.118f, 0.80f);        // a panel over the backdrop
    public static readonly Color FieldGlass = new Color(1f, 1f, 1f, 0.07f);
    public static readonly Color Good = new Color(0.47f, 0.84f, 0.63f);                 // only for "Completed"
    public static readonly Color Disabled = new Color(1f, 1f, 1f, 0.10f);

    // A key or mouse name on a highlighted chip (TextMeshPro rich text).
    public static string Chip(string key)
    {
        return $"<mark=#FFFFFF55 padding=\"18,18,6,6\"><b>{key}</b></mark><space=10>";
    }

    // Every [Key] in the text as a key chip.
    public static string Chips(string text)
    {
        return System.Text.RegularExpressions.Regex.Replace(text, @"\[([^\]]+)\]", m => Chip(m.Groups[1].Value));
    }

    private static TMP_FontAsset _font, _display, _bold;

    // The text face. Null when the font asset is missing, which leaves TextMeshPro's default.
    public static TMP_FontAsset Font => _font != null ? _font : (_font = Resources.Load<TMP_FontAsset>("Fonts/Nunito Sans SDF") ?? Resources.Load<TMP_FontAsset>("Fonts/Inter SDF"));

    // The face for titles (Title size and up) and the bold text face (for a HUD readout; `<b>` in rich text uses it too, through Nunito Sans's weight table).
    public static TMP_FontAsset DisplayFont => _display != null ? _display : (_display = Resources.Load<TMP_FontAsset>("Fonts/Nunito ExtraBold SDF") ?? Font);
    public static TMP_FontAsset BoldFont => _bold != null ? _bold : (_bold = Resources.Load<TMP_FontAsset>("Fonts/Nunito Sans Bold SDF") ?? Font);

    public static void Apply(TMP_Text text, float size)
    {
        TMP_FontAsset face = size >= 54f ? DisplayFont : Font;
        if (face != null)
        {
            text.font = face;
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
        if (BoldFont != null)
        {
            text.font = BoldFont;
        }

        text.alignment = TextAlignmentOptions.Center;

        Image plate = Image(rect.parent, name, plateColor, rect.anchorMin, rect.anchorMax, Vector2.zero, Vector2.zero);
        plate.raycastTarget = false;
        plate.sprite = RoundedSprite;                                        // a pill
        plate.type = UnityEngine.UI.Image.Type.Sliced;
        plate.pixelsPerUnitMultiplier = 48f / Mathf.Max(plateSize.y / 2f, 1f);
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
        Color idle = background.color;                                  // whatever the field was made with (the glass colour on the study's screens)
        Color focused = new Color(Mathf.Min(1f, idle.r + 0.07f), Mathf.Min(1f, idle.g + 0.07f), Mathf.Min(1f, idle.b + 0.07f), Mathf.Min(1f, idle.a + 0.06f));
        input.onSelect.AddListener(_ => { outline.enabled = true; background.color = focused; });
        input.onDeselect.AddListener(_ => { outline.enabled = false; background.color = idle; });
    }

    private static Sprite _rounded;

    // A white rounded square, nine-sliced: a corner radius of 48 reference pixels at multiplier 1 (see Rounded).
    public static Sprite RoundedSprite
    {
        get
        {
            if (_rounded == null)
            {
                const int size = 128;
                const float radius = 48f;
                var texture = new Texture2D(size, size, TextureFormat.RGBA32, false) { wrapMode = TextureWrapMode.Clamp, filterMode = FilterMode.Bilinear, name = "UiRounded" };
                float half = size / 2f;
                var pixels = new Color32[size * size];
                for (int y = 0; y < size; y++)
                {
                    for (int x = 0; x < size; x++)
                    {
                        float qx = Mathf.Abs(x + 0.5f - half) - (half - radius);
                        float qy = Mathf.Abs(y + 0.5f - half) - (half - radius);
                        float outside = Mathf.Sqrt(Mathf.Max(qx, 0f) * Mathf.Max(qx, 0f) + Mathf.Max(qy, 0f) * Mathf.Max(qy, 0f));
                        float distance = outside + Mathf.Min(Mathf.Max(qx, qy), 0f) - radius;
                        byte alpha = (byte)(Mathf.Clamp01(0.5f - distance) * 255f);
                        pixels[y * size + x] = new Color32(255, 255, 255, alpha);
                    }
                }

                texture.SetPixels32(pixels);
                texture.Apply();
                _rounded = Sprite.Create(texture, new Rect(0, 0, size, size), new Vector2(0.5f, 0.5f), 100f, 0, SpriteMeshType.FullRect, new Vector4(radius, radius, radius, radius));
            }

            return _rounded;
        }
    }

    // Anchors `rect` to the middle of its parent and puts it at (x, y) from there (y up), w by h, all in reference pixels.
    public static RectTransform Place(RectTransform rect, float x, float y, float w, float h)
    {
        rect.anchorMin = rect.anchorMax = rect.pivot = new Vector2(0.5f, 0.5f);
        rect.anchoredPosition = new Vector2(x, y);
        rect.sizeDelta = new Vector2(w, h);
        return rect;
    }

    // A rounded rectangle of `radius` reference pixels, anchored to the middle of its parent (see Place).
    public static Image Rounded(Transform parent, string name, Color color, float x, float y, float w, float h, float radius)
    {
        var go = new GameObject(name, typeof(RectTransform), typeof(Image));
        go.transform.SetParent(parent, false);
        Place(go.GetComponent<RectTransform>(), x, y, w, h);
        var image = go.GetComponent<Image>();
        image.sprite = RoundedSprite;
        image.type = UnityEngine.UI.Image.Type.Sliced;
        image.pixelsPerUnitMultiplier = 48f / Mathf.Max(radius, 1f);
        image.color = color;
        return image;
    }

    // Text placed like Place does, anchored in the middle (see Label for the style).
    public static TextMeshProUGUI Text(Transform parent, string name, string text, float size, TextAlignmentOptions alignment, float x, float y, float w, float h, Color? color = null)
    {
        TextMeshProUGUI label = Label(parent, name, text, size, alignment, Vector2.zero, Vector2.one, color);
        Place(label.rectTransform, x, y, w, h);
        return label;
    }

    // The small accent line over a title ("PART 3 OF 14"): bold, capitals, spaced.
    public static TextMeshProUGUI Eyebrow(Transform parent, string text, float x, float y, float w, TextAlignmentOptions alignment = TextAlignmentOptions.Left)
    {
        TextMeshProUGUI label = Text(parent, "Eyebrow", text.ToUpperInvariant(), EyebrowSize, alignment, x, y, w, 36f, Accent);
        label.font = BoldFont;
        label.characterSpacing = 4f;
        return label;
    }

    // A pill button: height 88 (or `height`), the accent colour (or an outline when `ghost`), a rounded label in the display face.
    public static Button Pill(Transform parent, string name, string caption, float x, float y, float w, UnityEngine.Events.UnityAction onClick, bool ghost = false, float height = 88f)
    {
        Image background = Rounded(parent, name, ghost ? new Color(1f, 1f, 1f, 0.12f) : Accent, x, y, w, height, height / 2f);
        TextMeshProUGUI label = Label(background.transform, "Text", caption, height < 80f ? 30f : ButtonText, TextAlignmentOptions.Center, Vector2.zero, Vector2.one, ghost ? Ink : new Color(0.05f, 0.07f, 0.10f));
        label.font = DisplayFont;
        var button = background.gameObject.AddComponent<Button>();
        button.targetGraphic = background;
        ColorBlock colors = button.colors;
        colors.disabledColor = new Color(1f, 1f, 1f, 0.25f);
        colors.highlightedColor = new Color(1f, 1f, 1f, 0.92f);
        colors.pressedColor = new Color(0.8f, 0.8f, 0.8f, 1f);
        button.colors = colors;
        if (onClick != null)
        {
            button.onClick.AddListener(onClick);
        }

        return button;
    }

    private static GameObject _bootBackdrop;

    // The one backdrop under all of the Boot scene's screens, made once (its own canvas, below them): switching from one screen to the next then leaves the picture
    // as it is, instead of each screen building its own and the new one starting from rest.
    public static void BootBackdrop()
    {
        if (_bootBackdrop != null)
        {
            return;
        }

        Canvas canvas = Canvas("BootBackdrop", null, 50);
        _bootBackdrop = canvas.gameObject;
        Backdrop(canvas.transform);
    }

    // The backdrop of the screens before the game: a still frame of the world (Resources/Backdrops/menu) under a dark scrim; the plain panel colour when the image is missing.
    public static void Backdrop(Transform parent, float scrimAlpha = 0.72f)
    {
        if (_bootBackdrop != null)
        {
            return;                                                      // the Boot scene's screens share one backdrop (BootBackdrop), so changing screens does not reload or restart it
        }

        Texture texture = Resources.Load<Texture>("Backdrops/menu");
        Image fallback = Image(parent, "Backdrop", new Color(0.06f, 0.07f, 0.09f), Vector2.zero, Vector2.one, Vector2.zero, Vector2.zero);
        fallback.raycastTarget = false;
        if (texture != null)
        {
            var go = new GameObject("BackdropImage", typeof(RectTransform), typeof(RawImage));
            go.transform.SetParent(parent, false);
            SetAnchors(go.GetComponent<RectTransform>(), Vector2.zero, Vector2.one, Vector2.zero, Vector2.zero);
            var raw = go.GetComponent<RawImage>();
            raw.texture = texture;
            raw.raycastTarget = false;
        }

        Image scrim = Image(parent, "Scrim", new Color(0.04f, 0.05f, 0.07f, scrimAlpha), Vector2.zero, Vector2.one, Vector2.zero, Vector2.zero);
        scrim.raycastTarget = false;
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
