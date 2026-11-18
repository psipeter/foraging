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
//   patch_switch        the nth patch leaving, as RankingBreak counts it (a settled move into another tile that qualifies: a bush harvested, not in the cooldown after a ranking, not in the last
//                       seconds); needs a session with rankings
//   ranking_start       the nth ranking break, a quarter second after the bushes of its first set have grown (the hint pauses the set's countdown)
//   ranking_end         the nth ranking break, as it ends
//   time_left           `@time_left 60`: the first moment 60 foraging seconds or fewer are left (not during a ranking break); the session clock pulses yellow while the hint is up
// Foraging triggers (`bout`, `patch_switch`) are ignored while a ranking break is running. A foraging hint waiting in the queue holds back a ranking hint behind it (the queue is in order).
// Each shown and dismissed hint is logged (`hint_shown`, `hint_dismissed`: id `trigger:n`, trigger, n). A resumed session skips the hints already shown (the server's `hints_shown`), and a trigger's
// count carries on from the highest hint of it that was shown.
public class TutorialHints : MonoBehaviour
{
    private const float RankingHintDelay = 0.25f;      // seconds after the first set's bushes have grown before the ranking hint appears (the set's countdown runs meanwhile; the hint then pauses it)

    private class Hint
    {
        public string trigger;
        public int n = 1;
        public string text;
        public bool shown;

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
        "bout", "patch_switch", "ranking_start", "ranking_end", "time_left",
    };

    private void OnEnable()
    {
        HarvestManager.OnHarvestBoutEnded += HandleBout;
        RankingBreak.OnSetReady += HandleSetReady;
        RankingBreak.OnLeaving += HandleLeaving;
        RankingBreak.OnBreakEnded += HandleBreakEnded;
    }

    private void OnDisable()
    {
        HarvestManager.OnHarvestBoutEnded -= HandleBout;
        RankingBreak.OnSetReady -= HandleSetReady;
        RankingBreak.OnLeaving -= HandleLeaving;
        RankingBreak.OnBreakEnded -= HandleBreakEnded;
    }

    private void HandleBout(HarvestBout bout)
    {
        if (!RankingBreak.Active && !bout.endedBySession && bout.fruitRewards.Count > 0)
        {
            _placeholder = bout.boutTotal.ToString("0");
            Fire("bout");
        }
    }

    private void HandleLeaving(int number)
    {
        _counts["patch_switch"] = number - 1;          // RankingBreak's own count (it continues across a resume), so Fire makes it `number`
        Fire("patch_switch");
    }

    private void HandleSetReady(int indexInBreak)
    {
        if (indexInBreak == 0)
        {
            StartCoroutine(FireAfter("ranking_start", RankingHintDelay));
        }
    }

    private System.Collections.IEnumerator FireAfter(string trigger, float seconds)
    {
        yield return new WaitForSeconds(seconds);
        Fire(trigger);
    }

    private void HandleBreakEnded()
    {
        Fire("ranking_end");
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

        if (_sun != null && !RankingBreak.Active && !_sun.SessionComplete && _sun.SessionTimeRemaining > 0f)
        {
            foreach (Hint hint in _hints)
            {
                if (!hint.shown && hint.trigger == "time_left" && _sun.SessionTimeRemaining <= hint.n)
                {
                    Queue(hint);
                }
            }
        }

        if (_screen.Visible)
        {
            if (Keyboard.current != null && !PauseGate.Pointer && (Keyboard.current.enterKey.wasPressedThisFrame || Keyboard.current.numpadEnterKey.wasPressedThisFrame))
            {
                Dismiss();
            }

            return;
        }

        if (_queue.Count > 0 && (!RankingBreak.Active || _queue.Peek().trigger.StartsWith("ranking")))       // only the ranking popups may appear during a ranking break
        {
            Show(_queue.Dequeue());
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
