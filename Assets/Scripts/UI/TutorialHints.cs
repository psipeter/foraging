using System.Collections.Generic;
using UnityEngine;
using UnityEngine.InputSystem;

// Popup hints that appear as a participant does things in a tutorial session. The hints are a text file in StreamingAssets (`SessionConfig.hintsFile`), a list of blocks,
// each starting with a trigger line:
//
//     # a comment line
//     @bout 1                    the trigger and which occurrence (default 1)
//     Title line                 the first line is the title, a last "Press [Enter] to ..." line the prompt, the rest the text ([Key] becomes a key chip)
//     You earned {points} points.
//
//     Press [Enter] to continue
//
// A hint is shown once, as a pause popup (the game holds still until Enter); hints that fire together are queued. Triggers (an unknown one is logged as an error and never fires):
//   bout                the nth harvest that took fruit, when it ends (`{points}` = what it earned)
//   patch_switch        the nth patch leaving, as SelectionBreak counts it (a settled move into another tile that qualifies: a bush harvested, not in the cooldown after a selection, not in the last
//                       seconds); needs a session with selections
//   selection_start     the nth selection (selection break), a quarter second after the bushes of its first set have grown (the hint pauses the set's countdown)
//   selection_end       the nth selection (selection break), as it ends
//                       A hint whose prompt line names [Escape] ("Press [Escape] to pause") ends when the participant pauses: in a browser, when they have clicked back in after the pause; elsewhere, at the key.
//   time_left           `@time_left 60`: the first moment 60 foraging seconds or fewer are left (not during a selection break); the session clock pulses yellow while the hint is up
// Foraging triggers (`bout`, `patch_switch`) are ignored while a selection break is running. A foraging hint waiting in the queue holds back a selection hint behind it (the queue is in order).
// Each shown and dismissed hint is logged (`hint_shown`, `hint_dismissed`: id `trigger:n`, trigger, n). A resumed session skips the hints already shown (the server's `hints_shown`), and a trigger's
// count carries on from the highest hint of it that was shown.
public class TutorialHints : MonoBehaviour
{
    private const float SelectionHintDelay = 0.25f;      // seconds after the first set's bushes have grown before the selection hint appears (the set's countdown runs meanwhile; the hint then pauses it)

    private class Hint
    {
        public string trigger;
        public int n = 1;
        public string text;
        public bool shown;
        public bool waitsForEscape;        // the prompt asks for [Escape]: the hint ends when the participant pauses, not on Enter

        public string Id => $"{trigger}:{n}";
    }

    private readonly List<Hint> _hints = new List<Hint>();
    private readonly Queue<Hint> _queue = new Queue<Hint>();
    private readonly Dictionary<string, int> _counts = new Dictionary<string, int>();
    private SessionConfig _config;
    private SunController _sun;
    private SessionTimerUI _timer;
    private DataLogger _log;
    private InstructionsScreen _screen;
    private Hint _current;
    private string _placeholder = "";
    private bool _released;                // a hint that waits for Escape: the participant has paused (in a browser it ends when they click back in)

    // True while a hint waits for Escape: QuitHandler leaves the key alone (outside a browser it would end the session).
    public static bool AwaitingEscape { get; private set; }

    // When a hint took Escape: QuitHandler (which runs after this script) leaves the key alone for a moment, so that the press that ended the hint, or its repeat, does not end the session too.
    public static bool EscapeJustTaken => Time.unscaledTime - _escapeTakenAt < 0.75f;
    private static float _escapeTakenAt = float.NegativeInfinity;

    public static TutorialHints Create(SessionConfig config, DataLogger log, SunController sun, SessionTimerUI timer)
    {
        if (config == null || string.IsNullOrEmpty(config.HintsFile))
        {
            return null;
        }

        if (!StreamingData.Exists(config.HintsFile))
        {
            Debug.LogError($"TutorialHints: hints file not found: {config.HintsFile}; write it (docs/DECISIONS.md, 'The tutorial's hints').");
            return null;
        }

        var go = new GameObject("TutorialHints");
        var hints = go.AddComponent<TutorialHints>();
        hints._config = config;
        hints._log = log;
        hints._sun = sun;
        hints._timer = timer;
        hints.Parse(StreamingData.ReadText(config.HintsFile));
        hints.SkipShown();
        hints._screen = InstructionsScreen.Create();
        return hints;
    }

