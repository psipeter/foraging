using System.Collections;
using System.IO;
using UnityEngine;
using UnityEngine.InputSystem;

public class InstructionsPanel : MonoBehaviour
{
    private const string FallbackInstructions =
        "Foraging task\n\n" +
        "Harvest bushes to collect **points**\n" +
        "Walk next to a bush and hold [Space] to harvest\n\n" +
        "Press [Enter] to begin";

    public SessionConfig sessionConfig;
    public DataLogger dataLogger;           // set by GameManager: the screens shown are logged (`instructions_shown` / `instructions_dismissed`)

    private InstructionsScreen _screen;

    private const int ReminderSortingOrder = 50;             // above the HUD, below every popup
    private const float FirstScreenDelay = 1f;          // seconds the world is shown, the game held, before a session's instruction screen appears

    private IEnumerator Start()
    {
        bool resumed = ResumeInfo.MidSession(GameManager.CurrentSessionIndex);        // decided now: the resume state is cleared a couple of frames into the scene
        _screen = InstructionsScreen.Create();
        PauseGate.Instructions = true;
        CreateControlsReminder();
        if (!resumed)
        {
            yield return new WaitForSecondsRealtime(FirstScreenDelay);          // a resumed session is covered until its pose is back (DataLogger), so its page comes at once
        }

        ShowText(LoadInstructions(resumed), GameManager.PartLabel);
        dataLogger?.LogEvent("instructions_shown", payload: Json.Obj(("kind", resumed ? "welcome_back" : "instructions"), ("file", resumed ? "instructions_resume.txt" : (sessionConfig != null ? sessionConfig.InstructionsFile : ""))));
    }

    // The file's first line is the central instruction (the title), the last "Press [Key] to ..." line the prompt, the rest the text; `eyebrow` is the small line above it
    // ("Session n of m", "Tutorial"), and [Key] in the text becomes a key chip. " // " in the title is a line break.
    private void ShowText(string text, string eyebrow)
    {
        string[] lines = text.Replace("\r", "").Trim().Split('\n');
        string title = System.Text.RegularExpressions.Regex.Replace(lines[0], "<[^>]+>", "").Trim().Replace(" // ", "\n");      // " // " is a line break in the title, to choose where it wraps
        int last = lines.Length - 1;
        string prompt = "Press [Enter] to begin";
        if (last > 0 && lines[last].TrimStart().StartsWith("Press"))
        {
            prompt = lines[last].Trim();
            last--;
        }

        string body = string.Join("\n", lines, 1, Mathf.Max(0, last)).Trim();
        _screen.Show(eyebrow, title, body, prompt);
    }

    private string LoadInstructions(bool resumed)
    {
        string file = sessionConfig != null ? sessionConfig.InstructionsFile : "instructions.txt";
        if (resumed)
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
            .Replace("{part}", GameManager.SessionNumber.ToString())
            .Replace("{total}", GameManager.SessionCount.ToString());
    }

    // The controls hint kept on screen for the whole session (sessions that set one in their config), on a pill at the bottom: "[Mouse] look  [W / S] walk ...".
    private void CreateControlsReminder()
    {
        if (sessionConfig == null || string.IsNullOrEmpty(sessionConfig.ControlsReminder))
        {
            return;
        }

        HintPill.Create(UiStyle.Canvas("ControlsReminder", null, ReminderSortingOrder).transform, "ControlsReminder", 44f, 0.5f).Show(FormatControls(sessionConfig.ControlsReminder));
    }

    // "Mouse: look. W / S: walk." -> "[Mouse] look      [W / S] walk": each "Key: action" pair with the key as a chip, pairs spaced apart.
    private static string FormatControls(string reminder)
    {
        var pairs = new System.Collections.Generic.List<string>();
        foreach (string part in reminder.Split(new[] { '.' }, System.StringSplitOptions.RemoveEmptyEntries))
        {
            int colon = part.IndexOf(':');
            pairs.Add(colon < 0 ? part.Trim() : $"[{part.Substring(0, colon).Trim()}] {part.Substring(colon + 1).Trim()}");
        }

        return string.Join("      ", pairs);
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
            dataLogger?.LogEvent("instructions_dismissed");
        }
    }
}
