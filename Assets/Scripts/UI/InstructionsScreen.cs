using System.Collections;
using System.Collections.Generic;
using TMPro;
using UnityEngine;

// The instruction screen of a part (and the "welcome back" screen): a wide panel centred on the screen (all its text centred) with the part number, the instruction as a title, the
// text, and under a rule the prompt ("Press Enter to begin") as the last line of the text, over the world. Built at runtime; [Key] in
// the text becomes a key chip.
public class InstructionsScreen : MonoBehaviour
{
    private const float PanelWidth = 1640f;
    private const float BodySize = 36f;

    public const float FadeIn = 0.25f;              // the entrance of a screen (ScoreScreen uses it too, through Enter)
    private const float StartScale = 0.96f, Rise = 20f, FadeOut = 0.2f, Stagger = 0.08f, EndScale = 0.97f;

    public static event System.Action OnOpened;          // a screen starts to appear (FeedbackAudio plays its soft cue)

    private GameObject _root;
    private bool _shown;
    private Coroutine _animation;
    private CanvasGroup _scrimGroup, _panelGroup;
    private RectTransform _panelRect;
    private Vector2 _panelHome;
    private readonly List<KeyValuePair<CanvasGroup, float>> _parts = new List<KeyValuePair<CanvasGroup, float>>();       // the text pieces and when each starts to appear

    // False as soon as Hide is called (the screen is still fading out), so a caller can hand the game back and show the next screen at once.
    public bool Visible => _shown;

    public static InstructionsScreen Create(Transform parent = null, int sortingOrder = 4000)
    {
        Canvas canvas = UiStyle.Canvas("InstructionsScreen", parent, sortingOrder);
        var screen = canvas.gameObject.AddComponent<InstructionsScreen>();
        screen._root = canvas.gameObject;
        canvas.gameObject.SetActive(false);
        return screen;
    }

    // Every instruction page, hint and notice is centred (PI, 2026-11-16): the label, the title in the display font, the text and the prompt.
    public void Show(string eyebrow, string title, string body, string prompt)
    {
        if (_animation != null)
        {
            StopCoroutine(_animation);
        }

        foreach (Transform child in _root.transform)
        {
            Destroy(child.gameObject);
        }

        _root.SetActive(true);
        _shown = true;
        _parts.Clear();
        _scrimGroup = UiStyle.Image(_root.transform, "Scrim", new Color(0.04f, 0.05f, 0.07f, 0.34f), Vector2.zero, Vector2.one, Vector2.zero, Vector2.zero).gameObject.AddComponent<CanvasGroup>();
        _scrimGroup.blocksRaycasts = false;

        const float pad = 56f;
        float textWidth = PanelWidth - 2f * pad;
        const TextAlignmentOptions align = TextAlignmentOptions.Center;
        const TextAlignmentOptions bodyAlign = TextAlignmentOptions.Top;
        float titleSize = UiStyle.Heading;
        float titleHeight = 64f;
        TextMeshProUGUI titleMeasure = UiStyle.Text(_root.transform, "TitleMeasure", title, titleSize, align, 0f, 0f, textWidth, 100f);
        titleMeasure.textWrappingMode = TextWrappingModes.Normal;
        titleHeight = Mathf.Max(titleHeight, titleMeasure.GetPreferredValues(title, textWidth, 0f).y + 14f);       // a title of two or more lines gets the room
        Destroy(titleMeasure.gameObject);
        body = UiStyle.Chips(body.Trim());
        TextMeshProUGUI measure = UiStyle.Text(_root.transform, "Measure", body, BodySize, bodyAlign, 0f, 0f, textWidth, 100f, UiStyle.Ink);
        measure.richText = true;
        measure.textWrappingMode = TextWrappingModes.Normal;
        measure.lineSpacing = 8f;
        float bodyHeight = measure.GetPreferredValues(body, textWidth, 0f).y + 12f;
        Destroy(measure.gameObject);

        // eyebrow, title, text, a rule, the prompt
        float eyebrowHeight = string.IsNullOrEmpty(eyebrow) ? 0f : 36f + 20f;
        if (string.IsNullOrEmpty(body)) bodyHeight = 0f;
        float height = pad * 2f + eyebrowHeight + titleHeight + 20f + bodyHeight + 28f + 2f + 28f + 48f;
        Transform panel = UiStyle.Rounded(_root.transform, "Panel", UiStyle.Glass, 0f, 0f, PanelWidth, height, UiStyle.PanelRadius).transform;
        _panelRect = (RectTransform)panel;
        _panelHome = _panelRect.anchoredPosition;
        _panelGroup = panel.gameObject.AddComponent<CanvasGroup>();
        float y = height / 2f - pad;
        if (!string.IsNullOrEmpty(eyebrow))
        {
            Part(UiStyle.Eyebrow(panel, eyebrow, 0f, y - 18f, textWidth, TextAlignmentOptions.Center), 0f);
        }

        y -= eyebrowHeight;
        TextMeshProUGUI titleText = UiStyle.Text(panel, "Title", title, titleSize, align, 0f, y - titleHeight / 2f, textWidth, titleHeight);
        titleText.font = UiStyle.DisplayFont;
        Part(titleText, 0f);
        y -= titleHeight + 20f;
        TextMeshProUGUI text = UiStyle.Text(panel, "Body", body, BodySize, bodyAlign, 0f, y - bodyHeight / 2f, textWidth, bodyHeight, UiStyle.Ink);
        text.richText = true;
        text.textWrappingMode = TextWrappingModes.Normal;
        text.lineSpacing = 8f;
        Part(text, Stagger);
        y -= bodyHeight + 28f;
        Part(UiStyle.Rounded(panel, "Rule", new Color(1f, 1f, 1f, 0.16f), 0f, y, textWidth, 2f, 1f), 2f * Stagger);
        y -= 2f + 28f;
        TextMeshProUGUI promptText = UiStyle.Text(panel, "Prompt", UiStyle.Chips(prompt), 34f, TextAlignmentOptions.Midline, 0f, y - 24f, textWidth, 48f, UiStyle.Ink);
        promptText.richText = true;
        Part(promptText, 2f * Stagger);
        _animation = StartCoroutine(Appear());
        OnOpened?.Invoke();
    }

