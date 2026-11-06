using System.Collections;
using UnityEngine;
using UnityEngine.InputSystem;
using UnityEngine.SceneManagement;

// The first scene of a build, and the experiment menu: the game returns here between experiments. It fetches the StreamingAssets files into memory in a
// browser (StreamingData), logs the participant in when the build uploads (online.json: the ID screen, the consent screen when the server holds no
// signature of this text's version, ConsentScreen), shows the menu of experiments (MenuScreen) and, for the one chosen, starts its run on the server
// and loads the game scene with that experiment's sessions (GameManager.BeginExperiment). In a browser a click then starts the pointer lock and the
// audio, which need a user gesture. It does not request fullscreen: changing the canvas size from inside the game left the picture black (real browser,
// and a headless reproduction); the participant may use the page's own fullscreen button.
// Without a server (the Editor, a lab build) the menu offers every experiment of the catalog; the Editor's Foraging > Experiments window, or -experiment
// <code> on a standalone build's command line, plays one without the menu.
public class Bootstrap : MonoBehaviour
{
    [SerializeField] private string gameScene = "SampleScene";

    private StatusScreen _status;
    private OnlineSettings _settings;
    private ExperimentCatalog _catalog;
    private bool _failed;

    private void Start()
    {
        StartCoroutine(Run());
    }

    private IEnumerator Run()
    {
        UiStyle.BootBackdrop();
        _status = StatusScreen.Show();
        if (StreamingData.NeedsPreload)
        {
            if (!StreamingData.Loaded)
            {
                string failure = null;
                _status.Set("Foraging study", "Loading", "Getting the game ready.", 0f);
                yield return StreamingData.Preload(p => _status.Set("Foraging study", "Loading", "Getting the game ready.", p), reason => failure = reason);
                if (failure != null)
                {
                    Fail(failure);
                    yield break;
                }
            }

            if (FindAnyObjectByType<PointerLockGuard>() == null)
            {
                var guard = new GameObject("PointerLockGuard", typeof(PointerLockGuard));
                DontDestroyOnLoad(guard);
            }

            PointerLockGuard.Suspended = true;       // the menu needs the mouse
        }

        Music.PlayMenu();                                                // a browser starts the sound at the first click
        _settings = OnlineSettings.Load();
        _catalog = ExperimentCatalog.Load();
        if (_catalog == null)
        {
            Debug.LogWarning("Bootstrap: no Resources/ExperimentCatalog asset; playing the scene's default experiment.");
            SceneManager.LoadScene(gameScene);
            yield break;
        }

        string direct = _settings.Active ? null : DirectExperiment();
        if (direct != null)
        {
            ExperimentConfig chosen = _catalog.Find(direct);
            if (chosen == null)
            {
                _status.Set("Foraging study", "No such experiment", $"There is no experiment \"{direct}\" in the catalog.");
                yield break;
            }

            yield return Begin(chosen);
            yield break;
        }

        if (_settings.Active)
        {
            yield return ParticipantSession.LoggedIn ? Refresh() : LogIn();
            if (_failed)
            {
                yield break;
            }
        }

        while (true)
        {
            _status.Hide();
            MenuScreen menu = _settings.Active
                ? MenuScreen.Show(MenuScreen.OnlineRows(ParticipantSession.Standings, _catalog), "Signed in as " + ParticipantSession.ProlificId, "")
                : MenuScreen.Show(MenuScreen.OfflineRows(_catalog), "No data server: the data is saved on this computer only.", "");
            yield return new WaitUntil(() => menu.Done);
            ExperimentConfig experiment = _catalog.Find(menu.ChosenCode);

            if (!_settings.Active)
            {
                yield return Begin(experiment);
                yield break;
            }

            _status.Set("Foraging study", "Connecting", "Reaching the server.");
            RunReply run = null;
            string error = null;
            yield return ParticipantSession.StartRun(_settings, menu.ChosenCode, r => run = r, e => error = e);
            if (error != null)
            {
                Fail(error);
                yield break;
            }

            if (run.status == "in_progress" && !string.IsNullOrEmpty(run.token) && experiment != null)
            {
                ParticipantSession.PendingRun = run;
                yield return Begin(experiment);
                yield break;
            }

            if (run.status == "finished")
            {
                yield return ShowCompleted(menu.ChosenCode, run);
            }

            yield return Refresh();
            if (_failed)
            {
                yield break;
            }
        }
    }

