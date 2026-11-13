using UnityEngine;
using UnityEngine.UI;

// The crosshair: four thin short bars around the centre of the view, always on, grey and mostly transparent (SessionConfig.crosshairAlpha) while nothing is aimed at,
// in the selection colour (and a little larger, and clearer) when it is on a bush that can be harvested, larger still while one is being harvested. Built in code by
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
    private Image[] _bars;
    private Color _current;

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
        crosshair._current = Idle(config);
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
        crosshair._bars = new Image[4];
        Vector2[] directions = { Vector2.up, Vector2.down, Vector2.left, Vector2.right };
        for (int i = 0; i < 4; i++)
        {
            bool vertical = directions[i].y != 0f;
            Vector2 size = vertical ? new Vector2(BarThickness, BarLength) : new Vector2(BarLength, BarThickness);
            Image outline = NewBar(crosshair._root, directions[i], size + Vector2.one * (2f * Outline), new Color(0f, 0f, 0f, 0.5f * config.CrosshairAlpha));
            crosshair._bars[i] = NewBar(crosshair._root, directions[i], size, Idle(config));
            outline.transform.SetAsFirstSibling();
        }

        return crosshair;
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
        }

        if (!live)
        {
            return;
        }

        bool aimed = _harvest != null && _harvest.FocusTreeId >= 0;
        bool harvesting = _harvest != null && _harvest.IsHarvesting;
        Color selected = _config.RimSelectedColor;
        Color target = aimed ? new Color(selected.r, selected.g, selected.b, Mathf.Max(_config.CrosshairAlpha, 0.85f)) : Idle(_config);
        _current = Color.Lerp(_current, target, 1f - Mathf.Exp(-20f * Time.unscaledDeltaTime));
        foreach (Image bar in _bars)
        {
            bar.color = _current;
        }

        float scale = harvesting ? 1.4f : (aimed ? 1.2f : 1f);
        _root.localScale = Vector3.Lerp(_root.localScale, Vector3.one * scale, 1f - Mathf.Exp(-20f * Time.unscaledDeltaTime));
    }
}
