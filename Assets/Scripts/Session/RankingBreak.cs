using System;
using System.Collections;
using System.Collections.Generic;
using TMPro;
using UnityEngine;

// A ranking break: a ranking set played in place, inside a foraging session, so the participant stays in the foraging stage (SessionConfig.rankingBreak*,
// docs/DECISIONS.md "FOR: ranking breaks inside the session"). After every `rankingBreakEvery` patch switches (a settled crossing into another tile of a tiles
// world) the real bushes fade to grayscale (and cannot be aimed at) and a set of ranking bushes grows on the Interlude's arc in front of the player, on the terrain they stand on. The player
// harvests them from most to least points under the Interlude's rules (stationary, any bush in view, a started harvest is finished). The session clock is held
// while a break runs (SunController.ClockHeld) and a second countdown shows the set's own seconds; outcomes are hidden and the ranking bushes pay nothing
// (zero fruit rewards), so the score does not move. The sets come from the session's pool file (scripts/ranking.py pool), used in order.
// Created at runtime by GameManager (no scene wiring). Not built yet: replay/visibility gaps, resume. The arc is placed on whatever ground is there (no wait for flat ground: it looked fine in the first playtest).
public class RankingBreak : MonoBehaviour
{
    [Serializable]
    private class PoolBush
    {
        public int id;
        public int slot;
        public float bearing;
        public float shape;
        public float color;
        public float moisture;
        public float value;
    }

    [Serializable]
    private class PoolSet
    {
        public int index;
        public PoolBush[] bushes;
    }

    [Serializable]
    private class PoolFile
    {
        public string format;
        public int n;
        public int setSize;
        public float tieTolerance;
        public int fruitCount;
        public float[] treePos;
        public float[] canopyRadius;
        public PoolSet[] trials;
    }

    // True from the start of a break to its end: the consumers of HarvestManager's events (HarvestUI, FeedbackAudio, InstructionsPanel) hide outcomes meanwhile.
    public static bool Active { get; private set; }

    // The hidden bonus earned in this session's breaks so far (what the correct pairs would pay, also in a practice session); the session's end screen adds it to the points.
    public static float Points { get; private set; }

    // The running set's countdown (seconds), for the clock under the main one.
    public float SecondsLeft { get; private set; }

    private SessionConfig _config;
    private WorldData _world;
    private TreeGenerator _treeGenerator;
    private PlayerController _player;
    private CameraController _camera;
    private HarvestManager _harvest;
    private SunController _sun;
    private HarvestUI _harvestUI;
    private DataLogger _log;
    private SessionTimerUI _timer;
    private PoolFile _pool;
    private TextMeshProUGUI _clockText;
    private GameObject _hud;
    private CanvasGroup _hudGroup;
    private Coroutine _hudFade;

    private bool _running;
    private bool _removingSet;                    // the last set's bushes are still shrinking away
    private bool _ungraying;                      // the world's bushes are still returning to colour
    private Tree[] _real;                         // the world's bushes, grey for the break
    private bool[] _realHarvested;                // whether each was spent (not aimable) before it
    private bool _prepared;
    private int _tile = -1;
    private int _switches;
    private int _breakNumber;
    private int _poolIndex;
    private int _setCounter;                // sets played in the session so far: the row's position, one after another
    private readonly HashSet<int> _harvestedBushes = new HashSet<int>();       // the world's bushes a fruit has been taken from
    private float _lastEnd = float.NegativeInfinity;       // session seconds elapsed when the last break ended

    // The running set.
    private bool _setLive;
    private float _setClock;
    private float _firstHarvestTime;
    private readonly List<int> _picks = new List<int>();
    private readonly List<float> _pickTimes = new List<float>();
    private readonly Dictionary<int, float> _firstStart = new Dictionary<int, float>();
    private readonly Dictionary<int, Tree> _setTrees = new Dictionary<int, Tree>();
    private int _setSize;

