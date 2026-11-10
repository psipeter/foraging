using System.Collections.Generic;
using UnityEngine;

// One experiment: a titled progression of sessions (practice sessions, sessions and their Interludes, in play order). The game's menu lists the
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
    [Tooltip("The sessions in play order, each followed by its Interlude where it has one. Every session's asset name starts with the code and an underscore.")]
    [SerializeField] private List<SessionConfig> sessions = new List<SessionConfig>();
    [Tooltip("Whether the points earned here are added to the total the menu and the completion screens show. Off for a tutorial or other practice, whose points pay nothing.")]
    [SerializeField] private bool countsTowardTotal = true;

    [Header("What the menu tells participants before they start")]
    [Tooltip("How long the experiment takes, in minutes. 0: worked out from the sessions (their durations plus each Interlude's trials at their time limit, plus a short allowance for the instruction screens). Replace by the measured median once pilot data exist.")]
    [SerializeField] private float estimatedMinutes = 0f;
    [Tooltip("The points a typical participant earns in it (shown as \"~N\"). 0: not known, shown as a dash. PLACEHOLDER until pilot data exist.")]
    [SerializeField] private float typicalPoints = 0f;

    public string Code => code;
    public string Title => title;
    public IReadOnlyList<string> Requires => requires;
    public List<SessionConfig> Sessions => sessions;

    // What participants count: sessions, not their Interludes (each session is Part A, its Interlude Part B).
    public int SessionCount
    {
        get
        {
            int count = 0;
            foreach (SessionConfig session in sessions)
            {
                count += session != null && session.IsInterlude ? 0 : 1;
            }

            return count;
        }
    }
    public bool CountsTowardTotal => countsTowardTotal;
    public float TypicalPoints => typicalPoints;

    private const float InstructionSecondsPerPart = 20f;       // reading the instructions of a session or an Interlude
    private const float RoundMinutesTo = 5f;

    // The minutes the menu quotes: the stated estimate, else the time the sessions and Interludes take at most, rounded to 5 minutes.
    public float EstimatedMinutes
    {
        get
        {
            if (estimatedMinutes > 0f)
            {
                return estimatedMinutes;
            }

            float seconds = 0f;
            foreach (SessionConfig session in sessions)
            {
                if (session != null)
                {
                    seconds += InstructionSecondsPerPart + (session.IsInterlude ? session.InterludeTrialCount * session.InterludeTrialSeconds : session.SessionDuration);
                }
            }

            return Mathf.Max(RoundMinutesTo, Mathf.Round(seconds / 60f / RoundMinutesTo) * RoundMinutesTo);
        }
    }

    // The StreamingAssets files a session reads: its world, its Interlude file and its instruction text.
    public static List<string> FilesOf(SessionConfig session)
    {
        var files = new List<string>();
        if (session == null)
        {
            return files;
        }

        files.Add(WorldData.PathFor(session));
        if (session.IsInterlude)
        {
            files.Add(WorldData.InterludePathFor(session));
        }

        if (!string.IsNullOrEmpty(session.InstructionsFile))
        {
            files.Add(session.InstructionsFile);
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
