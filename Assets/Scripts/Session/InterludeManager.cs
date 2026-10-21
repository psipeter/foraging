using System;
using System.Collections;
using System.Globalization;
using System.IO;
using System.Text;
using UnityEngine;
using UnityEngine.UI;

// Runs an Interlude: a short forced-choice block after a session, in that session's own world (terrain, mountains,
// sun) with only two bushes present at a time. The bush table and the trials come from scripts/interlude.py
// (WorldData swaps them in for the session's bushes). The player turns toward the bush they think pays more, walks
// to it and harvests it until interludeHarvestFruits fruits are taken; that bush is the choice. Outcomes are never
// shown (HarvestManager suppresses reward feedback in an Interlude). A trial ends on a
// choice or after interludeTrialSeconds, and every choice is logged to interlude.csv. Correct choices add a hidden
// bonus that is shown only on the final screen.
//
// An Interlude is an ordinary session kind (SessionConfig.isInterlude), so the sun, terrain, bushes, harvesting,
// instruction screen, data logger and end screen all run as in any session; this component only drives the trials.
[DefaultExecutionOrder(30)]
public class InterludeManager : MonoBehaviour
{
    [Serializable]
    private class Bush
    {
        public int id;
        public float shape;
        public float color;
        public float moisture;
        public float value;
    }

    [Serializable]
    private class Trial
    {
        public int index;
        public string type;
        public string varied;
        public float[] start;
        public float yaw;
        public string correct;
        public float deltaValue;
        public Bush left;
        public Bush right;
    }

    [Serializable]
    private class TrialFile
    {
        public string session;
        public string interludeFor;
        public int seed;
        public int n;
        public Trial[] trials;
    }

    private enum State
    {
        Waiting,
        Running,
        Transition,
        Finished
    }

    public SessionConfig sessionConfig;
    public HarvestUI harvestUI;
    public DataLogger dataLogger;

    [SerializeField] private PlayerController player;
    [SerializeField] private CameraController cameraController;
    [SerializeField] private HarvestManager harvestManager;
    [SerializeField] private SunController sunController;
    [Tooltip("Seconds to fade to and from black between trials.")]
    [SerializeField] private float fadeSeconds = 0.25f;
    [Tooltip("Seconds held at black between trials, so the next bushes are in place before the view returns.")]
    [SerializeField] private float blackHoldSeconds = 0.2f;

    private State _state = State.Waiting;
    private Trial[] _order;
    private Tree[] _treesById;
    private int _position = -1;
    private Trial _trial;
    private float _clock;
    private readonly int[] _fruits = new int[2];
    private int _choice = -1;
    private float _choiceTime;
    private float _firstHarvestTime = -1f;
    private int _firstHarvestSide = -1;
    private Image _fade;
    private string _csvPath;

    // True once the trials are loaded and running; SessionTimerUI shows TimerLabel instead of the session clock.
    public bool Active => _order != null && _state != State.Finished;

    public string TimerLabel
    {
        get
        {
            float total = sessionConfig != null ? sessionConfig.InterludeTrialSeconds : 7f;
            int seconds = Mathf.CeilToInt(Mathf.Clamp(total - _clock, 0f, total));
            return $"00:{seconds:D2}";
        }
    }

    private void OnEnable()
    {
        HarvestManager.OnFruitTaken += HandleFruitTaken;
    }

    private void OnDisable()
    {
        HarvestManager.OnFruitTaken -= HandleFruitTaken;
    }

    private void Start()
    {
        if (sessionConfig == null || !sessionConfig.IsInterlude)
        {
            enabled = false;
            return;
        }

        GameManager.BeginInterludeTally();

        TrialFile file = LoadTrials();
        if (file == null || file.trials == null || file.trials.Length == 0)
        {
            Debug.LogError("InterludeManager: no trials loaded; generate them with scripts/interlude.py.");
            enabled = false;
            return;
        }

        // Presentation order is shuffled per participant; the file order is fixed.
        _order = (Trial[])file.trials.Clone();
        var rng = new System.Random();
        for (int i = _order.Length - 1; i > 0; i--)
        {
            int j = rng.Next(i + 1);
            (_order[i], _order[j]) = (_order[j], _order[i]);
        }

        Tree[] all = FindObjectsByType<Tree>(FindObjectsSortMode.None);
        int max = 0;
        foreach (Tree tree in all)
        {
            max = Mathf.Max(max, tree.treeId);
        }

        _treesById = new Tree[max + 1];
        foreach (Tree tree in all)
        {
            if (tree.treeId >= 0)
            {
                _treesById[tree.treeId] = tree;
            }
        }

        BuildFadeOverlay();
        BeginTrial(0);
    }