    // A resumed session does not show again what it showed: the hints the server logged as shown are marked shown, and the counts of their triggers carry on from them
    // (a `bout 2` hint then waits for the second bout of the session, not of this visit).
    private void SkipShown()
    {
        if (!ResumeInfo.MidSession(GameManager.CurrentSessionIndex) || ResumeInfo.Pending.hints_shown == null)
        {
            return;
        }

        foreach (string id in ResumeInfo.Pending.hints_shown)
        {
            foreach (Hint hint in _hints)
            {
                if (!hint.shown && hint.Id == id)
                {
                    hint.shown = true;
                    _counts[hint.trigger] = Mathf.Max(_counts.TryGetValue(hint.trigger, out int c) ? c : 0, hint.n);
                }
            }
        }
    }

    // The blocks of a hints file, in order. A block with an unknown trigger is reported once as an error and kept (it never fires), so a typo shows in the console.
    private void Parse(string text)
    {
        Hint block = null;
        var body = new List<string>();
        void Close()
        {
            if (block != null)
            {
                block.text = string.Join("\n", body).Trim();
                _hints.Add(block);
            }

            body.Clear();
        }

        foreach (string raw in text.Replace("\r", "").Split('\n'))
        {
            string line = raw.TrimEnd();
            if (line.TrimStart().StartsWith("#"))
            {
                continue;
            }

            if (line.StartsWith("@"))
            {
                Close();
                string[] parts = line.Substring(1).Trim().Split(new[] { ' ', '\t' }, System.StringSplitOptions.RemoveEmptyEntries);
                block = new Hint { trigger = parts.Length > 0 ? parts[0].ToLowerInvariant() : "" };
                if (parts.Length > 1 && int.TryParse(parts[1], out int n))
                {
                    block.n = Mathf.Max(1, n);
                }

                if (System.Array.IndexOf(Triggers, block.trigger) < 0)
                {
                    Debug.LogError($"TutorialHints: unknown trigger '{block.trigger}' in {_config.HintsFile}.");
                }

                continue;
            }

            if (block != null)
            {
                body.Add(line);
            }
        }

        Close();
    }

    private static readonly string[] Triggers =
    {
        "bout", "patch_switch", "selection_start", "selection_end", "time_left",
    };

    private void OnEnable()
    {
        HarvestManager.OnHarvestBoutEnded += HandleBout;
        SelectionBreak.OnSetReady += HandleSetReady;
        SelectionBreak.OnLeaving += HandleLeaving;
        SelectionBreak.OnBreakEnded += HandleBreakEnded;
    }

    private void OnDisable()
    {
        AwaitingEscape = false;
        HarvestManager.OnHarvestBoutEnded -= HandleBout;
        SelectionBreak.OnSetReady -= HandleSetReady;
        SelectionBreak.OnLeaving -= HandleLeaving;
        SelectionBreak.OnBreakEnded -= HandleBreakEnded;
    }

    private void HandleBout(HarvestBout bout)
    {
        if (!SelectionBreak.Active && !bout.endedBySession && bout.fruitRewards.Count > 0)
        {
            _placeholder = bout.boutTotal.ToString("0");
            Fire("bout");
        }
    }

    private void HandleLeaving(int number)
    {
        _counts["patch_switch"] = number - 1;          // SelectionBreak's own count (it continues across a resume), so Fire makes it `number`
        Fire("patch_switch");
    }

    private void HandleSetReady(int indexInBreak)
    {
        if (indexInBreak == 0)
        {
            StartCoroutine(FireAfter("selection_start", SelectionHintDelay));
        }
    }

    private System.Collections.IEnumerator FireAfter(string trigger, float seconds)
    {
        yield return new WaitForSeconds(seconds);
        Fire(trigger);
    }

    private void HandleBreakEnded()
    {
        Fire("selection_end");
    }

