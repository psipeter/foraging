using System;
using System.Collections.Generic;
using System.Globalization;
using UnityEngine;

// Reduced runs, for development: two independent knobs that shorten what a participant plays so that the whole path (the sessions, the finish
// screen, the menu round trip, the loading bar) can be tested in minutes.
//   short   0 to 1: every session lasts this fraction of its length (at least MinSessionSeconds). 1 = as designed.
//   repeats 1 or more: an experiment's sessions that repeat a cell (the design record's `iteration`) are played only up to this iteration;
//           more than any iteration that exists = everything. A session without an iteration always plays.
// Set in the Editor's Foraging > Experiments window (EditorPrefs, kept between runs), as ?short=0.3&repeats=1 in the address of a browser development build or as
// -short 0.3 -repeats 1 on a standalone development build. A release build ignores all of it: a link must not be able to shorten a participant's run.
// A run with fewer sessions than the experiment lists declares its count at run-start (ExpectedSessions), which only a development release may do; the server
// then lets it finish. The knobs are logged in a run_modes event after each session's start.
public static class RunModes
{
    public const float MinSessionSeconds = 10f;

    public const string ShortKey = "Foraging.Short";
    public const string RepeatsKey = "Foraging.Repeats";
    public const int AllRepeats = 99;                                  // the Editor window's default: more than any experiment repeats

    [Serializable]
    private class Design
    {
        public int iteration;
    }

    private static bool Allowed => Application.isEditor || Debug.isDebugBuild;

    // The value of an address parameter or command-line option (WebGL: ?name=; elsewhere: -name value); null when absent.
    private static string Raw(string name)
    {
        if (Application.platform == RuntimePlatform.WebGLPlayer)
        {
            return OnlineSettings.UrlParameter(name);
        }

        string[] args = Environment.GetCommandLineArgs();
        for (int i = 0; i + 1 < args.Length; i++)
        {
            if (args[i] == "-" + name)
            {
                return args[i + 1];
            }
        }

        return null;
    }

    // The fraction of each session's length to play (1 = all).
    public static float Short
    {
        get
        {
            if (!Allowed)
            {
                return 1f;
            }
#if UNITY_EDITOR
            return Mathf.Clamp01(UnityEditor.EditorPrefs.GetFloat(ShortKey, 1f));
#else
            return float.TryParse(Raw("short"), NumberStyles.Float, CultureInfo.InvariantCulture, out float f) ? Mathf.Clamp01(f) : 1f;
#endif
        }
    }

    // The highest iteration of a repeated cell to play (int.MaxValue = all).
    public static int Repeats
    {
        get
        {
            if (!Allowed)
            {
                return int.MaxValue;
            }
#if UNITY_EDITOR
            int n = UnityEditor.EditorPrefs.GetInt(RepeatsKey, AllRepeats);
#else
            int n = int.TryParse(Raw("repeats"), NumberStyles.Integer, CultureInfo.InvariantCulture, out int r) ? r : int.MaxValue;
#endif
            return n < 1 ? 1 : n;
        }
    }

    public static bool Active => Short < 1f || Repeats < AllRepeats;

    // A session's length with the factor applied (the session as designed at 1).
    public static float SessionSeconds(SessionConfig session, float factor)
    {
        return factor >= 1f ? session.SessionDuration : Mathf.Max(MinSessionSeconds, session.SessionDuration * factor);
    }

    // The iteration of the cell a session plays (1 when its design record has none).
    private static int Iteration(SessionConfig session)
    {
        if (string.IsNullOrEmpty(session.DesignJson))
        {
            return 1;
        }

        try
        {
            return Mathf.Max(1, JsonUtility.FromJson<Design>(session.DesignJson).iteration);
        }
        catch (ArgumentException)
        {
            return 1;
        }
    }

    // The sessions to play from an experiment's list, in their order: the repeats knob applied.
    public static List<SessionConfig> Apply(IList<SessionConfig> sessions)
    {
        int repeats = Repeats;
        var played = new List<SessionConfig>();
        foreach (SessionConfig session in sessions)
        {
            if (session == null || Iteration(session) <= repeats)
            {
                played.Add(session);
            }
        }

        return played;
    }

    // What run-start declares: the number of sessions of a run that has fewer than the experiment lists; null for a full run.
    public static int? ExpectedSessions(IList<SessionConfig> sessions)
    {
        int count = Apply(sessions).Count;
        return count < sessions.Count ? count : (int?)null;
    }

    // The payload of the run_modes event; null when nothing is reduced.
    public static string Payload()
    {
        return Active ? Json.Obj(("short", Short), ("repeats", Repeats == int.MaxValue ? AllRepeats : Repeats)) : null;
    }
}
