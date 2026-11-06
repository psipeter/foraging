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

    public string Code => code;
    public string Title => title;
    public IReadOnlyList<string> Requires => requires;
    public List<SessionConfig> Sessions => sessions;
    public bool CountsTowardTotal => countsTowardTotal;

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
