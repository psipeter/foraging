using System.IO;
using TMPro;
using UnityEngine;
using UnityEngine.InputSystem;

public class InstructionsPanel : MonoBehaviour
{
    private const string FallbackInstructions =
        "Find the best fruit\n\n" +
        "Collect as many points as you can before time runs out.\n" +
        "Walk next to a bush and hold [Space] to harvest.\n\n" +
        "Press [Enter] to begin";

    // The scene's own panel and text are not used any more (the screen is built in code, UI/InstructionsScreen.cs) and stay hidden.
    [SerializeField] private GameObject panel;
    [SerializeField] private TextMeshProUGUI bodyText;

    public SessionConfig sessionConfig;

    private bool _firstHarvestShown;
    private bool _sessionEnded;
    private InstructionsScreen _screen;

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
            bout.fruitRewards.Count == 0 || _screen == null)
        {
            return;
        }

        _firstHarvestShown = true;
        ShowText(sessionConfig.FirstHarvestMessage.Replace("{points}", bout.boutTotal.ToString("0")) + "\n\nPress [Enter] to continue");
        PauseGate.Instructions = true;
    }

    private void Start()
    {
        if (panel != null)
        {
            panel.SetActive(false);
        }

        _screen = InstructionsScreen.Create();
        ShowText(LoadInstructions());
        PauseGate.Instructions = true;

        CreateControlsReminder();
    }

    // The file's first line is the central instruction (the title), the last "Press [Key] to ..." line the prompt, the rest the text; the part number above is
    // "Part n of m" (a session or an Interlude is just a part), and [Key] in the text becomes a key chip.
    private void ShowText(string text)
    {
        string[] lines = text.Replace("\r", "").Trim().Split('\n');
        string title = System.Text.RegularExpressions.Regex.Replace(lines[0], "<[^>]+>", "").Trim();
        int last = lines.Length - 1;
        string prompt = "Press [Enter] to begin";
        if (last > 0 && lines[last].TrimStart().StartsWith("Press"))
        {
            prompt = lines[last].Trim();
            last--;
        }

        string body = string.Join("\n", lines, 1, Mathf.Max(0, last)).Trim();
        _screen.Show($"Part {GameManager.PartNumber} of {GameManager.PartCount}", title, body, prompt);
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

        return text
            .Replace("{part}", GameManager.PartNumber.ToString())
            .Replace("{total}", GameManager.PartCount.ToString())
            .Replace("{trial_seconds}", (sessionConfig != null ? sessionConfig.InterludeTrialSeconds : 0f).ToString("0"));
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
        foreach (string part in reminder.Split(new[] { '.' }, System.StringSplitOptions.RemoveEmptyEntries))
        {
            int colon = part.IndexOf(':');
            pairs.Add(colon < 0 ? part.Trim()
                : $"{UiStyle.Chip(part.Substring(0, colon).Trim())}  {part.Substring(colon + 1).Trim()}");
        }

        return string.Join("<space=70>", pairs);
    }

    private void Update()
    {
        if (_screen == null || !_screen.Visible || Keyboard.current == null || PauseGate.Pointer)   // not while the "Paused" screen covers it
        {
            return;
        }

        // Space is reserved for harvesting, so screens advance with Enter only.
        if (Keyboard.current.enterKey.wasPressedThisFrame ||
            Keyboard.current.numpadEnterKey.wasPressedThisFrame)
        {
            _screen.Hide();
            PauseGate.Instructions = false;
        }
    }
}
