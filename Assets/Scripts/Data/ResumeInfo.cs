using System;

// What the server returns from run-start when the participant is coming back to an unfinished run (the `resume` object of
// supabase/migrations/20261030000000_resume_state.sql): flat, no nulls, so JsonUtility can read it.
[Serializable]
public class PoseReply
{
    public double t;
    public float x, z, yaw, pitch;
    public int keys;
}

[Serializable]
public class TreeCount
{
    public int tree;
    public int n;
}

[Serializable]
public class TrialTally
{
    public int correct;
    public float bonus;
}

[Serializable]
public class PreviousSession
{
    public int index;
    public bool is_practice;
    public bool is_interlude;
    public float score;
}

[Serializable]
public class InterludeTotals
{
    public int trials;
    public int correct;
    public float bonus;
}

[Serializable]
public class ResumeReply
{
    public int session_index;
    public string name;
    public bool is_practice;
    public bool is_interlude;
    public bool completed;                  // the latest session was finished: continue with the next one
    public float final_score;
    public string started_at;
    public bool has_pose;
    public PoseReply pose;
    public double last_event_t;
    public double clock;                    // the session clock to continue from (later than every stored frame and event)
    public float running_total;
    public TreeCount[] fruits_taken;        // fruits already taken per bush
    public int open_bout_tree;              // the bush being harvested when the data stops, or -1
    public int[] interlude_plan;
    public TrialTally[] trial_rows;         // the current Interlude's finished trials
    public PreviousSession[] previous;      // completed sessions, for the running totals
    public InterludeTotals previous_interlude;
    public double gap_seconds;              // how long ago the server last heard from the participant
    public int events_next, trajectory_next, trials_next;
}

// The server's state for the session about to start, held between the scene reload that DataPipeline triggers and the
// components that restore it (DataLogger, InterludeManager, InstructionsPanel); cleared once applied.
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