    private void Part(Component piece, float delay)
    {
        _parts.Add(new KeyValuePair<CanvasGroup, float>(piece.gameObject.AddComponent<CanvasGroup>(), delay));
    }

    // The scrim and panel fade in while the panel rises and grows a little; the title comes first, then the text, then the rule and the prompt. Real time: the game is held still behind it.
    private IEnumerator Appear()
    {
        float last = 2f * Stagger + FadeIn;
        for (float t = 0f; t < last; t += Time.unscaledDeltaTime)
        {
            Enter(_scrimGroup, _panelGroup, _panelRect, _panelHome, t);
            foreach (KeyValuePair<CanvasGroup, float> part in _parts)
            {
                part.Key.alpha = Ease((t - part.Value) / FadeIn);
            }

            yield return null;
        }

        Enter(_scrimGroup, _panelGroup, _panelRect, _panelHome, FadeIn);
        foreach (KeyValuePair<CanvasGroup, float> part in _parts)
        {
            part.Key.alpha = 1f;
        }
    }

    // The pose of a screen `t` seconds into its entrance (final from FadeIn on): the scrim and panel fade in while the panel rises and grows a little.
    public static void Enter(CanvasGroup scrim, CanvasGroup panel, RectTransform panelRect, Vector2 home, float t)
    {
        float whole = Ease(t / FadeIn);
        scrim.alpha = panel.alpha = whole;
        panelRect.localScale = Vector3.one * Mathf.Lerp(StartScale, 1f, whole);
        panelRect.anchoredPosition = home + Vector2.down * Rise * (1f - whole);
    }

    private static float Ease(float t)
    {
        t = Mathf.Clamp01(t);
        return 1f - (1f - t) * (1f - t);
    }

    // The screen fades out over a fifth of a second; the caller has the game back from this call on.
    public void Hide()
    {
        if (!_shown)
        {
            return;
        }

        _shown = false;
        if (_animation != null)
        {
            StopCoroutine(_animation);
        }

        _animation = StartCoroutine(Disappear());
    }

    private IEnumerator Disappear()
    {
        float from = _panelGroup.alpha;
        for (float t = 0f; t < FadeOut; t += Time.unscaledDeltaTime)
        {
            float k = Ease(t / FadeOut);
            _scrimGroup.alpha = _panelGroup.alpha = from * (1f - k);
            _panelRect.localScale = Vector3.one * Mathf.Lerp(1f, EndScale, k);
            yield return null;
        }

        _root.SetActive(false);
    }
}
