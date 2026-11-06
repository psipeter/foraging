using TMPro;
using UnityEngine;
using UnityEngine.UI;

// A line of hint text on a rounded pill at the bottom of the screen ("Hold Space to harvest", the controls reminder): the pill is as wide as its text, [Key] becomes a
// key chip. Used instead of loose text so the hints read against any part of the world.
public class HintPill : MonoBehaviour
{
    private RectTransform _pill;
    private TextMeshProUGUI _label;

    // `y` is the pill's centre above the bottom edge, in reference pixels.
    public static HintPill Create(Transform parent, string name, float y, float opacity = 0.62f)
    {
        var go = new GameObject(name, typeof(RectTransform));
        go.transform.SetParent(parent, false);
        var hint = go.AddComponent<HintPill>();
        Image background = UiStyle.Rounded(go.transform, "Pill", new Color(0.06f, 0.067f, 0.09f, opacity), 0f, 0f, 400f, 60f, 30f);
        background.raycastTarget = false;
        hint._pill = background.rectTransform;
        hint._label = UiStyle.Text(background.transform, "Text", "", 30f, TextAlignmentOptions.Center, 0f, 0f, 400f, 60f, UiStyle.Ink);
        hint._label.richText = true;
        hint._label.raycastTarget = false;
        var rect = go.GetComponent<RectTransform>();
        rect.anchorMin = rect.anchorMax = new Vector2(0.5f, 0f);
        rect.pivot = new Vector2(0.5f, 0.5f);
        rect.anchoredPosition = new Vector2(0f, y);
        rect.sizeDelta = new Vector2(400f, 60f);
        go.SetActive(false);
        return hint;
    }

    public void Show(string text)
    {
        string rich = UiStyle.Chips(text);
        _label.text = rich;
        float width = _label.GetPreferredValues(rich, 1700f, 0f).x + 72f;
        UiStyle.Place(_pill, 0f, 0f, width, 60f);
        UiStyle.Place(_label.rectTransform, 0f, 0f, width, 60f);
        gameObject.SetActive(true);
    }

    public void Hide()
    {
        gameObject.SetActive(false);
    }
}
