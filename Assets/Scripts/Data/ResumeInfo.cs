using System;

// What the server returns from run-start when the participant is coming back to an unfinished run (the `resume` object of
// supabase/migrations/20261030000000_resume_state.sql): flat, no nulls, so JsonUtility can read it.
[Serializable]
public class PoseReply
{
    public double t;
    public float x, z, yaw, pitch;
}

[Serializable]
public class TreeCount
{
    public int tree;
    public int n;
}

[Serializable]
public class PreviousSession
{
    public bool is_practice;
    public float foraging_points;
    public float ranking_points;
}

[Serializable]
public class ResumeReply
{
    public int session_index;
    public bool completed;                  // the latest session was finished: continue with the next one
    public string started_at;
    public bool has_pose;
    public PoseReply pose;
    public double clock;                    // the session clock to continue from (later than every stored frame and event)
    public double held_seconds;             // of it, the seconds the session clock was held in selection breaks (the foraging clock continues from clock - held_seconds)
    public int breaks;                      // the number of the last selection break begun (a break played again after an interruption keeps its number)
    public int open_break;                  // the number of the break the data stops inside, 0 when none (docs/ONLINE_DATA_PLAN.md, "Selection breaks")
    public int open_break_leaving;          // the patch leaving it came at
    public int open_break_sets_done;        // how many of its sets were scored
    public bool open_break_end_logged;      // the break's aborted end is already in the log (a second reload before it was played again): do not log another
    public int leavings;                    // the patch leavings counted so far (rank_leaving events): the selection schedule continues from it
    public bool leaving_due;                // the last leaving made a selection due that had not begun
    public string[] hints_shown;            // the ids of the tutorial hints already shown in the session (not shown again)
    public int sets_played;                 // selection sets shown so far, counting the tries that were interrupted (the pool continues from sets_next, the scored ones)
    public float ranking_points;            // the points paid by the selection sets so far (0 in a practice session)
    public int ranking_pairs;               // the correct pairs of the selection sets so far: with the bonus per pair, what they were worth, which the end screen shows
    public float running_total;
    public TreeCount[] fruits_taken;        // fruits already taken per bush
    public int open_bout_tree;              // the bush being harvested when the data stops, or -1
    public PreviousSession[] previous;      // completed sessions, for the running totals
    public double gap_seconds;              // how long ago the server last heard from the participant
    public int events_next, trajectory_next, sets_next;
}

// The server's state for the session about to start, held between the scene reload that DataPipeline triggers and the
// components that restore it (DataLogger, InstructionsPanel); cleared once applied.
public static class ResumeInfo
{
    public static ResumeReply Pending;

    // True when `sessionIndex` is the unfinished session to continue (not the start of a fresh one).
    public static bool MidSession(int sessionIndex)
    {
        return Pending != null && !Pending.completed && Pending.session_index == sessionIndex;
    }

    [UnityEngine.RuntimeInitializeOnLoadMethod(UnityEngine.RuntimeInitializeLoadType.SubsystemRegistration)]
    private static void Reset()
    {
        Pending = null;
    }
}
