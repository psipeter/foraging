using UnityEngine;
using UnityEngine.UI;

// The crosshair: four thin short bars around the centre of the view, always on, grey and mostly transparent (SessionConfig.crosshairAlpha) while nothing is aimed at. When it is on a
// bush that can be harvested the bars fade into the harvest ring: a clock-style ring in the selection colour that shows how much of that bush is left (HarvestManager.FocusFill), erased
// clockwise from 12 o'clock as it is harvested, with the erased part a faint track; an interrupted harvest keeps its fill. Built in code by
// GameManager on the HUD canvas; it is only a cue, the harvest rule (the hidden circle of crosshairRadius) is HarvestManager's.
public class AimCrosshair : MonoBehaviour
{
    private const float BarLength = 11f;
    private const float BarThickness = 1.5f;
    private const float Gap = 5f;
    private const float Outline = 1f;

    private HarvestManager _harvest;
    private SessionConfig _config;
    private RectTransform _root;
    private RectTransform _ring;
    private CanvasGroup _barsGroup, _ringGroup;
    private Image _ringFill;
    private float _blend, _fillShown = 1f;               // 0 = the bars, 1 = the ring

    public static AimCrosshair Build(Canvas canvas, HarvestManager harvest, SessionConfig config)
    {
        if (canvas == null)
        {
            return null;
        }

        var go = new GameObject("AimCrosshair", typeof(RectTransform));
        go.transform.SetParent(canvas.transform, false);
        var crosshair = go.AddComponent<AimCrosshair>();
        crosshair._harvest = harvest;
        crosshair._config = config;
        var shown = new GameObject("Bars", typeof(RectTransform));          // what is switched on and off (this object keeps running Update)
        shown.transform.SetParent(go.transform, false);
        crosshair._root = shown.GetComponent<RectTransform>();
        RectTransform self = go.GetComponent<RectTransform>();
        self.anchorMin = self.anchorMax = new Vector2(0.5f, 0.5f);
        self.anchoredPosition = Vector2.zero;
        self.sizeDelta = Vector2.zero;
        crosshair._root.anchorMin = crosshair._root.anchorMax = new Vector2(0.5f, 0.5f);
        crosshair._root.anchoredPosition = Vector2.zero;
        crosshair._root.sizeDelta = Vector2.zero;
        Vector2[] directions = { Vector2.up, Vector2.down, Vector2.left, Vector2.right };
        for (int i = 0; i < 4; i++)
        {
            bool vertical = directions[i].y != 0f;
            Vector2 size = vertical ? new Vector2(BarThickness, BarLength) : new Vector2(BarLength, BarThickness);
            Image outline = NewBar(crosshair._root, directions[i], size + Vector2.one * (2f * Outline), new Color(0f, 0f, 0f, 0.5f * config.CrosshairAlpha));
            NewBar(crosshair._root, directions[i], size, Idle(config));
            outline.transform.SetAsFirstSibling();
        }

        crosshair._barsGroup = crosshair._root.gameObject.AddComponent<CanvasGroup>();
        crosshair.BuildRing(go.transform);

        return crosshair;
    }

    private void BuildRing(Transform parent)
    {
        var go = new GameObject("HarvestRing", typeof(RectTransform), typeof(CanvasGroup));
        _ring = go.GetComponent<RectTransform>();
        _ring.SetParent(parent, false);
        _ring.anchorMin = _ring.anchorMax = new Vector2(0.5f, 0.5f);
        _ring.anchoredPosition = Vector2.zero;
        _ringGroup = go.GetComponent<CanvasGroup>();
        _ringGroup.alpha = 0f;
        _ringGroup.blocksRaycasts = false;
        Sprite sprite = RingSprite();
        Color selected = _config.RimSelectedColor;
        NewRingImage(_ring, sprite, false).color = new Color(selected.r, selected.g, selected.b, 0.25f);
        _ringFill = NewRingImage(_ring, sprite, true);
        _ringFill.color = new Color(selected.r, selected.g, selected.b, 1f);
    }