    private TrialFile LoadTrials()
    {
        string path = WorldData.InterludePathFor(sessionConfig);
        if (!File.Exists(path))
        {
            Debug.LogError($"Interlude trial file not found: {path}");
            return null;
        }

        try
        {
            return JsonUtility.FromJson<TrialFile>(File.ReadAllText(path));
        }
        catch (Exception e)
        {
            Debug.LogError($"Failed to read {path}: {e}");
            return null;
        }
    }

    // Shows only this trial's two bushes, puts the player at the stage spawn facing them, and resets the trial state.
    private void BeginTrial(int position)
    {
        _position = position;
        _trial = _order[position];

        foreach (Tree tree in _treesById)
        {
            if (tree != null)
            {
                tree.gameObject.SetActive(tree.treeId == _trial.left.id || tree.treeId == _trial.right.id);
            }
        }

        harvestManager.RefreshTrees();
        player.TeleportTo(_trial.start[0], _trial.start[1]);
        float pitch = PitchTowardsPair();
        cameraController.SetView(_trial.yaw, pitch);
        if (dataLogger != null)
        {
            dataLogger.LogEvent("teleport", note: $"x={F(_trial.start[0])};z={F(_trial.start[1])};yaw={F(_trial.yaw)};pitch={F(pitch)}");
            dataLogger.LogEvent("trial_start", note: $"order={position};trial={_trial.index};left={_trial.left.id};right={_trial.right.id}");
        }

        _fruits[0] = _fruits[1] = 0;
        _choice = -1;
        _firstHarvestTime = -1f;
        _firstHarvestSide = -1;
        _clock = 0f;

        if (harvestUI != null)
        {
            harvestUI.SetProgressText($"{position + 1}/{_order.Length}");
        }
    }

    // Pitch (degrees, + = looking down) that puts the middle of the two bushes' visible canopies on the view's horizontal
    // centre line, from the eye position at the stage spawn. The yaw (from the trial file) already faces their midpoint.
    private float PitchTowardsPair()
    {
        Camera cam = cameraController.PlayerCamera;
        Tree left = _trial.left.id >= 0 && _trial.left.id < _treesById.Length ? _treesById[_trial.left.id] : null;
        Tree right = _trial.right.id >= 0 && _trial.right.id < _treesById.Length ? _treesById[_trial.right.id] : null;
        if (cam == null || left == null || right == null)
        {
            return 0f;
        }

        Vector3 eye = cam.transform.position;
        Vector3 mid = (left.GetVisibleCenter() + right.GetVisibleCenter()) * 0.5f;
        float horizontal = Mathf.Sqrt((mid.x - eye.x) * (mid.x - eye.x) + (mid.z - eye.z) * (mid.z - eye.z));
        float pitch = Mathf.Atan2(eye.y - mid.y, Mathf.Max(horizontal, 0.01f)) * Mathf.Rad2Deg;
        return Mathf.Clamp(pitch, -sessionConfig.LookPitchLimit, sessionConfig.LookPitchLimit);
    }

    private void Update()
    {
        switch (_state)
        {
            case State.Waiting:
                // The instruction screen holds Time.timeScale at 0; the first trial's clock starts when it closes.
                if (Time.timeScale > 0f)
                {
                    _state = State.Running;
                }

                break;

            case State.Running:
                if (Time.timeScale <= 0f)
                {
                    break;
                }

                _clock += Time.deltaTime;
                if (_firstHarvestTime < 0f && harvestManager.IsHarvesting)
                {
                    _firstHarvestTime = _clock;
                    _firstHarvestSide = harvestManager.FocusTreeId == _trial.left.id ? 0 : 1;
                }

                if (_choice >= 0)
                {
                    harvestManager.CancelBout();
                    Finish(false);
                }
                else if (_clock >= sessionConfig.InterludeTrialSeconds)
                {
                    harvestManager.CancelBout();
                    Finish(true);
                }

                break;
        }
    }

    // A fruit counts toward the bush it came from; the first bush to reach the required count is the choice.
    private void HandleFruitTaken(Tree tree)
    {
        if (_state != State.Running || tree == null || _trial == null)
        {
            return;
        }

        int side = tree.treeId == _trial.left.id ? 0 : (tree.treeId == _trial.right.id ? 1 : -1);
        if (side < 0)
        {
            return;
        }

        _fruits[side]++;
        if (_choice < 0 && _fruits[side] >= sessionConfig.InterludeHarvestFruits)
        {
            _choice = side;
            _choiceTime = _clock;
        }
    }

