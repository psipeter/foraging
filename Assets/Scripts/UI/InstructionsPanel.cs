using System.IO;
using TMPro;
using UnityEngine;
using UnityEngine.InputSystem;

public class InstructionsPanel : MonoBehaviour
{
    private const string FallbackInstructions =
        "<i>Press Enter to begin.</i>\n\n" +
        "<size=125%><b>Welcome to the Foraging Task</b></size>\n\n" +
        "Your goal is to collect as many points as you can before time runs out.\n\n" +
        "Move the mouse to look around.\n" +
        "Press W to walk forward and S to walk backward.\n" +
        "Hold [Space] to harvest.";

    [SerializeField] private GameObject panel;
    [SerializeField] private TextMeshProUGUI bodyText;
    [SerializeField] private TextMeshProUGUI sessionLabel;

    private const string ContinuePrompt = "<i>Press Enter to continue.</i>\n\n";

    public SessionConfig sessionConfig;

    private bool _firstHarvestShown;
    private bool _sessionEnded;

    private void OnEnable()
    {
        HarvestManager.OnHarvestBoutEnded += HandleHarvestBoutEnded;
        SunController.OnSessionEnd += HandleSessionEnd;
    }

    private void OnDisable()
    {
        HarvestManager.OnHarvestBoutEnded -= HandleHarvestBoutEnded;
        SunController.OnSessionEnd -= HandleSessionEnd;
    }

    private void HandleSessionEnd()
    {
        _sessionEnded = true;
    }

    // One-time message after the first harvest that actually collected fruit (e.g. in practice).
    private void HandleHarvestBoutEnded(HarvestBout bout)
    {
        if (_firstHarvestShown || _sessionEnded || bout.endedBySession || sessionConfig == null || sessionConfig.IsInterlude ||
            string.IsNullOrEmpty(sessionConfig.FirstHarvestMessage) ||
            bout.fruitRewards.Count == 0 || panel == null || bodyText == null)
        {
            return;
        }

        _firstHarvestShown = true;
        ShowText(ContinuePrompt + sessionConfig.FirstHarvestMessage.Replace("{points}", bout.boutTotal.ToString("0")));
        panel.SetActive(true);
        PauseGate.Instructions = true;
    }

    private void Start()
    {
        if (sessionLabel != null)
        {
            sessionLabel.gameObject.SetActive(false);
        }

        if (bodyText != null)
        {
            bodyText.gameObject.SetActive(true);
            bodyText.richText = true;
            ShowText(LoadInstructions());
        }

        if (panel != null)
        {
            panel.SetActive(true);
        }

        PauseGate.Instructions = true;

        CreateControlsReminder();
    }

    // One centred block: the heading (the paragraph after the "Press Enter ..." one, bold), the text, then the prompt with Enter as a
    // key chip. The text files and the first-harvest message start with the prompt paragraph.
    private void ShowText(string text)
    {
        RectTransform rect = bodyText.rectTransform;
        rect.anchorMin = rect.anchorMax = rect.pivot = new Vector2(0.5f, 0.5f);
        rect.anchoredPosition = Vector2.zero;
        rect.sizeDelta = new Vector2(1500f, 700f);
        bodyText.alignment = TextAlignmentOptions.Center;
        bodyText.fontSize = UiStyle.Body;
        bodyText.textWrappingMode = TextWrappingModes.Normal;

        const string gap = "\n\n";
        string prompt = "";
        int cut = text.IndexOf(gap, System.StringComparison.Ordinal);
        if (text.StartsWith("<i>Press Enter") && cut > 0)
        {
            prompt = text.Substring(0, cut).Replace("<i>", "").Replace("</i>", "").TrimEnd('.').Replace("Press Enter", "Press " + UiStyle.Chip("Enter"));
            text = text.Substring(cut + gap.Length);
        }

        int split = text.IndexOf(gap, System.StringComparison.Ordinal);
        if (split > 0)
        {
            string heading = System.Text.RegularExpressions.Regex.Replace(text.Substring(0, split), "</?(size|b)[^>]*>", "");
            text = "<b>" + heading + "</b>" + text.Substring(split);
        }

        // [Key] in a text file becomes a key chip.
        text = System.Text.RegularExpressions.Regex.Replace(text, @"\[([^\]]+)\]", m => UiStyle.Chip(m.Groups[1].Value));
        bodyText.text = prompt.Length > 0 ? text.TrimEnd() + gap + prompt : text;
    }