    // The break component for a session, or null when it has none (no breaks configured, no tiles in the world, no pool file).
    public static RankingBreak Create(SessionConfig config, WorldData world, TreeGenerator treeGenerator, PlayerController player, CameraController camera,
        HarvestManager harvest, SunController sun, HarvestUI harvestUI, DataLogger log, SessionTimerUI timer)
    {
        if (config == null || config.RankingBreakEvery <= 0 || world == null || !world.HasTiles || config.IsInterlude)
        {
            return null;
        }

        string path = WorldData.RankingPoolPathFor(config);
        if (!StreamingData.Exists(path))
        {
            Debug.LogError($"RankingBreak: pool file not found: {path}; generate it with scripts/ranking.py pool {config.name}.");
            return null;
        }

        PoolFile pool = JsonUtility.FromJson<PoolFile>(StreamingData.ReadText(path));
        if (pool == null || pool.format != "ranking-break" || pool.trials == null || pool.trials.Length == 0)
        {
            Debug.LogError($"RankingBreak: {path} is not a ranking-break pool; regenerate it.");
            return null;
        }

        var go = new GameObject("RankingBreak");
        var rankingBreak = go.AddComponent<RankingBreak>();
        rankingBreak._config = config;
        rankingBreak._world = world;
        rankingBreak._treeGenerator = treeGenerator;
        rankingBreak._player = player;
        rankingBreak._camera = camera;
        rankingBreak._harvest = harvest;
        rankingBreak._sun = sun;
        rankingBreak._harvestUI = harvestUI;
        rankingBreak._log = log;
        rankingBreak._timer = timer;
        rankingBreak._pool = pool;
        Points = 0f;
        if (ResumeInfo.MidSession(GameManager.CurrentSessionIndex))
        {
            Points = ResumeInfo.Pending.break_bonus;
            // Continuing an interrupted session: the numbering, the pool and the rows carry on (an unfinished break is not resumed; the patch switch count starts again).
            rankingBreak._breakNumber = ResumeInfo.Pending.breaks;
            rankingBreak._poolIndex = ResumeInfo.Pending.sets_played;
            rankingBreak._setCounter = ResumeInfo.Pending.trials_next;
            foreach (TreeCount taken in ResumeInfo.Pending.fruits_taken)
            {
                if (taken.n > 0 && taken.tree < world.TreeCount)
                {
                    rankingBreak._harvestedBushes.Add(taken.tree);
                }
            }
        }

        return rankingBreak;
    }

    private void OnEnable()
    {
        HarvestManager.OnFruitTaken += HandleFruitTaken;
        HarvestManager.OnHarvestBoutStarted += HandleBoutStarted;
    }

    private void OnDisable()
    {
        HarvestManager.OnFruitTaken -= HandleFruitTaken;
        HarvestManager.OnHarvestBoutStarted -= HandleBoutStarted;
    }

    private void OnDestroy()
    {
        Active = false;
        if (_sun != null)
        {
            _sun.ClockHeld = false;
        }

        _timer?.SetPaused(false);

        if (_harvest != null)
        {
            _harvest.SetFruitSeconds(-1f);
        }
    }

    private void Update()
    {
        if (_running)
        {
            RefreshClock();
            return;
        }

        if (_pool == null || Time.timeScale <= 0f || _sun.SessionComplete)
        {
            return;
        }

        if (!_prepared)
        {
            _prepared = true;
            Tree[] trees = FindObjectsByType<Tree>(FindObjectsSortMode.None);
            if (trees.Length > 0)
            {
                trees[0].PrepareGray();                // makes the desaturated canopy textures now, not in the first break
            }
        }

        Vector3 p = _player.transform.position;
        int tile = _world.NearestTile(p.x, p.z);
        if (_tile < 0)
        {
            _tile = tile;
            return;
        }

        // A switch counts once the player is `rankingBreakSettleDepth` past the edge on the new side (0: at the edge, which puts the arc farthest from the next cluster); one inside the cooldown after a break,
        // or in the last seconds of the session, or before enough bushes have been harvested, is ignored (it does not wait to fire later, in the middle of the next patch).
        if (tile != _tile && _world.DepthIntoTile(p.x, p.z, _tile, tile) >= _config.RankingBreakSettleDepth)
        {
            _tile = tile;
            if (SwitchCounts())
            {
                _switches++;
            }
        }

        if (_switches >= _config.RankingBreakEvery && !_harvest.IsHarvesting)
        {
            StartCoroutine(RunBreak());
        }
    }