    private void Finish(bool timedOut)
    {
        bool correct = !timedOut && (_trial.correct == "either"
                                     || (_choice == 0 && _trial.correct == "left")
                                     || (_choice == 1 && _trial.correct == "right"));
        float bonus = correct && !sessionConfig.IsPractice ? sessionConfig.InterludeBonusPerCorrect : 0f;
        if (!sessionConfig.IsPractice)
        {
            GameManager.RecordInterludeTrial(correct, bonus);
        }

        WriteRow(timedOut, correct, bonus);
        if (dataLogger != null)
        {
            string side = _choice == 0 ? "left" : (_choice == 1 ? "right" : "none");
            dataLogger.LogEvent("trial_end", note: $"choice={side};correct={(correct ? 1 : 0)};timed_out={(timedOut ? 1 : 0)}");
        }

        _state = State.Transition;
        StartCoroutine(_position + 1 < _order.Length ? TransitionTo(_position + 1) : Complete());
    }

    private IEnumerator TransitionTo(int next)
    {
        player.SetFrozen(true);
        yield return Fade(0f, 1f);
        BeginTrial(next);
        yield return new WaitForSecondsRealtime(blackHoldSeconds);
        yield return Fade(1f, 0f);
        player.SetFrozen(false);
        _state = State.Running;
    }

    private IEnumerator Complete()
    {
        player.SetFrozen(true);
        yield return new WaitForSecondsRealtime(0.2f);
        _state = State.Finished;
        sunController.EndSession();
    }

    private IEnumerator Fade(float from, float to)
    {
        float t = 0f;
        float seconds = Mathf.Max(fadeSeconds, 0.01f);
        while (t < seconds)
        {
            t += Time.unscaledDeltaTime;
            SetFade(Mathf.Lerp(from, to, t / seconds));
            yield return null;
        }

        SetFade(to);
    }

    private void SetFade(float alpha)
    {
        if (_fade != null)
        {
            _fade.color = new Color(0f, 0f, 0f, alpha);
        }
    }

    private void BuildFadeOverlay()
    {
        Canvas canvas = harvestUI != null ? harvestUI.GetComponent<Canvas>() : null;
        if (canvas == null)
        {
            return;
        }

        var go = new GameObject("InterludeFade", typeof(RectTransform), typeof(Image));
        RectTransform rect = go.GetComponent<RectTransform>();
        rect.SetParent(canvas.transform, false);
        rect.anchorMin = Vector2.zero;
        rect.anchorMax = Vector2.one;
        rect.offsetMin = Vector2.zero;
        rect.offsetMax = Vector2.zero;
        _fade = go.GetComponent<Image>();
        _fade.raycastTarget = false;
        SetFade(0f);
    }

    private void WriteRow(bool timedOut, bool correct, float bonus)
    {
        string folder = dataLogger != null ? dataLogger.SessionDataPath : null;
        if (string.IsNullOrEmpty(folder))
        {
            return;
        }

        try
        {
            if (_csvPath == null)
            {
                _csvPath = Path.Combine(folder, "interlude.csv");
                File.WriteAllText(_csvPath,
                    "presented_order,trial_index,type,varied_feature,stage_x,stage_z," +
                    "left_id,left_shape,left_color,left_moisture,left_value," +
                    "right_id,right_shape,right_color,right_moisture,right_value," +
                    "correct_side,choice,choice_correct,timed_out,response_time,first_harvest_time,first_harvest_side," +
                    "left_fruits,right_fruits,bonus\n", Encoding.UTF8);
            }

            string choice = _choice == 0 ? "left" : (_choice == 1 ? "right" : "none");
            string firstSide = _firstHarvestSide == 0 ? "left" : (_firstHarvestSide == 1 ? "right" : "none");
            float response = timedOut ? sessionConfig.InterludeTrialSeconds : _choiceTime;
            var sb = new StringBuilder();
            sb.Append(_position).Append(',').Append(_trial.index).Append(',').Append(_trial.type).Append(',').Append(_trial.varied).Append(',');
            sb.Append(F(_trial.start[0])).Append(',').Append(F(_trial.start[1])).Append(',');
            AppendBush(sb, _trial.left);
            AppendBush(sb, _trial.right);
            sb.Append(_trial.correct).Append(',').Append(choice).Append(',').Append(correct ? 1 : 0).Append(',').Append(timedOut ? 1 : 0).Append(',');
            sb.Append(F(response)).Append(',').Append(_firstHarvestTime < 0f ? "" : F(_firstHarvestTime)).Append(',').Append(firstSide).Append(',');
            sb.Append(_fruits[0]).Append(',').Append(_fruits[1]).Append(',').Append(F(bonus)).Append('\n');
            File.AppendAllText(_csvPath, sb.ToString(), Encoding.UTF8);
        }
        catch (Exception e)
        {
            Debug.LogError($"InterludeManager failed to write interlude.csv: {e}");
        }
    }

    private static void AppendBush(StringBuilder sb, Bush b)
    {
        sb.Append(b.id).Append(',').Append(F(b.shape)).Append(',').Append(F(b.color)).Append(',').Append(F(b.moisture)).Append(',').Append(F(b.value)).Append(',');
    }

    private static string F(float value)
    {
        return value.ToString("0.####", CultureInfo.InvariantCulture);
    }
}
