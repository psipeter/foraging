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
    [Tooltip("The menu's Payment column, in dollars: what completing the experiment pays. Shown as \"$a to finish +\". 0 here and in the bonus: a dash. The menu only displays it (Prolific pays): it must match the study page.")]
    [SerializeField] private float paymentFinish = 0f;
    [Tooltip("The bonus in dollars for each `paymentBonusPoints` points earned (shown as \"$b per 100 points\").")]
    [SerializeField] private float paymentBonus = 0f;
    [Tooltip("The points one bonus amount is paid for.")]
    [SerializeField] private float paymentBonusPoints = 100f;

    public string Code => code;
    public string Title => title;
    public IReadOnlyList<string> Requires => requires;
    public List<SessionConfig> Sessions => sessions;

    public int SessionCount => sessions.Count;
    public bool CountsTowardTotal => countsTowardTotal;
    public float TypicalPoints => typicalPoints;
    public float PaymentFinish => paymentFinish;
    public float PaymentBonus => paymentBonus;
    public float PaymentBonusPoints => paymentBonusPoints;


    // The minutes the menu quotes: the stated estimate, else MinutesOf the sessions.
    public float EstimatedMinutes => estimatedMinutes > 0f ? estimatedMinutes : MinutesOf(sessions, 1f);

    // The foraging time of the sessions, `shortFactor` as RunModes.Short applies it, rounded to the nearest minute (at least 1). Selection time is left out (PI, 2026-11-19): how many
    // patch leavings there are and how fast the participant ranks is too variable to estimate, so the quote undershoots the true time a little.
    public static float MinutesOf(IList<SessionConfig> list, float shortFactor)
    {
        float seconds = 0f;
        foreach (SessionConfig session in list)
        {
            seconds += SessionSeconds(session, shortFactor);
        }

        return Mathf.Max(1f, Mathf.Round(seconds / 60f));
    }

    // A session's foraging time. The menu's bar and time left are measured against it.
    private static float SessionSeconds(SessionConfig session, float shortFactor)
    {
        return session == null ? 0f : RunModes.SessionSeconds(session, shortFactor);
    }

    // The share of an experiment's foraging time a run has behind it: its finished sessions in full, and the session under way by its foraging clock.
    public static float Progress(IList<SessionConfig> list, int sessionsDone, float foragingSeconds, float shortFactor)
    {
        float total = 0f;
        foreach (SessionConfig session in list)
        {
            total += SessionSeconds(session, shortFactor);
        }

        return total > 0f ? Mathf.Clamp01(1f - SecondsLeft(list, sessionsDone, foragingSeconds, shortFactor) / total) : 0f;
    }

    // The foraging seconds a run still needs, for the menu's "time left": the foraging time of every session not finished, less what the session under way has behind it.
    public static float SecondsLeft(IList<SessionConfig> list, int sessionsDone, float foragingSeconds, float shortFactor)
    {
        float seconds = 0f;
        for (int i = Mathf.Max(sessionsDone, 0); i < list.Count; i++)
        {
            if (list[i] == null)
            {
                continue;
            }

            float most = SessionSeconds(list[i], shortFactor);
            seconds += i == sessionsDone ? Mathf.Max(most - Mathf.Max(foragingSeconds, 0f), 0f) : most;
        }

        return seconds;
    }

    // The StreamingAssets files a session reads: its world, its selection pool and its instruction text.
    public static List<string> FilesOf(SessionConfig session)
    {
        var files = new List<string>();
        if (session == null)
        {
            return files;
        }

        files.Add(WorldData.PathFor(session));
        if (session.SelectionEvery > 0 || session.SelectionTimes.Length > 0)
        {
            files.Add(WorldData.SelectionPoolPathFor(session));
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