    // The ID screen, then (when the server has no signature of the consent text's version for that ID) the consent screen.
    private IEnumerator LogIn()
    {
        // A browser build asks for consent; a lab build with an ID on its command line does not (and skips the ID screen).
        string version = StreamingData.NeedsPreload && StreamingData.Exists(ConsentScreen.File) ? ConsentScreen.ReadVersion() : null;
        string pid = _settings.prolificPid;
        if (StreamingData.NeedsPreload || string.IsNullOrEmpty(pid))
        {
            _status.Hide();
            ConsentScreen idScreen = ConsentScreen.ShowId(pid);
            yield return new WaitUntil(() => idScreen.Done);
            pid = idScreen.ParticipantId;
        }

        _status.Set("Foraging study", "Connecting", "Reaching the server.");
        LoginReply reply = null;
        string error = null;
        yield return ParticipantSession.Login(_settings, pid, version, null, r => reply = r, e => error = e);
        if (error == null && reply.needs_consent)
        {
            _status.Hide();
            ConsentScreen consentScreen = ConsentScreen.ShowConsent();
            yield return new WaitUntil(() => consentScreen.Done);
            _status.Set("Foraging study", "Connecting", "Reaching the server.");
            yield return ParticipantSession.Login(_settings, pid, version, consentScreen.Consent, r => reply = r, e => error = e);
        }

        if (error == null && !ParticipantSession.LoggedIn)
        {
            error = "The server did not log you in.";
        }

        Failed(error);
    }

    // After an experiment, or a view of a finished one: log in again for a fresh token and the menu as it stands now.
    private IEnumerator Refresh()
    {
        _status.Set("Foraging study", "Connecting", "Reaching the server.");
        string error = null;
        yield return ParticipantSession.Refresh(_settings, r => { }, e => error = e);
        Failed(error);
    }

    private void Failed(string error)
    {
        if (error != null)
        {
            Fail(error);
            _failed = true;
        }
    }

    private void Fail(string reason)
    {
        _status.Set("Something went wrong", "We could not continue", reason + "\n\nPlease reload the page. If this continues, contact the researcher.");
    }

    // The completion code of a finished experiment, with the optional feedback box and the way back (to Prolific, and to the menu).
    private IEnumerator ShowCompleted(string code, RunReply run)
    {
        string title = code;
        foreach (ExperimentStanding s in ParticipantSession.Standings)
        {
            if (s.code == code)
            {
                title = s.title;
            }
        }

        ExperimentConfig config = _catalog.Find(code);
        bool counts = config == null || config.CountsTowardTotal;
        float points = 0f;
        foreach (ExperimentStanding s in ParticipantSession.Standings)
        {
            if (s.code == code)
            {
                points = s.points;
            }
        }

        bool back = false;
        CompletionScreen screen = null;
        screen = CompletionScreen.Show(title, counts ? points : (float?)null, run.completion_code, OnlineSettings.UrlParameter("PROLIFIC_PID") != null,
            text => StartCoroutine(ParticipantSession.SendFeedback(_settings, run.run_id, text, ok =>
                screen.SetStatus(ok ? "Thank you, your feedback was saved." : "Your feedback could not be sent. You can try again.", false))),
            () => DataPipeline.OpenProlificCompletion(run.completion_code), () => back = true);
        yield return new WaitUntil(() => back);
        Destroy(screen.gameObject);
    }

    // The game scene with the experiment's sessions. In a browser, first a click: pointer lock and audio need a user gesture, and this is the one that starts them.
    private IEnumerator Begin(ExperimentConfig experiment)
    {
        GameManager.BeginExperiment(experiment);
        Music.Stop();
        if (StreamingData.NeedsPreload)
        {
            // The experiment's files (its worlds, Interlude files and instruction texts) are fetched now, not with the common ones at the start.
            string failure = null;
            _status.Set("Getting ready", experiment.Title, "Loading the worlds for this experiment.", 0f);
            yield return StreamingData.Fetch(experiment.FilesToStart(), p => _status.Set("Getting ready", experiment.Title, "Loading the worlds for this experiment.", p), reason => failure = reason);
            if (failure != null)
            {
                Fail(failure);
                yield break;
            }

            _status.Set("Ready", experiment.Title, "The mouse will be captured by the game. Press [Escape] to release it.".Replace("[Escape]", UiStyle.Chip("Escape")), -1f, "[Click] anywhere to begin");
            yield return null;
            yield return new WaitUntil(() => Mouse.current != null && Mouse.current.leftButton.wasPressedThisFrame);

            Cursor.lockState = CursorLockMode.Locked;
            PointerLockGuard.Suspended = false;
        }

        SceneManager.LoadScene(gameScene);
    }

    // The experiment to play without the menu: the Editor's Foraging > Experiments window (an EditorPref) or -experiment <code> on a standalone build.
    private static string DirectExperiment()
    {
#if UNITY_EDITOR
        string code = UnityEditor.EditorPrefs.GetString("Foraging.Experiment", "");
        if (!string.IsNullOrEmpty(code))
        {
            return code;
        }
#endif
        string[] args = System.Environment.GetCommandLineArgs();
        for (int i = 0; i + 1 < args.Length; i++)
        {
            if (args[i] == "-experiment")
            {
                return args[i + 1];
            }
        }

        return null;
    }
}
