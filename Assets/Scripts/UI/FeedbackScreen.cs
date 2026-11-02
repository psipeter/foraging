using System;
using TMPro;
using UnityEngine;
using UnityEngine.UI;

// The optional box for free-text feedback on a browser's final screen, drawn on the data gate's canvas below the completion code, with
// a button that returns the participant to Prolific when there is somewhere to return to. It only collects the text: the caller
// (DataPipeline) sends it and reports back through SetStatus. The mouse is released for it (PointerLockGuard.Suspended).
public class FeedbackScreen : MonoBehaviour
{
    public const int MaxLength = 5000;       // the server's limit (supabase/functions/_shared/handlers.ts)

    private TMP_InputField _input;
    private Button _send;
    private TextMeshProUGUI _status;
    private Action<string> _onSend;

    public static FeedbackScreen Show(Transform canvas, TextMeshProUGUI message, bool withReturn, Action<string> onSend, Action onReturn)
    {
        var screen = new GameObject("Feedback", typeof(RectTransform)).AddComponent<FeedbackScreen>();
        screen.transform.SetParent(canvas, false);
        UiStyle.SetAnchors((RectTransform)screen.transform, Vector2.zero, Vector2.one, Vector2.zero, Vector2.zero);
        screen.Build(message, withReturn, onSend, onReturn);
        return screen;
    }

    public void SetStatus(string text, bool sending)
    {
        _status.text = text;
        _send.interactable = !sending;
    }

    private void Build(TextMeshProUGUI message, bool withReturn, Action<string> onSend, Action onReturn)
    {
        _onSend = onSend;
        UiStyle.SetAnchors(message.rectTransform, new Vector2(0.2f, 0.55f), new Vector2(0.8f, 0.92f), Vector2.zero, Vector2.zero);
        UiStyle.Label(transform, "Prompt", "Optional: tell us what you thought of the game.", UiStyle.Small, TextAlignmentOptions.BottomLeft,
            new Vector2(0.2f, 0.47f), new Vector2(0.8f, 0.53f), UiStyle.Muted);

        Image background = UiStyle.Image(transform, "Box", UiStyle.Field, new Vector2(0.2f, 0.2f), new Vector2(0.8f, 0.46f), Vector2.zero, Vector2.zero);
        var area = new GameObject("Text Area", typeof(RectTransform), typeof(RectMask2D));
        area.transform.SetParent(background.transform, false);
        var areaRect = area.GetComponent<RectTransform>();
        UiStyle.SetAnchors(areaRect, Vector2.zero, Vector2.one, new Vector2(16f, 8f), new Vector2(-16f, -8f));
        TextMeshProUGUI shown = UiStyle.Label(area.transform, "Text", "", UiStyle.Body * 0.85f, TextAlignmentOptions.TopLeft, Vector2.zero, Vector2.one);
        _input = background.gameObject.AddComponent<TMP_InputField>();
        _input.textViewport = areaRect;
        _input.textComponent = shown;
        _input.targetGraphic = background;
        _input.lineType = TMP_InputField.LineType.MultiLineNewline;
        _input.characterLimit = MaxLength;

        _send = Button(background.transform.parent, "Send", "Send", new Vector2(0.64f, 0.11f), new Vector2(0.8f, 0.18f), Send);
        _status = UiStyle.Label(transform, "Status", "", UiStyle.Small, TextAlignmentOptions.MidlineLeft,
            new Vector2(0.2f, 0.11f), new Vector2(0.62f, 0.18f), UiStyle.Muted);
        if (withReturn)
        {
            Button(transform, "Return", "Return to Prolific", new Vector2(0.38f, 0.02f), new Vector2(0.62f, 0.09f), () => onReturn());
        }

        _input.ActivateInputField();
    }

    private void Send()
    {
        string text = _input.text.Trim();
        if (text.Length == 0)
        {
            SetStatus("Type something first.", false);
            return;
        }

        SetStatus("Sending...", true);
        _onSend(text);
    }

    private static Button Button(Transform parent, string name, string caption, Vector2 min, Vector2 max, UnityEngine.Events.UnityAction onClick)
    {
        Image background = UiStyle.Image(parent, name, UiStyle.Accent, min, max, Vector2.zero, Vector2.zero);
        UiStyle.Label(background.transform, "Text", caption, UiStyle.Small, TextAlignmentOptions.Center, Vector2.zero, Vector2.one, UiStyle.Panel);
        var button = background.gameObject.AddComponent<Button>();
        button.targetGraphic = background;
        ColorBlock colors = button.colors;
        colors.disabledColor = new Color(0.35f, 0.4f, 0.48f, 0.6f);
        button.colors = colors;
        button.onClick.AddListener(onClick);
        return button;
    }
}