    private bool SwitchCounts()
    {
        float elapsed = _config.SessionDuration - _sun.SessionTimeRemaining;
        return _sun.SessionTimeRemaining > _config.RankingBreakLastSeconds && elapsed - _lastEnd >= _config.RankingBreakCooldown
            && _harvestedBushes.Count >= _config.RankingBreakMinBushes;
    }

    private IEnumerator RunBreak()
    {
        _running = true;
        Active = true;
        _sun.ClockHeld = true;
        _timer?.SetPaused(true);
        _breakNumber++;
        _player.SetStationary(true);
        _harvest.SetBlocked(true);
        _harvest.SetAimMode(true, _config.InterludeAimTolerance);
        _harvest.SetFruitSeconds(_config.RankingBreakFruitSeconds);
        if (_log != null)
        {
            _log.LogEvent("rank_break_start", payload: Json.Obj(("break", _breakNumber), ("switches", _switches), ("tile", _tile), ("pool_index", _poolIndex), ("sets", _config.RankingBreakSets)));
        }

        // The world's bushes stay where they are but go grey, and none can be aimed at meanwhile.
        _real = FindObjectsByType<Tree>(FindObjectsSortMode.None);
        _realHarvested = new bool[_real.Length];
        for (int i = 0; i < _real.Length; i++)
        {
            _realHarvested[i] = _real[i].isHarvested;
            _real[i].isHarvested = true;
        }

        yield return GrayFade(1f);

        for (int s = 0; s < _config.RankingBreakSets; s++)
        {
            PoolSet set = _pool.trials[_poolIndex % _pool.trials.Length];
            yield return RunSet(set, s, s == _config.RankingBreakSets - 1);
            _poolIndex++;
        }

        while (_removingSet || _ungraying)
        {
            yield return null;
        }

        for (int i = 0; i < _real.Length; i++)
        {
            if (_real[i] != null)
            {
                _real[i].isHarvested = _realHarvested[i];
            }
        }

        _harvest.RefreshTrees();
        _harvest.SetAimMode(false, 0f);
        _harvest.SetFruitSeconds(-1f);
        _player.SetStationary(false);
        _harvest.SetBlocked(false);
        HideHud();
        if (_log != null)
        {
            _log.LogEvent("rank_break_end", payload: Json.Obj(("break", _breakNumber)));
        }

        Active = false;
        _sun.ClockHeld = false;
        _timer?.SetPaused(false);
        _lastEnd = _config.SessionDuration - _sun.SessionTimeRemaining;
        _switches = 0;
        _running = false;
    }

