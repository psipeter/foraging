using System;
using System.Collections;
using UnityEngine;
using UnityEngine.Networking;

// One experiment's standing for the logged-in participant, as `participant-start` reports it (supabase/migrations/20261106000000_experiments.sql, server.menu).
[Serializable]
public class ExperimentStanding
{
    public string code;
    public string title;
    public int n_sessions;
    public string status;            // none, in_progress, finished, terminated
    public int sessions_done;
    public float points;             // the score of its completed sessions plus its Interlude bonuses, practice left out
    public bool unlocked;            // the prerequisites are finished (the server enforces it when the run starts)
}

[Serializable]
public class LoginReply
{
    public bool needs_consent;       // the server holds no consent of this version for the ID: sign, then log in again with the signature
    public string participant_id;
    public string token;
    public ExperimentStanding[] experiments;
}

// What `run-start` returns for an experiment: a run to play (a token, and a resume to continue where the participant stopped) or, for a
// finished experiment, its status and completion code.
[Serializable]
public class RunReply
{
    public string run_id;
    public string token;
    public string status;
    public string experiment;
    public bool has_resume;          // `resume` is a nested object, which JsonUtility cannot leave null: this says whether it was sent
    public ResumeReply resume;
    public string completion_code;
}

// The participant who is logged in, kept across the scene reloads between the menu and the game (the Boot scene is the menu). The login gives
// a participant token (the menu and starting runs); each experiment's run has its own token. Reset only when the player starts.
public static class ParticipantSession
{
    public static string ProlificId;
    public static string ConsentVersion;       // the consent text's version the game holds (null: no consent is asked)
    public static string ParticipantId;
    public static string Token;
    public static ExperimentStanding[] Standings;

    // The run the menu started, for DataPipeline to adopt when the game scene loads (null: no run, the game records locally only).
    public static RunReply PendingRun;

    public static bool LoggedIn => !string.IsNullOrEmpty(Token);

    [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.SubsystemRegistration)]
    private static void Reset()
    {
        ProlificId = ConsentVersion = ParticipantId = Token = null;
        Standings = null;
        PendingRun = null;
    }

    private static string BuildJson(BuildInfo build)
    {
        return Json.Obj(("commit", build?.commit), ("dirty", build != null ? (object)build.dirty : false),
            ("platform", Application.platform.ToString()), ("unity_version", Application.unityVersion));
    }

    // Logs the participant in (a returning ID gets a fresh token and the menu). `consent` is null for a participant who has signed this version
    // already or when no consent is asked; the reply says `needs_consent` when it is missing.
    public static IEnumerator Login(OnlineSettings settings, string pid, string consentVersion, ConsentRecord consent, Action<LoginReply> done, Action<string> failed)
    {
        string body = Json.Obj(("build", new Json.Raw(BuildJson(BuildInfo.Read()))), ("prolific_pid", pid),
            ("consent_version", consent == null ? consentVersion : null),
            ("consent", consent != null ? new Json.Raw(Json.Obj(("version", consent.version), ("signature", consent.signature), ("at", consent.at))) : null));
        yield return HttpSink.Call(settings.url, settings.apikey, "participant-start", System.Text.Encoding.UTF8.GetBytes(body), request =>
        {
            if (request.result != UnityWebRequest.Result.Success)
            {
                failed("The server did not accept this version of the game (" + HttpSink.Describe(request) + ").");
                return;
            }

            LoginReply reply = JsonUtility.FromJson<LoginReply>(request.downloadHandler.text);
            if (!reply.needs_consent)
            {
                ProlificId = pid;
                ConsentVersion = consentVersion;
                ParticipantId = reply.participant_id;
                Token = reply.token;
                Standings = reply.experiments ?? new ExperimentStanding[0];
            }

            done(reply);
        });
    }

    // Logs in again as the same participant: a new token and the menu as it stands now (after an experiment, or a return to the menu).
    public static IEnumerator Refresh(OnlineSettings settings, Action<LoginReply> done, Action<string> failed)
    {
        return Login(settings, ProlificId, ConsentVersion, null, done, failed);
    }

    // Starts (or continues) the participant's run of an experiment.
    // `expectedSessions`: the number of sessions (sessions and Interludes alike) of a reduced run (RunModes.ExpectedSessions); null for a full one.
    public static IEnumerator StartRun(OnlineSettings settings, string experiment, int? expectedSessions, Action<RunReply> done, Action<string> failed)
    {
        string body = expectedSessions.HasValue
            ? Json.Obj(("build", new Json.Raw(BuildJson(BuildInfo.Read()))), ("participant_id", ParticipantId), ("participant_token", Token), ("experiment", experiment),
                ("expected_sessions", expectedSessions.Value))
            : Json.Obj(("build", new Json.Raw(BuildJson(BuildInfo.Read()))), ("participant_id", ParticipantId), ("participant_token", Token), ("experiment", experiment));
        yield return HttpSink.Call(settings.url, settings.apikey, "run-start", System.Text.Encoding.UTF8.GetBytes(body), request =>
        {
            if (request.result != UnityWebRequest.Result.Success)
            {
                failed("The server did not start this experiment (" + HttpSink.Describe(request) + ").");
                return;
            }

            done(JsonUtility.FromJson<RunReply>(request.downloadHandler.text));
        });
    }

    // The participant's feedback on an experiment's run (the participant token authorizes it also after the run is finished).
    public static IEnumerator SendFeedback(OnlineSettings settings, string runId, string text, Action<bool> done)
    {
        byte[] body = System.Text.Encoding.UTF8.GetBytes(Json.Obj(("run_id", runId), ("token", Token), ("text", text)));
        yield return HttpSink.Call(settings.url, settings.apikey, "feedback", body, request => done(request.result == UnityWebRequest.Result.Success));
    }
}
