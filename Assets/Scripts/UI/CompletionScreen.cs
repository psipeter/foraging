using System;
using TMPro;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.InputSystem.UI;
using UnityEngine.UI;

// The screen at the end of an experiment, and when a finished one is opened from the menu: its title, the points earned (for an experiment that counts), the
// completion code, an optional box for free-text feedback and the way on (back to the menu and, for a participant who came from Prolific, back to Prolific).
// It only collects the feedback text: the caller sends it and reports back through SetStatus. The mouse is released for it (PointerLockGuard.Suspended).
public class CompletionScreen : MonoBehaviour
{
    public const int MaxLength = 5000;       // the server's limit (supabase/functions/_shared/handlers.ts)

    private TMP_InputField _input;
    private Button _send;
    private TextMeshProUGUI _status;
    private Action<string> _onSend;

    public static CompletionScreen Show(string title, float? points, string code, bool fromProlific, Action<string> onSend, Action onProlific, Action onMenu)
    {
        Canvas canvas = UiStyle.Canvas("CompletionScreen", null, 5500);
        canvas.gameObject.AddComponent<GraphicRaycaster>();
        if (FindAnyObjectByType<EventSystem>() == null)
        {
            new GameObject("EventSystem", typeof(EventSystem), typeof(InputSystemUIInputModule));
        }

        PointerLockGuard.Suspended = true;
        var screen = canvas.gameObject.AddComponent<CompletionScreen>();
        screen.Build(title, points, code, fromProlific, onSend, onProlific, onMenu);
        return screen;
    }

    public void SetStatus(string text, bool sending)
    {
        _status.text = text;
        _send.interactable = !sending;
    }

    private void Build(string title, float? points, string code, bool fromProlific, Action<string> onSend, Action onProlific, Action onMenu)
    {
        _onSend = onSend;
        UiStyle.Backdrop(transform);
        Transform panel = UiStyle.Rounded(transform, "Panel", UiStyle.Glass, 0f, 0f, 1300f, 840f, UiStyle.PanelRadius).transform;
        UiStyle.Eyebrow(panel, "Experiment complete", 0f, 342f, 1180f);
        UiStyle.Text(panel, "Title", title, 60f, TextAlignmentOptions.Left, 0f, 270f, 1180f, 80f);

        float codeX = points.HasValue ? 300f : 0f;
        if (points.HasValue)
        {
            UiStyle.Text(panel, "PointsLabel", "Points earned", UiStyle.Small, TextAlignmentOptions.Left, -300f, 178f, 560f, 36f, UiStyle.Muted);
            UiStyle.Text(panel, "Points", $"{points.Value:F0}", 76f, TextAlignmentOptions.Left, -300f, 110f, 560f, 90f);
        }

        UiStyle.Text(panel, "CodeLabel", "Your completion code", UiStyle.Small, TextAlignmentOptions.Left, codeX, 178f, 560f, 36f, UiStyle.Muted);
        Transform codeBox = UiStyle.Rounded(panel, "CodeBox", UiStyle.FieldGlass, codeX, 112f, 560f, 88f, 18f).transform;
        UiStyle.Text(codeBox, "Code", code ?? "", 48f, TextAlignmentOptions.Center, 0f, 0f, 540f, 80f).characterSpacing = 3f;

        UiStyle.Text(panel, "Prompt", "Optional: tell us what you thought of the game", UiStyle.Small, TextAlignmentOptions.Left, 0f, 20f, 1180f, 36f, UiStyle.Muted);
        Image box = UiStyle.Rounded(panel, "Box", UiStyle.FieldGlass, 0f, -80f, 1180f, 150f, 16f);
        var area = new GameObject("Text Area", typeof(RectTransform), typeof(RectMask2D));
        area.transform.SetParent(box.transform, false);
        var areaRect = area.GetComponent<RectTransform>();
        UiStyle.SetAnchors(areaRect, Vector2.zero, Vector2.one, new Vector2(24f, 14f), new Vector2(-24f, -14f));
        TextMeshProUGUI shown = UiStyle.Label(area.transform, "Text", "", UiStyle.Small + 4f, TextAlignmentOptions.TopLeft, Vector2.zero, Vector2.one);
        _input = box.gameObject.AddComponent<TMP_InputField>();
        _input.textViewport = areaRect;
        _input.textComponent = shown;
        _input.targetGraphic = box;
        _input.lineType = TMP_InputField.LineType.MultiLineNewline;
        _input.characterLimit = MaxLength;
        UiStyle.StyleInput(_input, box);

        _status = UiStyle.Text(panel, "Status", "", UiStyle.Small, TextAlignmentOptions.Left, -290f, -196f, 600f, 36f, UiStyle.Muted);

        // buttons from the right edge inwards
        float right = 594f;
        Button Add(string name, string caption, float width, bool ghost, UnityEngine.Events.UnityAction click)
        {
            Button button = UiStyle.Pill(panel, name, caption, right - width / 2f, -300f, width, click, ghost, 68f);
            right -= width + 20f;
            return button;
        }

        Add("Menu", "Back to the menu", 300f, false, () => onMenu());
        if (fromProlific)
        {
            Add("Prolific", "Return to Prolific", 300f, true, () => onProlific());
        }

        _send = Add("Send", "Send feedback", 270f, true, Send);
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
}