    // One set: the bushes grow on the arc in front of the player, the countdown runs until every bush is ranked or the seconds are used, the set is scored (hidden)
    // and logged, and the bushes shrink away. After the break's last set the player is free to move at once; the set's bushes
    // shrink and the real ones regrow around them, and harvesting is allowed again when that is done.
    private IEnumerator RunSet(PoolSet set, int indexInBreak, bool last)
    {
        Vector3 origin = _player.transform.position;
        Quaternion turn = Quaternion.Euler(0f, _camera.Yaw, 0f);
        _setTrees.Clear();
        _setSize = set.bushes.Length;
        var created = new List<Tree>();
        var scales = new List<Vector3>();
        foreach (PoolBush b in set.bushes)
        {
            Vector3 offset = turn * new Vector3(_pool.treePos[2 * b.id], 0f, _pool.treePos[2 * b.id + 1]);
            var attributes = new TreeAttributes { shape = b.shape, color = b.color, moisture = b.moisture };
            Tree tree = _treeGenerator.CreateTree(_world.TreeCount + b.id, origin.x + offset.x, origin.z + offset.z, attributes, new int[Mathf.Max(_pool.fruitCount, 1)]);
            if (tree == null)
            {
                continue;
            }

            tree.isHarvested = true;           // not aimable (no highlight, no ring) until the set has finished growing
            _setTrees[b.id] = tree;
            created.Add(tree);
            scales.Add(tree.transform.localScale);
        }

        foreach (Tree tree in created)
        {
            tree.transform.localScale = tree.transform.localScale * 0.001f;
        }

        _harvest.RefreshTrees();
        if (_log != null)
        {
            // The set's bush table (where the arc fell, so replay.py and visibility.py can place the bushes): they are not in the world file.
            var table = new List<string>();
            foreach (PoolBush b in set.bushes)
            {
                if (_setTrees.TryGetValue(b.id, out Tree placed))
                {
                    Vector3 at = placed.transform.position;
                    table.Add(Json.Obj(("id", _world.TreeCount + b.id), ("x", (double)at.x), ("z", (double)at.z), ("radius", (double)placed.CanopyRadius), ("shape", (double)b.shape)));
                }
            }

            _log.LogEvent("rank_set", payload: Json.Obj(("break", _breakNumber), ("set", set.index), ("fruits", Mathf.Max(_pool.fruitCount, 1)), ("bushes", new Json.Raw("[" + string.Join(",", table) + "]"))));
        }

        ShowHud();
        yield return Scale(created.ToArray(), scales.ToArray(), 0f, 1f);
        foreach (Tree tree in created)
        {
            tree.isHarvested = false;
        }

        _picks.Clear();
        _pickTimes.Clear();
        _firstStart.Clear();
        _firstHarvestTime = -1f;
        _setClock = 0f;
        float paused = 0f;
        bool timedOut = false;
        SecondsLeft = _config.RankingBreakSeconds;
        var ids = new List<string>();
        foreach (PoolBush b in set.bushes)
        {
            ids.Add((_world.TreeCount + b.id).ToString());
        }

        if (_log != null)
        {
            _log.LogEvent("trial_start", payload: Json.Obj(("order", indexInBreak), ("trial", set.index), ("break", _breakNumber), ("bushes", new Json.Raw("[" + string.Join(",", ids) + "]"))));
        }

        _setLive = true;
        _harvest.SetBlocked(false);
        if (_log != null)
        {
            _log.LogEvent("rank_go", payload: Json.Obj(("break", _breakNumber)));       // the end of the harvest block: replay ignores presses up to and including this frame
        }

        while (true)
        {
            yield return null;
            if (Time.timeScale <= 0f)
            {
                paused += Time.unscaledDeltaTime;          // held still (mouse released, upload, ...): the set's clock stops
                continue;
            }

            _setClock += Time.deltaTime;
            SecondsLeft = Mathf.Max(0f, _config.RankingBreakSeconds - _setClock);
            if (_firstHarvestTime < 0f && _harvest.IsHarvesting)
            {
                _firstHarvestTime = _setClock;
            }

            if (_picks.Count == _setSize)
            {
                break;
            }

            if (_setClock >= _config.RankingBreakSeconds)
            {
                _harvest.CancelBout();
                timedOut = true;
                break;
            }
        }

        _setLive = false;
        _harvest.SetBlocked(true);
        foreach (Tree tree in created)
        {
            tree.isHarvested = true;           // no highlight or ring while the set shrinks away
        }

        FinishSet(set, indexInBreak, timedOut, paused);
        if (last)
        {
            _player.SetStationary(false);
            HideHud();
            _removingSet = true;
            _ungraying = true;
            StartCoroutine(RemoveSet(created, scales));
            StartCoroutine(GrayFadeBack());
            yield break;
        }

        FadeHud(0f);
        yield return new WaitForSecondsRealtime(_config.RankingBreakFadeSeconds);
        yield return RemoveSet(created, scales);
    }

    // The set's bushes shrink away and are destroyed.
    private IEnumerator RemoveSet(List<Tree> created, List<Vector3> scales)
    {
        yield return Scale(created.ToArray(), scales.ToArray(), 1f, 0f);
        foreach (Tree tree in created)
        {
            tree.SetRank(0);
            Destroy(tree.gameObject);
        }

        _setTrees.Clear();
        yield return null;
        _harvest.RefreshTrees();
        _removingSet = false;
    }

