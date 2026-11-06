using System;
using System.Text.RegularExpressions;
using TMPro;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.InputSystem.UI;
using UnityEngine.UI;

// What a participant agreed to: the consent text's version line, the name they typed, and when (their clock, UTC, ISO 8601).
[Serializable]
public class ConsentRecord
{
    public string version;
    public string signature;
    public string at;
}

// The opening screens of an online build, both built at runtime like the other overlays. The ID screen asks for the participant's Prolific ID (filled in
// and locked when the page address carries one) or name; the server then says whether it holds a consent of the current version for that ID. If not, the
// consent screen shows the text (StreamingAssets/consent.txt: a first line "version: <id>", then the title and the text) and asks for a typed signature,
// which counts as agreement. A returning participant who has signed this version is not asked again.
public class ConsentScreen : MonoBehaviour
{
    public const string File = "consent.txt";

    // Mirror of PID in supabase/functions/_shared/handlers.ts.
    private static readonly Regex IdPattern = new Regex("^[A-Za-z0-9_-]{1,64}$");

    public bool Done { get; private set; }
    public string ParticipantId { get; private set; }
    public ConsentRecord Consent { get; private set; }

    private TMP_InputField _id;
    private TMP_InputField _signature;
    private Button _continue;
    private TextMeshProUGUI _problem;
    private string _version = "unversioned";

    // The version line of the consent text ("unversioned" when the file has none or is missing).
    public static string ReadVersion()
    {
        ParseText(out string version, out _, out _);
        return version;
    }

    public static ConsentScreen ShowId(string presetId, string problem = null)
    {
        ConsentScreen screen = Create();
        screen.BuildId(presetId, problem);
        return screen;
    }

    public static ConsentScreen ShowConsent()
    {
        ConsentScreen screen = Create();
        screen.BuildConsent();
        return screen;
    }

    private static ConsentScreen Create()
    {
        Canvas canvas = UiStyle.Canvas("ConsentScreen", null, 6000);
        canvas.gameObject.AddComponent<GraphicRaycaster>();
        if (FindAnyObjectByType<EventSystem>() == null)
        {
            new GameObject("EventSystem", typeof(EventSystem), typeof(InputSystemUIInputModule));
        }

        return canvas.gameObject.AddComponent<ConsentScreen>();
    }

    private static void ParseText(out string version, out string title, out string body)
    {
        version = "unversioned";
        title = "Consent to participate";
        body = "Consent text not found (StreamingAssets/" + File + ").";
        if (!StreamingData.Exists(File))
        {
            return;
        }

        string[] lines = StreamingData.ReadText(File).Replace("\r", "").Split('\n');
        int first = 0;
        if (lines.Length > 0 && lines[0].StartsWith("version:", StringComparison.OrdinalIgnoreCase))
        {
            version = lines[0].Substring(8).Trim();
            first = 1;
        }

        if (lines.Length > first + 1)
        {
            title = lines[first].Trim();
            body = string.Join("\n", lines, first + 1, lines.Length - first - 1).Trim();
        }
    }

    private void BuildId(string presetId, string problem)
    {
        UiStyle.Image(transform, "Background", UiStyle.Panel, Vector2.zero, Vector2.one, Vector2.zero, Vector2.zero);
        UiStyle.Label(transform, "Title", "Welcome", UiStyle.Title, TextAlignmentOptions.Left, new Vector2(0.1f, 0.78f), new Vector2(0.9f, 0.9f));
        UiStyle.Label(transform, "Intro", "Enter your Prolific ID to begin, or to continue where you stopped.", UiStyle.Body, TextAlignmentOptions.TopLeft,
            new Vector2(0.1f, 0.62f), new Vector2(0.9f, 0.76f), UiStyle.Muted);

        bool locked = !string.IsNullOrEmpty(presetId) && IdPattern.IsMatch(presetId);   // a malformed ID from the address can be corrected
        UiStyle.Label(transform, "IdLabel", locked ? "Your Prolific ID" : "Prolific ID or participant ID", UiStyle.Small, TextAlignmentOptions.Left,
            new Vector2(0.1f, 0.5f), new Vector2(0.6f, 0.56f), UiStyle.Muted);
        _id = Field("IdField", presetId ?? "", new Vector2(0.1f, 0.42f), new Vector2(0.6f, 0.5f));
        _id.characterLimit = 64;
        _id.interactable = !locked;
        _problem = UiStyle.Label(transform, "Problem", problem ?? "", UiStyle.Small, TextAlignmentOptions.Left, new Vector2(0.1f, 0.33f), new Vector2(0.9f, 0.4f),
            new Color(0.95f, 0.55f, 0.45f));
        _continue = ContinueButton(new Vector2(0.65f, 0.42f), new Vector2(0.9f, 0.5f), AcceptId);
        _id.onValueChanged.AddListener(_ => RefreshId());
        RefreshId(problem);
        _id.ActivateInputField();
    }

    private void RefreshId(string keepProblem = null)
    {
        string id = _id.text.Trim();
        bool idOk = IdPattern.IsMatch(id);
        if (keepProblem == null)
        {
            _problem.text = id.Length > 0 && !idOk ? "The ID may contain only letters, digits, - and _." : "";
        }

        _continue.interactable = idOk;
    }