    private string LoadInstructions()
    {
        string file = sessionConfig != null ? sessionConfig.InstructionsFile : "instructions.txt";
        if (ResumeInfo.MidSession(GameManager.CurrentSessionIndex))
        {
            file = "instructions_resume.txt";       // the participant is coming back to an interrupted session
        }
        string text = FallbackInstructions;
        try
        {
            if (StreamingData.Exists(file))
            {
                text = StreamingData.ReadText(file);
            }
        }
        catch (IOException)
        {
            text = FallbackInstructions;
        }

        int number = GameManager.ExperimentSessionNumber(GameManager.CurrentSessionIndex);
        return text
            .Replace("{session}", number.ToString())
            .Replace("{interlude}", GameManager.InterludeNumber(GameManager.CurrentSessionIndex).ToString())
            .Replace("{trial_seconds}", (sessionConfig != null ? sessionConfig.InterludeTrialSeconds : 0f).ToString("0"))
            .Replace("{total}", GameManager.ExperimentSessionCount.ToString());
    }

    // A faint controls hint kept on screen for the whole session (sessions that set one in their config).
    private void CreateControlsReminder()
    {
        if (sessionConfig == null || string.IsNullOrEmpty(sessionConfig.ControlsReminder) ||
            panel == null || bodyText == null)
        {
            return;
        }

        GameObject go = new GameObject("ControlsReminder", typeof(RectTransform));
        go.transform.SetParent(panel.transform.parent, false);
        RectTransform rect = go.GetComponent<RectTransform>();
        rect.anchorMin = rect.anchorMax = new Vector2(0.5f, 0f);
        rect.pivot = new Vector2(0.5f, 0f);
        rect.anchoredPosition = new Vector2(0f, 24f);
        rect.sizeDelta = new Vector2(1800f, 56f);

        TextMeshProUGUI text = go.AddComponent<TextMeshProUGUI>();
        text.font = bodyText.font;
        UiStyle.Apply(text, UiStyle.Hint);
        text.alignment = TextAlignmentOptions.Center;
        text.color = new Color(1f, 1f, 1f, sessionConfig.ControlsReminderOpacity);
        text.raycastTarget = false;
        text.richText = true;
        text.text = FormatControls(sessionConfig.ControlsReminder);
    }

    // "Mouse: look. W / S: walk." -> each "Key: action" pair with the key on a highlighted chip, pairs spaced apart.
    private static string FormatControls(string reminder)
    {
        var pairs = new System.Collections.Generic.List<string>();
        foreach (string part in reminder.Split(new[] { ". ", "." }, System.StringSplitOptions.RemoveEmptyEntries))
        {
            int colon = part.IndexOf(':');
            pairs.Add(colon < 0 ? part.Trim()
                : $"{UiStyle.Chip(part.Substring(0, colon).Trim())}  {part.Substring(colon + 1).Trim()}");
        }

        return string.Join("<space=70>", pairs);
    }

    private void Update()
    {
        if (panel == null || !panel.activeSelf)
        {
            return;
        }

        if (Keyboard.current == null)
        {
            return;
        }

        // Space is reserved for harvesting, so screens advance with Enter only.
        if (Keyboard.current.enterKey.wasPressedThisFrame ||
            Keyboard.current.numpadEnterKey.wasPressedThisFrame)
        {
            panel.SetActive(false);
            PauseGate.Instructions = false;
        }
    }
}
