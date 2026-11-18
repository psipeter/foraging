using System.Collections.Generic;
using UnityEngine;

// One experiment: a titled progression of sessions (sessions, in play order). The game's menu lists the
// experiments; the one chosen supplies GameManager's session list. `code` is the prefix of every asset and generated file of the experiment
// (CF_S1.asset, CF_I1.asset, Experiments/CF/CF_S1_seed201.world) and the experiment's key in the online database; `title` is what participants read.
// A title can change at any time (and its database row with it); changing the code means renaming the assets and generated files and the database rows.
[CreateAssetMenu(fileName = "Experiment", menuName = "Foraging/Experiment", order = 0)]
public class ExperimentConfig : ScriptableObject
{
    [Tooltip("Short key: the prefix of the experiment's assets and the folder of its generated files (Assets/StreamingAssets/Experiments/<code>/). Letters and digits only.")]
    [SerializeField] private string code = "";
    [Tooltip("The name the menu shows.")]
    [SerializeField] private string title = "";
    [Tooltip("Experiment codes a participant must have finished before this one unlocks (also enforced by the server).")]
    [SerializeField] private string[] requires = new string[0];
    [Tooltip("The sessions in play order. Every session's asset name starts with the code and an underscore.")]
    [SerializeField] private List<SessionConfig> sessions = new List<SessionConfig>();
    [Tooltip("Whether the points earned here are added to the total the menu and the completion screens show. Off for a tutorial or other practice, whose points pay nothing.")]
    [SerializeField] private bool countsTowardTotal = true;

    [Header("What the menu tells participants before they start")]
    [Tooltip("How long the experiment takes, in minutes. 0: worked out from the sessions (their durations plus a short allowance for the instruction screens). Replace by the measured median once pilot data exist.")]
    [SerializeField] private float estimatedMinutes = 0f;
    [Tooltip("The points a typical participant earns in it (shown as \"~N\"). 0: not known, shown as a dash. PLACEHOLDER until pilot data exist.")]
    [SerializeField] private float typicalPoints = 0f;

    public string Code => code;
    public string Title => title;
    public IReadOnlyList<string> Requires => requires;
    public List<SessionConfig> Sessions => sessions;

    public int SessionCount => sessions.Count;
    public bool CountsTowardTotal => countsTowardTotal;
    public float TypicalPoints => typicalPoints;


    // The minutes the menu quotes: the stated estimate, else MinutesOf the sessions.
    public float EstimatedMinutes => estimatedMinutes > 0f ? estimatedMinutes : MinutesOf(sessions, 1f);

    // The time the sessions take at most (SessionSecondsAtMost: foraging time plus the rankings), `shortFactor` as RunModes.Short applies it, rounded to the nearest minute (at least 1).
    public static float MinutesOf(IList<SessionConfig> list, float shortFactor)
    {
        float seconds = 0f;
        foreach (SessionConfig session in list)
        {
            seconds += SessionSecondsAtMost(session, shortFactor);
        }

        return Mathf.Max(1f, Mathf.Round(seconds / 60f));
    }

    // A session's time at most: its foraging time plus its rankings at their longest. The menu's bar and time left are measured against it.
    public static float SessionSecondsAtMost(SessionConfig session, float shortFactor)
    {
        return session == null ? 0f : RunModes.SessionSeconds(session, shortFactor) + RankingSecondsAtMost(session);
    }

    // The ranking sets of a session at their longest: every ranking on the schedule (SessionConfig.rankingLeavings; with no schedule the estimate `rankingEstimate`, since how many
    // leavings there will be is not known), each set its full countdown. The breaks hold the session clock, so they come on top of the session's length.
    public static float RankingSecondsAtMost(SessionConfig session)
    {
        if (session == null || session.RankingEvery <= 0)
        {
            return 0f;
        }

        int rankings = session.RankingLeavings.Length > 0 ? session.RankingLeavings.Length : session.RankingEstimate;
        return rankings * session.RankingSets * session.RankingSeconds;
    }

    // How much of a session's maximum time is behind a participant who has `foragingSeconds` on the foraging clock and `rankings` rankings ended: the foraging seconds (at most the
    // session's length) plus each ranking at its full countdown (RankingSets x RankingSeconds; the time of a ranking is counted when it ends).
    private static float SecondsDone(SessionConfig session, float shortFactor, float foragingSeconds, int rankings)
    {
        float ranking = session.RankingEvery > 0 ? Mathf.Min(rankings * session.RankingSets * session.RankingSeconds, RankingSecondsAtMost(session)) : 0f;
        return Mathf.Min(Mathf.Max(foragingSeconds, 0f), RunModes.SessionSeconds(session, shortFactor)) + ranking;
    }

    // The share of an experiment's maximum time (the sum of SessionSecondsAtMost) a run has behind it: its finished sessions in full, and the session under way as SecondsDone.
    public static float Progress(IList<SessionConfig> list, int sessionsDone, float foragingSeconds, int rankings, float shortFactor)
    {
        float total = 0f, done = 0f;
        for (int i = 0; i < list.Count; i++)
        {
            float most = SessionSecondsAtMost(list[i], shortFactor);
            total += most;
            done += i < sessionsDone ? most : i == sessionsDone && list[i] != null ? Mathf.Min(SecondsDone(list[i], shortFactor, foragingSeconds, rankings), most) : 0f;
        }

        return total > 0f ? Mathf.Clamp01(done / total) : 0f;
    }

    // The seconds a run still needs at most, for the menu's "time left": the maximum time of every session not finished, less what the session under way has behind it.
    public static float SecondsLeft(IList<SessionConfig> list, int sessionsDone, float foragingSeconds, int rankings, float shortFactor)
    {
        float seconds = 0f;
        for (int i = Mathf.Max(sessionsDone, 0); i < list.Count; i++)
        {
            if (list[i] == null)
            {
                continue;
            }

            float most = SessionSecondsAtMost(list[i], shortFactor);
            seconds += i == sessionsDone ? Mathf.Max(most - SecondsDone(list[i], shortFactor, foragingSeconds, rankings), 0f) : most;
        }

        return seconds;
    }

    // The StreamingAssets files a session reads: its world, its ranking pool and its instruction text.
    public static List<string> FilesOf(SessionConfig session)
    {
        var files = new List<string>();
        if (session == null)
        {
            return files;
        }

        files.Add(WorldData.PathFor(session));
        if (session.RankingEvery > 0)
        {
            files.Add(WorldData.RankingPoolPathFor(session));
        }

        if (!string.IsNullOrEmpty(session.InstructionsFile))
        {
            files.Add(session.InstructionsFile);
        }

        if (!string.IsNullOrEmpty(session.HintsFile))
        {
            files.Add(session.HintsFile);
        }

        return files;
    }

    // The files to have before the experiment starts: every session's (the browser downloads them when the experiment is chosen).
    public List<string> FilesToStart()
    {
        var files = new List<string>();
        for (int i = 0; i < sessions.Count; i++)
        {
            files.AddRange(FilesOf(sessions[i]));
        }

        return files;
    }
}
