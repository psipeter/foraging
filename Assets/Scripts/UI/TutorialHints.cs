using System.Collections.Generic;
using UnityEngine;
using UnityEngine.InputSystem;

// Popup hints that appear as a participant does things in a tutorial session. The hints are a text file in StreamingAssets (`SessionConfig.hintsFile`), a list of blocks,
// each starting with a trigger line:
//
//     # a comment line
//     @fruit 1                   the trigger and, where it counts, which occurrence (default 1)
//     Title line                 the first line is the title, a last "Press [Enter] to ..." line the prompt, the rest the text ([Key] becomes a key chip)
//     You earned {points} points.
//
//     Press [Enter] to continue
//
// A hint is shown once, as a pause popup (the game holds still until Enter, as for the first-harvest message); hints that fire together are queued. Triggers:
//   harvest_available   the nth time a bush comes into harvest range and under the crosshair (the "hold Space" hint appears)
//   harvest_paused      the nth time a harvest in progress is paused (looked away)
//   fruit               the nth fruit taken (`{points}` = its reward)
//   bout                the nth harvest that took fruit, when it ends (`{points}` = what it earned)
//   exhausted           the nth bush picked empty
//   patch_switch        the nth patch switch (the nearest tile changes and the player is a few units into the new one)
//   ranking_start       the nth ranking break, as it starts
//   ranking_end         the nth ranking break, as it ends
//   seconds             this many foraging seconds into the session (n = seconds)
//   idle                after this many seconds standing still without harvesting (n = seconds; fires again for each block of the same trigger with a larger n)
// Foraging triggers are ignored while a ranking break is running (the ranking bushes pay nothing and show no outcome). Each shown and dismissed hint is logged
// (`hint_shown`, `hint_dismissed`: id, trigger, n). A resumed session starts its hints again.
public class TutorialHints : MonoBehaviour
{
    private const float PatchSettleDepth = 3f;       // units into the new tile before a patch switch counts (the edge itself would flicker)

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
    private WorldData _world;
    private PlayerController _player;
    private SunController _sun;
    private DataLogger _log;
    private InstructionsScreen _screen;
    private Hint _current;
    private string _placeholder = "";
    private int _tile = -1;
    private float _idleSeconds;
    private Vector3 _lastPosition;

    public static TutorialHints Create(SessionConfig config, WorldData world, PlayerController player, SunController sun, DataLogger log)
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
        hints._world = world;
        hints._player = player;
        hints._sun = sun;
        hints._log = log;
        hints.Parse(StreamingData.ReadText(config.HintsFile));
        hints._screen = InstructionsScreen.Create();
        return hints;
    }

    // The blocks of a hints file, in order. A block with an unknown trigger is reported once and kept (it never fires), so a typo shows in the console.
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
                    Debug.LogWarning($"TutorialHints: unknown trigger '{block.trigger}' in {_config.HintsFile}.");
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
        "harvest_available", "harvest_paused", "fruit", "bout", "exhausted", "patch_switch", "ranking_start", "ranking_end", "seconds", "idle",
    };

    private void OnEnable()
    {
        HarvestManager.OnHintChanged += HandleHint;
        HarvestManager.OnFruitCollected += HandleFruit;
        HarvestManager.OnHarvestBoutEnded += HandleBout;
        HarvestManager.OnBushExhausted += HandleExhausted;
        RankingBreak.OnBreakStarted += HandleBreakStarted;
        RankingBreak.OnBreakEnded += HandleBreakEnded;
    }

    private void OnDisable()
    {
        HarvestManager.OnHintChanged -= HandleHint;
        HarvestManager.OnFruitCollected -= HandleFruit;
        HarvestManager.OnHarvestBoutEnded -= HandleBout;
        HarvestManager.OnBushExhausted -= HandleExhausted;
        RankingBreak.OnBreakStarted -= HandleBreakStarted;
        RankingBreak.OnBreakEnded -= HandleBreakEnded;
    }

    private void HandleHint(HarvestHint hint)
    {
        if (RankingBreak.Active)
        {
            return;
        }

        if (hint == HarvestHint.Available)
        {
            Fire("harvest_available");
        }
        else if (hint == HarvestHint.Paused)
        {
            Fire("harvest_paused");
        }
    }

    private void HandleFruit(float amount, Vector3 worldPos)
    {
        if (!RankingBreak.Active)
        {
            _placeholder = amount.ToString("0");
            Fire("fruit");
        }
    }

    private void HandleBout(HarvestBout bout)
    {
        if (!RankingBreak.Active && !bout.endedBySession && bout.fruitRewards.Count > 0)
        {
            _placeholder = bout.boutTotal.ToString("0");
            Fire("bout");
        }
    }

    private void HandleExhausted()
    {
        if (!RankingBreak.Active)
        {
            Fire("exhausted");
        }
    }

    private void HandleBreakStarted()
    {
        Fire("ranking_start");
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

        if (_screen.Visible)
        {
            if (Keyboard.current != null && !PauseGate.Pointer && (Keyboard.current.enterKey.wasPressedThisFrame || Keyboard.current.numpadEnterKey.wasPressedThisFrame))
            {
                Dismiss();
            }

            return;
        }

        PollClockAndPlace();
        if (_queue.Count > 0)
        {
            Show(_queue.Dequeue());
        }
    }

    // The triggers that are read from the world rather than announced: foraging seconds, patch switches and standing idle.
    private void PollClockAndPlace()
    {
        if (RankingBreak.Active || _player == null)
        {
            return;
        }

        if (_sun != null)
        {
            float elapsed = _config.SessionDuration - _sun.SessionTimeRemaining;
            foreach (Hint hint in _hints)
            {
                if (!hint.shown && hint.trigger == "seconds" && elapsed >= hint.n)
                {
                    Queue(hint);
                }
            }
        }

        Vector3 position = _player.transform.position;
        _idleSeconds = (position - _lastPosition).sqrMagnitude > 0.0004f || HarvestHeld() ? 0f : _idleSeconds + Time.deltaTime;
        _lastPosition = position;
        foreach (Hint hint in _hints)
        {
            if (!hint.shown && hint.trigger == "idle" && _idleSeconds >= hint.n)
            {
                Queue(hint);
            }
        }

        if (_world != null && _world.HasTiles)
        {
            int nearest = _world.NearestTile(position.x, position.z);
            if (_tile < 0)
            {
                _tile = nearest;
            }
            else if (nearest != _tile && _world.DepthIntoTile(position.x, position.z, _tile, nearest) >= PatchSettleDepth)
            {
                _tile = nearest;
                Fire("patch_switch");
            }
        }
    }

    private bool HarvestHeld()
    {
        return _player != null && _player.HarvestHeld;
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
        _screen.Show(null, title, body, prompt, true);
        PauseGate.Instructions = true;
        _log?.LogEvent("hint_shown", payload: Json.Obj(("id", hint.Id), ("trigger", hint.trigger), ("n", hint.n)));
    }

    private void Dismiss()
    {
        _log?.LogEvent("hint_dismissed", payload: Json.Obj(("id", _current != null ? _current.Id : ""), ("trigger", _current != null ? _current.trigger : ""), ("n", _current != null ? _current.n : 0)));
        _screen.Hide();
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