    private static Image NewRingImage(RectTransform parent, Sprite sprite, bool filled)
    {
        var go = new GameObject(filled ? "Fill" : "Track", typeof(RectTransform), typeof(Image));
        RectTransform rect = go.GetComponent<RectTransform>();
        rect.SetParent(parent, false);
        rect.anchorMin = Vector2.zero;
        rect.anchorMax = Vector2.one;
        rect.offsetMin = rect.offsetMax = Vector2.zero;
        Image image = go.GetComponent<Image>();
        image.sprite = sprite;
        image.raycastTarget = false;
        if (filled)
        {
            image.type = Image.Type.Filled;
            image.fillMethod = Image.FillMethod.Radial360;
            image.fillOrigin = 2;                    // from the top
            image.fillClockwise = false;             // the arc that is left runs from 12 o'clock back round to where the erased part ends
        }

        return image;
    }

    private static Sprite _ringSprite;

    // A ring (inner and outer radius 0.72 and 0.96 of the half size, soft edges), white, tinted by the Image.
    private static Sprite RingSprite()
    {
        if (_ringSprite != null)
        {
            return _ringSprite;
        }

        const int size = 256;
        var texture = new Texture2D(size, size, TextureFormat.RGBA32, false) { wrapMode = TextureWrapMode.Clamp, filterMode = FilterMode.Bilinear };
        var pixels = new Color32[size * size];
        const float inner = 0.72f, outer = 0.96f, edge = 0.012f;
        for (int y = 0; y < size; y++)
        {
            for (int x = 0; x < size; x++)
            {
                float r = new Vector2((x + 0.5f) / size * 2f - 1f, (y + 0.5f) / size * 2f - 1f).magnitude;
                float a = Mathf.Clamp01((r - (inner - edge)) / (2f * edge)) * Mathf.Clamp01(((outer + edge) - r) / (2f * edge));
                pixels[y * size + x] = new Color32(255, 255, 255, (byte)Mathf.RoundToInt(a * 255f));
            }
        }

        texture.SetPixels32(pixels);
        texture.Apply();
        _ringSprite = Sprite.Create(texture, new Rect(0f, 0f, size, size), new Vector2(0.5f, 0.5f), 100f);
        return _ringSprite;
    }

    private static Color Idle(SessionConfig config)
    {
        return new Color(0.8f, 0.8f, 0.8f, config.CrosshairAlpha);
    }

    private static Image NewBar(RectTransform parent, Vector2 direction, Vector2 size, Color color)
    {
        var go = new GameObject("Bar", typeof(RectTransform), typeof(Image));
        RectTransform rect = go.GetComponent<RectTransform>();
        rect.SetParent(parent, false);
        rect.sizeDelta = size;
        rect.anchoredPosition = direction * (Gap + (direction.y != 0f ? size.y : size.x) * 0.5f);
        Image image = go.GetComponent<Image>();
        image.color = color;
        image.raycastTarget = false;
        return image;
    }

    private void Update()
    {
        bool live = Time.timeScale > 0f && _config.CrosshairAlpha > 0f;      // not over the instruction screen or a pause, and not switched off
        if (_root.gameObject.activeSelf != live)
        {
            _root.gameObject.SetActive(live);
            _ring.gameObject.SetActive(live);
        }

        if (!live)
        {
            return;
        }

        float fill = _harvest != null ? _harvest.FocusFill : -1f;
        bool aimed = fill >= 0f;
        if (aimed)
        {
            _fillShown = fill;
        }

        _blend = Mathf.Lerp(_blend, aimed ? 1f : 0f, 1f - Mathf.Exp(-20f * Time.unscaledDeltaTime));
        _barsGroup.alpha = 1f - _blend;
        _ringFill.fillAmount = Mathf.Clamp01(_fillShown);
        _ringGroup.alpha = _blend;
        float height = ((RectTransform)transform.parent).rect.height;
        float diameter = _config.HarvestRingSizeDeg / Mathf.Max(_config.CameraFieldOfView, 1f) * height;
        _ring.sizeDelta = Vector2.one * diameter;
        _ring.localScale = Vector3.one * Mathf.Lerp(0.85f, 1f, _blend);
    }
}