    private void FinishSet(PoolSet set, int indexInBreak, bool timedOut, float paused)
    {
        var values = new Dictionary<int, float>();
        var setIds = new List<int>();
        foreach (PoolBush b in set.bushes)
        {
            values[_world.TreeCount + b.id] = b.value;
            setIds.Add(_world.TreeCount + b.id);
        }

        float tie = _pool.tieTolerance > 0f ? _pool.tieTolerance : 0.05f;
        RankingSets.ScorePairs(setIds, values, _picks, tie, out int correct, out int total);
        float worth = correct * _config.InterludeBonusPerPair;
        float bonus = _config.IsPractice ? 0f : worth;
        Points += worth;
        if (_log == null)
        {
            return;
        }

        var times = new List<string>();
        foreach (float t in _pickTimes)
        {
            times.Add(RankingSets.F(t));
        }

        _log.LogEvent("trial_end", payload: Json.Obj(("picked", new Json.Raw("[" + string.Join(",", _picks) + "]")), ("pick_times", new Json.Raw("[" + string.Join(",", times) + "]")),
            ("correct_pairs", correct), ("total_pairs", total), ("first_harvest_time", _firstHarvestTime < 0f ? null : (object)_firstHarvestTime), ("timed_out", timedOut ? 1 : 0),
            ("paused_seconds", paused), ("bonus", bonus), ("break", _breakNumber)));

        var objects = new List<string>();
        foreach (PoolBush b in set.bushes)
        {
            int id = _world.TreeCount + b.id;
            int index = _picks.IndexOf(id);
            _setTrees.TryGetValue(b.id, out Tree tree);
            objects.Add(RankingSets.BushObject(id, b.slot, b.shape, b.color, b.moisture, b.value, index + 1, _firstStart.TryGetValue(id, out float started) ? started : -1f,
                index >= 0 ? _pickTimes[index] : -1f, tree != null ? tree.FruitCount - tree.FruitsRemaining : 0));
        }

        float response = timedOut ? _config.RankingBreakSeconds : (_pickTimes.Count > 0 ? _pickTimes[_pickTimes.Count - 1] : 0f);
        Vector3 p = _player.transform.position;
        _log.LogTrial(RankingSets.RowCells(_setCounter++, set.index, p.x, p.z, timedOut, response, _firstHarvestTime, bonus, paused, _setSize, correct, total, objects));
    }

    private void HandleBoutStarted(Tree tree)
    {
        if (_setLive && tree != null && _setTrees.ContainsValue(tree) && !_firstStart.ContainsKey(tree.treeId))
        {
            _firstStart[tree.treeId] = _setClock;
        }
    }

    // A fruit of a set's bush; the bush finished (every fruit taken) takes the next rank, which is shown above it.
    private void HandleFruitTaken(Tree tree)
    {
        if (!_running && tree != null && tree.treeId < _world.TreeCount)
        {
            _harvestedBushes.Add(tree.treeId);
        }

        if (!_setLive || tree == null || !_setTrees.ContainsValue(tree) || _picks.Contains(tree.treeId) || tree.FruitsRemaining > 0)
        {
            return;
        }

        _picks.Add(tree.treeId);
        _pickTimes.Add(_setClock);
        tree.SetRank(_picks.Count);
        if (_log != null)
        {
            _log.LogEvent("pick", tree.treeId, payload: Json.Obj(("rank", _picks.Count), ("set_time", _setClock), ("break", _breakNumber)));
        }
    }

    // The world's bushes fade to grayscale over the gray-fade seconds (`to` 1; the arc's bushes grow after it).
    private IEnumerator GrayFade(float to)
    {
        yield return GrayFade(_real, 1f - to, to);
    }

    private IEnumerator GrayFadeBack()
    {
        yield return GrayFade(_real, 1f, 0f);
        _ungraying = false;
    }

    private IEnumerator GrayFade(Tree[] trees, float from, float to)
    {
        float seconds = Mathf.Max(_config.RankingBreakGraySeconds, 0.01f);
        float elapsed = 0f;
        while (elapsed < seconds)
        {
            elapsed += Time.deltaTime;
            float amount = Mathf.Lerp(from, to, Mathf.Clamp01(elapsed / seconds));
            foreach (Tree tree in trees)
            {
                if (tree != null)
                {
                    tree.SetGray(amount);
                }
            }

            yield return null;
        }

        foreach (Tree tree in trees)
        {
            if (tree != null)
            {
                tree.SetGray(to);
            }
        }
    }

