using System.IO;
using TMPro;
using UnityEngine;
using UnityEngine.InputSystem;

public class InstructionsPanel : MonoBehaviour
{
    private const string FallbackInstructions =
        "<size=28><b>Welcome to the Foraging Task</b></size>\n\n" +
        "Your goal is to collect as many points as you can before time runs out.\n\n" +
        "Move the mouse to look around.\n" +
        "Press W to walk forward and S to walk backward.\n" +
        "Hold Space to harvest.\n\n" +
        "<i>Press Enter to begin.</i>";

    [SerializeField] private GameObject panel;
    [SerializeField] private TextMeshProUGUI bodyText;
    [SerializeField] private TextMeshProUGUI sessionLabel;

    private const string ContinuePrompt = "\n\n<i>Press Enter to continue.</i>";

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
        bodyText.text = sessionConfig.FirstHarvestMessage.Replace("{points}", bout.boutTotal.ToString("0")) + ContinuePrompt;
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
            bodyText.text = LoadInstructions();
        }

        if (panel != null)
        {
            panel.SetActive(true);
        }

        PauseGate.Instructions = true;

        CreateControlsReminder();
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
        rect.sizeDelta = new Vector2(900f, 40f);

        TextMeshProUGUI text = go.AddComponent<TextMeshProUGUI>();
        text.font = bodyText.font;
        text.fontSize = 22f;
        text.alignment = TextAlignmentOptions.Center;
        text.color = new Color(1f, 1f, 1f, sessionConfig.ControlsReminderOpacity);
        text.raycastTarget = false;
        text.text = sessionConfig.ControlsReminder;
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
