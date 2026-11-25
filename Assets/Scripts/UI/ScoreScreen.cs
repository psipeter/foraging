using System.Collections;
using TMPro;
using UnityEngine;

// The screen at the end of a session: "Session 3 of 4", the points of that session very large in a panel, and under a rule the prompt
// as the last line of the panel. The world stays behind it and the camera turns slowly, so it is not a still frame. The music (UI/Music.cs) starts with it. Built at runtime.
public class ScoreScreen : MonoBehaviour
{
    private const float DegreesPerSecond = 3.5f;


    private TextMeshProUGUI _total, _selection, _foragingText;
    private float _foraging, _selectionPoints;
    private CanvasGroup _scrimGroup, _panelGroup;
    private RectTransform _panelRect;
    private Vector2 _panelHome;

    // `foraging` and `selection` are the two parts of the session's points. With `split` (a session that has selections) the total is shown in the middle with the two parts
    // smaller on either side, and after a moment the three count up together from zero (the selection points stay hidden until now). `config` (optional) supplies the captions under
    // the foraging and the selection points and a note centred under the total (SessionConfig.scoreCaption*, scoreNote).
    public static ScoreScreen Show(string partLabel, float foraging, float selection, bool split, string prompt, CameraController camera, SessionConfig config = null)
    {
        Canvas canvas = UiStyle.Canvas("ScoreScreen", null, 4100);
        var screen = canvas.gameObject.AddComponent<ScoreScreen>();
        screen.Build(canvas.transform, partLabel, foraging, selection, split, prompt, config);
        screen.StartCoroutine(screen.Appear());
        if (camera != null)
        {
            screen.StartCoroutine(screen.Drift(camera));
        }

        if (split)
        {
            screen.StartCoroutine(screen.CountUp());
        }

        return screen;
    }

    private void Build(Transform canvas, string partLabel, float foraging, float selection, bool split, string prompt, SessionConfig config)
    {
        _foraging = foraging;
        _selectionPoints = selection;
        string note = split && config != null ? config.ScoreNote : "";
        // Every item is placed from the panel's top edge (the top stays put) or, for the prompt, from its bottom edge, so a note only makes the panel taller.
        float ruleFromTop = note.Length > 0 ? 435f : 335f;
        float height = ruleFromTop + 170f;
        float top = height / 2f;
        _scrimGroup = UiStyle.Image(canvas, "Scrim", new Color(0.04f, 0.05f, 0.07f, 0.34f), Vector2.zero, Vector2.one, Vector2.zero, Vector2.zero).gameObject.AddComponent<CanvasGroup>();
        _scrimGroup.blocksRaycasts = false;
        _panelHome = new Vector2(0f, 330f - top);
        Transform panel = UiStyle.Rounded(canvas, "Panel", UiStyle.Glass, _panelHome.x, _panelHome.y, 900f, height, UiStyle.PanelRadius).transform;
        _panelRect = (RectTransform)panel;
        _panelGroup = panel.gameObject.AddComponent<CanvasGroup>();
        UiStyle.Eyebrow(panel, $"{partLabel} complete", 0f, top - 58f, 780f, TextAlignmentOptions.Center);
        _total = UiStyle.Text(panel, "Points", split ? "0" : $"{foraging + selection:F0}", split ? 190f : 230f, TextAlignmentOptions.Center, 0f, top - 220f, split ? 460f : 780f, 260f);
        _total.font = UiStyle.DisplayFont;
        if (split)
        {
            const float sideX = 335f;
            UiStyle.Eyebrow(panel, "foraging", -sideX, top - 170f, 170f, TextAlignmentOptions.Center).color = UiStyle.ForagingTint;
            _foragingText = UiStyle.Text(panel, "Foraging", "0", 66f, TextAlignmentOptions.Center, -sideX, top - 230f, 170f, 100f, UiStyle.Muted);
            _foragingText.font = UiStyle.DisplayFont;
            UiStyle.Eyebrow(panel, "selection", sideX, top - 170f, 170f, TextAlignmentOptions.Center).color = UiStyle.SelectionTint;
            _selection = UiStyle.Text(panel, "Selection", "0", 66f, TextAlignmentOptions.Center, sideX, top - 230f, 170f, 100f, UiStyle.Muted);
            _selection.font = UiStyle.DisplayFont;
            Caption(panel, config != null ? config.ScoreCaptionForaging : "", -sideX, top - 320f, 190f, 90f);
            Caption(panel, config != null ? config.ScoreCaptionSelection : "", sideX, top - 320f, 190f, 90f);
        }

        if (note.Length > 0)
        {
            TextMeshProUGUI noteText = UiStyle.Text(panel, "Note", UiStyle.Chips(note), 28f, TextAlignmentOptions.Center, 0f, top - 375f, 780f, 44f, UiStyle.Ink);
            noteText.richText = true;
        }

        UiStyle.Rounded(panel, "Rule", new Color(1f, 1f, 1f, 0.16f), 0f, top - ruleFromTop, 780f, 2f, 1f);
        TextMeshProUGUI promptText = UiStyle.Text(panel, "Prompt", UiStyle.Chips(prompt), 34f, TextAlignmentOptions.Center, 0f, 98f - top, 780f, 56f, UiStyle.Ink);
        promptText.richText = true;
    }

