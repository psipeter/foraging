using TMPro;
using UnityEngine;
using UnityEngine.UI;

// The plain screen of the Boot scene: a panel over the backdrop with a small accent line, a title, a sentence and, while something loads, a progress bar.
// Loading, connecting, "click anywhere to begin" and the errors all use it, so they look alike.
public class StatusScreen : MonoBehaviour
{
    private TextMeshProUGUI _eyebrow, _title, _body, _percent;
    private RectTransform _barFill;
    private GameObject _bar;
    private GameObject _root;

    public static StatusScreen Show()
    {
        Canvas canvas = UiStyle.Canvas("StatusScreen", null, 100);
        var screen = canvas.gameObject.AddComponent<StatusScreen>();
        screen.Build(canvas.transform);
        return screen;
    }

    private void Build(Transform canvas)
    {
        _root = canvas.gameObject;
        UiStyle.Backdrop(canvas);
        Transform panel = UiStyle.Rounded(canvas, "Panel", UiStyle.Glass, 0f, 0f, 980f, 560f, UiStyle.PanelRadius).transform;
        _eyebrow = UiStyle.Eyebrow(panel, "", 0f, 190f, 820f, TextAlignmentOptions.Center);
        _title = UiStyle.Text(panel, "Title", "", 60f, TextAlignmentOptions.Center, 0f, 110f, 860f, 80f);
        _body = UiStyle.Text(panel, "Body", "", UiStyle.Body, TextAlignmentOptions.Top, 0f, -20f, 820f, 190f, UiStyle.Ink);
        _body.textWrappingMode = TextWrappingModes.Normal;
        _bar = UiStyle.Rounded(panel, "Bar", new Color(1f, 1f, 1f, 0.14f), 0f, -150f, 720f, 14f, 7f).gameObject;
        _barFill = UiStyle.Rounded(_bar.transform, "Fill", UiStyle.Accent, 0f, 0f, 720f, 14f, 7f).rectTransform;
        _percent = UiStyle.Text(panel, "Percent", "", UiStyle.Small, TextAlignmentOptions.Center, 0f, -200f, 400f, 40f, UiStyle.Muted);
    }

    // `progress` 0 to 1 shows the bar; a negative value hides it. Rich text in `body` works ([Key] chips are the caller's business).
    public void Set(string eyebrow, string title, string body = "", float progress = -1f)
    {
        _root.SetActive(true);
        _eyebrow.text = eyebrow.ToUpperInvariant();
        _title.text = title;
        _body.text = body;
        _bar.SetActive(progress >= 0f);
        _percent.gameObject.SetActive(progress >= 0f);
        if (progress >= 0f)
        {
            float p = Mathf.Clamp01(progress);
            UiStyle.Place(_barFill, -(720f * (1f - p)) / 2f, 0f, Mathf.Max(720f * p, 14f), 14f);
            _percent.text = $"{Mathf.RoundToInt(p * 100f)}%";
        }
    }

    public void Hide()
    {
        _root.SetActive(false);
    }
}