    private void AcceptId()
    {
        ParticipantId = _id.text.Trim();
        Done = true;
        Destroy(gameObject);
    }

    private void BuildConsent()
    {
        ParseText(out _version, out string title, out string body);
        UiStyle.Image(transform, "Background", UiStyle.Panel, Vector2.zero, Vector2.one, Vector2.zero, Vector2.zero);
        UiStyle.Label(transform, "Title", title, UiStyle.Title, TextAlignmentOptions.Left, new Vector2(0.1f, 0.88f), new Vector2(0.9f, 0.97f));
        BuildScroll(body);
        UiStyle.Label(transform, "SignatureLabel", "Type your full name to sign. This means you have read this form and agree to take part.", UiStyle.Small,
            TextAlignmentOptions.Left, new Vector2(0.1f, 0.255f), new Vector2(0.9f, 0.295f), UiStyle.Muted);
        _signature = Field("SignatureField", "", new Vector2(0.1f, 0.19f), new Vector2(0.62f, 0.25f));
        _signature.characterLimit = 120;
        _continue = ContinueButton(new Vector2(0.7f, 0.19f), new Vector2(0.9f, 0.25f), AcceptConsent);
        _signature.onValueChanged.AddListener(_ => _continue.interactable = _signature.text.Trim().Length >= 2);
        _continue.interactable = false;
        _signature.ActivateInputField();
    }

    private void AcceptConsent()
    {
        Consent = new ConsentRecord { version = _version, signature = _signature.text.Trim(), at = DateTime.UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ", System.Globalization.CultureInfo.InvariantCulture) };
        Done = true;
        Destroy(gameObject);
    }

    private void BuildScroll(string body)
    {
        GameObject view = UiStyle.Image(transform, "ConsentText", UiStyle.Field, new Vector2(0.1f, 0.32f), new Vector2(0.9f, 0.86f), Vector2.zero, Vector2.zero).gameObject;
        view.AddComponent<RectMask2D>();
        var scroll = view.AddComponent<ScrollRect>();
        scroll.horizontal = false;
        scroll.movementType = ScrollRect.MovementType.Clamped;
        scroll.scrollSensitivity = 40f;

        var content = new GameObject("Content", typeof(RectTransform), typeof(ContentSizeFitter));
        content.transform.SetParent(view.transform, false);
        var rect = content.GetComponent<RectTransform>();
        rect.anchorMin = new Vector2(0f, 1f);
        rect.anchorMax = new Vector2(1f, 1f);
        rect.pivot = new Vector2(0.5f, 1f);
        rect.offsetMin = new Vector2(24f, 0f);
        rect.offsetMax = new Vector2(-24f, 0f);
        content.GetComponent<ContentSizeFitter>().verticalFit = ContentSizeFitter.FitMode.PreferredSize;
        var text = content.AddComponent<TextMeshProUGUI>();
        UiStyle.Apply(text, UiStyle.Body * 0.85f);
        text.color = UiStyle.Ink;
        text.text = body;
        text.margin = new Vector4(0f, 16f, 0f, 16f);
        scroll.content = rect;
        scroll.viewport = view.GetComponent<RectTransform>();
    }

    private TMP_InputField Field(string name, string text, Vector2 min, Vector2 max)
    {
        Image background = UiStyle.Image(transform, name, UiStyle.Field, min, max, Vector2.zero, Vector2.zero);
        var area = new GameObject("Text Area", typeof(RectTransform), typeof(RectMask2D));
        area.transform.SetParent(background.transform, false);
        var areaRect = area.GetComponent<RectTransform>();
        areaRect.anchorMin = Vector2.zero;
        areaRect.anchorMax = Vector2.one;
        areaRect.offsetMin = new Vector2(16f, 4f);
        areaRect.offsetMax = new Vector2(-16f, -4f);
        TextMeshProUGUI shown = UiStyle.Label(area.transform, "Text", "", UiStyle.Body, TextAlignmentOptions.MidlineLeft, Vector2.zero, Vector2.one);
        var input = background.gameObject.AddComponent<TMP_InputField>();
        input.textViewport = areaRect;
        input.textComponent = shown;
        input.targetGraphic = background;
        input.lineType = TMP_InputField.LineType.SingleLine;
        UiStyle.StyleInput(input, background);
        input.text = text;
        return input;
    }

    private Button ContinueButton(Vector2 min, Vector2 max, UnityEngine.Events.UnityAction onClick)
    {
        Image background = UiStyle.Image(transform, "Continue", UiStyle.Accent, min, max, Vector2.zero, Vector2.zero);
        UiStyle.Label(background.transform, "Text", "Continue", UiStyle.Body, TextAlignmentOptions.Center, Vector2.zero, Vector2.one, UiStyle.Panel);
        var button = background.gameObject.AddComponent<Button>();
        button.targetGraphic = background;
        ColorBlock colors = button.colors;
        colors.disabledColor = new Color(0.35f, 0.4f, 0.48f, 0.6f);
        button.colors = colors;
        button.onClick.AddListener(onClick);
        return button;
    }
}