    // The scrim and panel fade in while the panel rises and grows a little, as an instruction popup does.
    private IEnumerator Appear()
    {
        for (float t = 0f; t < InstructionsScreen.FadeIn; t += Time.unscaledDeltaTime)
        {
            InstructionsScreen.Enter(_scrimGroup, _panelGroup, _panelRect, _panelHome, t);
            yield return null;
        }

        InstructionsScreen.Enter(_scrimGroup, _panelGroup, _panelRect, _panelHome, InstructionsScreen.FadeIn);
    }

    private static void Caption(Transform panel, string text, float x, float y, float w, float h)
    {
        if (text.Length == 0)
        {
            return;
        }

        TextMeshProUGUI caption = UiStyle.Text(panel, "Caption", UiStyle.Chips(text), 22f, TextAlignmentOptions.Top, x, y, w, h, UiStyle.Muted);
        caption.richText = true;
        caption.textWrappingMode = TextWrappingModes.Normal;
    }

    // The foraging points, the selection points and the total count up together from zero (ease-out); the total punches when they land.
    private IEnumerator CountUp()
    {
        const float delay = 0.8f, seconds = 1.4f;
        yield return new WaitForSecondsRealtime(delay);
        float elapsed = 0f;
        while (elapsed < seconds)
        {
            elapsed += Time.unscaledDeltaTime;
            float t = Mathf.Clamp01(elapsed / seconds);
            float eased = 1f - (1f - t) * (1f - t) * (1f - t);
            SetNumbers(eased);
            yield return null;
        }

        SetNumbers(1f);
        RectTransform rect = _total.rectTransform;
        for (float e = 0f; e < 0.25f; e += Time.unscaledDeltaTime)
        {
            rect.localScale = Vector3.one * Mathf.Lerp(1.12f, 1f, e / 0.25f);
            yield return null;
        }

        rect.localScale = Vector3.one;
    }

    private void SetNumbers(float fraction)
    {
        _foragingText.text = $"{_foraging * fraction:F0}";
        _selection.text = $"{_selectionPoints * fraction:F0}";
        _total.text = $"{(_foraging + _selectionPoints) * fraction:F0}";
    }

    private IEnumerator Drift(CameraController camera)
    {
        float yaw = camera.Yaw;
        float pitch = camera.Pitch;
        while (true)
        {
            yaw += DegreesPerSecond * Time.unscaledDeltaTime;
            camera.SetView(yaw, pitch);
            yield return null;
        }
    }
}
