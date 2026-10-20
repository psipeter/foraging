using UnityEngine;
using UnityEngine.UI;

// Small runtime-built HUD pieces (plain rectangles), so the scene needs no extra authored objects.
public static class HudWidgets
{
    // A translucent plate behind `text`, same anchors and position, drawn just behind it.
    public static RectTransform CreatePlate(RectTransform text, Vector2 size, Color color, string name)
    {
        var go = new GameObject(name, typeof(RectTransform), typeof(Image));
        var rect = go.GetComponent<RectTransform>();
        rect.SetParent(text.parent, false);
        rect.anchorMin = text.anchorMin;
        rect.anchorMax = text.anchorMax;
        rect.pivot = text.pivot;
        rect.anchoredPosition = text.anchoredPosition;
        rect.sizeDelta = size;
        rect.SetSiblingIndex(text.GetSiblingIndex());

        Image image = go.GetComponent<Image>();
        image.color = color;
        image.raycastTarget = false;
        return rect;
    }
}