    // Counts the occurrence and queues the hints of this trigger that were waiting for it.
    private void Fire(string trigger)
    {
        int count = _counts.TryGetValue(trigger, out int c) ? c + 1 : 1;
        _counts[trigger] = count;
        foreach (Hint hint in _hints)
        {
            if (!hint.shown && hint.trigger == trigger && hint.n == count)
            {
                Queue(hint);
            }
        }
    }

    private void Queue(Hint hint)
    {
        hint.shown = true;
        hint.text = hint.text.Replace("{points}", _placeholder);
        _queue.Enqueue(hint);
    }

    private void Update()
    {
        if (_screen == null)
        {
            return;
        }

        if (_sun != null && !SelectionBreak.Active && !_sun.SessionComplete && _sun.SessionTimeRemaining > 0f)
        {
            foreach (Hint hint in _hints)
            {
                if (!hint.shown && hint.trigger == "time_left" && _sun.SessionTimeRemaining <= hint.n)
                {
                    Queue(hint);
                }
            }
        }

        if (_current != null && _current.waitsForEscape)
        {
            WaitForEscape();
            return;
        }

        if (_screen.Visible)
        {
            if (Keyboard.current != null && !PauseGate.Pointer && (Keyboard.current.enterKey.wasPressedThisFrame || Keyboard.current.numpadEnterKey.wasPressedThisFrame))
            {
                Dismiss();
            }

            return;
        }

        if (_queue.Count > 0 && (!SelectionBreak.Active || _queue.Peek().trigger.StartsWith("selection")))       // only the selection popups may appear during a selection break
        {
            Show(_queue.Dequeue());
        }
    }

    // A hint that asks for [Escape] (its prompt names it). In a browser the key is the browser's and releases the mouse capture, so the pause (PauseGate.Pointer, the "click to continue" screen) is the
    // sign that it was pressed; the popup then gives way to that screen and ends when the participant has clicked back in. Elsewhere the key itself ends the hint.
    private void WaitForEscape()
    {
        bool browser = Application.platform == RuntimePlatform.WebGLPlayer;
        if (!_released)
        {
            bool pressed = browser ? PauseGate.Pointer : Keyboard.current != null && Keyboard.current.escapeKey.wasPressedThisFrame;
            if (pressed)
            {
                _escapeTakenAt = Time.unscaledTime;
                _released = true;
                _screen.Hide();
            }
        }

        if (_released && (!browser || !PauseGate.Pointer))
        {
            Dismiss();
        }
    }

    private void Show(Hint hint)
    {
        _current = hint;
        string[] lines = hint.text.Trim().Split('\n');
        string title = System.Text.RegularExpressions.Regex.Replace(lines[0], "<[^>]+>", "").Trim().Replace(" // ", "\n");
        int last = lines.Length - 1;
        string prompt = "Press [Enter] to continue";
        if (last > 0 && lines[last].TrimStart().StartsWith("Press"))
        {
            prompt = lines[last].Trim();
            last--;
        }

        string body = string.Join("\n", lines, 1, Mathf.Max(0, last)).Trim();
        _released = false;
        hint.waitsForEscape = prompt.IndexOf("[Escape]", System.StringComparison.OrdinalIgnoreCase) >= 0;
        AwaitingEscape = hint.waitsForEscape;
        _screen.Show(GameManager.PartLabel, title, body, prompt);
        PauseGate.Instructions = true;
        _timer?.SetPulse(hint.trigger == "time_left");
        _log?.LogEvent("hint_shown", payload: Json.Obj(("id", hint.Id), ("trigger", hint.trigger), ("n", hint.n)));
    }

    private void Dismiss()
    {
        _log?.LogEvent("hint_dismissed", payload: Json.Obj(("id", _current != null ? _current.Id : ""), ("trigger", _current != null ? _current.trigger : ""), ("n", _current != null ? _current.n : 0)));
        _screen.Hide();
        _timer?.SetPulse(false);
        _current = null;
        AwaitingEscape = false;
        if (_queue.Count > 0)
        {
            Show(_queue.Dequeue());
        }
        else
        {
            PauseGate.Instructions = false;
        }
    }
}