    // The trees' scales move from `from` to `to` times their own over the fade (not exactly zero: a zero-scale collider logs warnings).
    private IEnumerator Scale(Tree[] trees, Vector3[] full, float from, float to)
    {
        float seconds = Mathf.Max(_config.RankingBreakFadeSeconds, 0.01f);
        float elapsed = 0f;
        while (elapsed < seconds)
        {
            elapsed += Time.deltaTime;
            float t = Mathf.SmoothStep(0f, 1f, Mathf.Clamp01(elapsed / seconds));
            float factor = Mathf.Max(Mathf.Lerp(from, to, t), 0.001f);
            for (int i = 0; i < trees.Length; i++)
            {
                if (trees[i] != null)
                {
                    trees[i].transform.localScale = full[i] * factor;
                }
            }

            yield return null;
        }

        for (int i = 0; i < trees.Length; i++)
        {
            if (trees[i] != null)
            {
                trees[i].transform.localScale = full[i] * Mathf.Max(to, 0.001f);
            }
        }
    }

    private void RefreshClock()
    {
        if (_clockText != null)
        {
            int whole = Mathf.CeilToInt(SecondsLeft);
            _clockText.text = $"{whole / 60:D2}:{whole % 60:D2}";
        }
    }

    // The line at the top of the screen, the countdown under the main clock appear with a set's bushes: the countdown
    // is set to the set's full seconds first, so it never shows 00:00 or the last set's value, and everything fades in over the bushes' growth.
    private void ShowHud()
    {
        Canvas canvas = _harvestUI != null ? _harvestUI.GetComponent<Canvas>() : null;
        if (canvas == null)
        {
            return;
        }

        if (_hud == null)
        {
            _hud = new GameObject("RankingBreakHud", typeof(RectTransform), typeof(CanvasGroup));
            _hud.transform.SetParent(canvas.transform, false);
            _hudGroup = _hud.GetComponent<CanvasGroup>();
            _hudGroup.blocksRaycasts = false;
            _hudGroup.interactable = false;
            var rect = _hud.GetComponent<RectTransform>();
            rect.anchorMin = Vector2.zero;
            rect.anchorMax = Vector2.one;
            rect.offsetMin = Vector2.zero;
            rect.offsetMax = Vector2.zero;
            Color plate = new Color(0.06f, 0.067f, 0.09f, 0.55f);
            TextMeshProUGUI banner = UiStyle.Label(_hud.transform, "Banner", _config.RankingBreakText, 32f, TextAlignmentOptions.Center, new Vector2(0.5f, 1f), new Vector2(0.5f, 1f), Color.white);
            UiStyle.HudPlate(banner, new Vector2(0f, -64f), new Vector2(1100f, 64f), 32f, plate, "BannerPlate");
            _clockText = UiStyle.Label(_hud.transform, "Countdown", "", 46f, TextAlignmentOptions.Center, new Vector2(0f, 1f), new Vector2(0f, 1f), Color.white);
            UiStyle.HudPlate(_clockText, new Vector2(64f + 110f, -(44f + 34f + 76f)), new Vector2(220f, 68f), 46f, plate, "CountdownPlate");
        }

        SecondsLeft = _config.RankingBreakSeconds;
        RefreshClock();
        _hudGroup.alpha = 0f;
        _hud.SetActive(true);
        FadeHud(1f);
    }

    // Fades the line and the countdown to `target` (1 in, 0 out) over the fade seconds, alongside the bushes' growth or shrinking.
    private void FadeHud(float target)
    {
        if (_hud == null)
        {
            return;
        }

        if (_hudFade != null)
        {
            StopCoroutine(_hudFade);
        }

        _hudFade = StartCoroutine(FadeHudRoutine(target));
    }

    private IEnumerator FadeHudRoutine(float target)
    {
        float from = _hudGroup.alpha;
        float seconds = Mathf.Max(_config.RankingBreakFadeSeconds, 0.01f);
        float elapsed = 0f;
        while (elapsed < seconds)
        {
            elapsed += Time.deltaTime;
            _hudGroup.alpha = Mathf.Lerp(from, target, Mathf.Clamp01(elapsed / seconds));
            yield return null;
        }

        _hudGroup.alpha = target;
        if (target <= 0f)
        {
            _hud.SetActive(false);
        }

        _hudFade = null;
    }

    // The line and the countdown fade out.
    private void HideHud()
    {
        FadeHud(0f);
    }
}
