using UnityEngine;
using UnityEngine.InputSystem;
using UnityEngine.SceneManagement;
using TMPro;

public class SessionTimerUI : MonoBehaviour
{
    [SerializeField] private TextMeshProUGUI timerText;
    [SerializeField] private SunController sunController;
    public SessionConfig sessionConfig;
    public InterludeManager interludeManager;
    // The scene's own end-of-part panel and texts are not used any more (the score screen is built in code, UI/ScoreScreen.cs) and stay hidden.
    [SerializeField] private GameObject sessionEndPanel;
    [SerializeField] private TextMeshProUGUI finalScoreText;
    [SerializeField] private TextMeshProUGUI sessionCompleteText;
    [SerializeField] private TextMeshProUGUI nextSessionPromptText;

    [Header("Timer display")]
    [SerializeField] private float timerFontSize = 32f;
    [SerializeField] private Vector2 timerPosition = new Vector2(150f, -44f);
    [SerializeField] private Vector2 timerPlateSize = new Vector2(230f, 60f);
    [SerializeField] private Color plateColor = new Color(0f, 0f, 0f, 0.38f);

    private float _lastTotalScore;
    private bool _sessionEndHandled;
    private bool _leaveRequested;
    private ScoreScreen _score;
    private UnityEngine.UI.Image _timerPlate;
    private Color _plateIdle;
    private Color _textIdle;

    private void Awake()
    {
        if (sessionEndPanel != null)
        {
            sessionEndPanel.SetActive(false);
        }
    }

    private void Start()
    {
        if (timerText == null)
        {
            return;
        }

        // upper left, a pill 64 from the corner (the serialized position, size and colour are the old rectangle's and no longer used)
        UiStyle.HudPlate(timerText, new Vector2(64f + 110f, -(44f + 34f)), new Vector2(220f, 68f), 46f, new Color(0.06f, 0.067f, 0.09f, 0.55f), "TimerPlate");
        Transform plate = timerText.transform.parent.Find("TimerPlate");
        _timerPlate = plate != null ? plate.GetComponent<UnityEngine.UI.Image>() : null;
        _plateIdle = _timerPlate != null ? _timerPlate.color : Color.clear;
        _textIdle = timerText.color;
    }

    // The session clock is held (a ranking break): the plate and digits dim; false puts them back.
    public void SetPaused(bool paused)
    {
        if (timerText == null)
        {
            return;
        }

        if (_timerPlate != null)
        {
            _timerPlate.color = paused ? new Color(_plateIdle.r, _plateIdle.g, _plateIdle.b, _plateIdle.a * 0.5f) : _plateIdle;
        }

        timerText.color = paused ? new Color(0.72f, 0.72f, 0.72f, 0.6f) : _textIdle;
    }

    private void OnEnable()
    {
        SunController.OnSessionEnd += HandleSessionEnd;
        HarvestManager.OnScoreChanged += HandleScoreChanged;
    }

    private void OnDisable()
    {
        SunController.OnSessionEnd -= HandleSessionEnd;
        HarvestManager.OnScoreChanged -= HandleScoreChanged;
    }

    private void Update()
    {
        if (timerText == null || sunController == null || sessionConfig == null)
        {
            return;
        }

        if (sunController.SessionComplete)
        {
            timerText.text = "00:00";

            if (_score != null)
            {
                // Space is reserved for harvesting, so screens advance with Enter only.
                if (Keyboard.current != null &&
                    (Keyboard.current.enterKey.wasPressedThisFrame ||
                     Keyboard.current.numpadEnterKey.wasPressedThisFrame))
                {
                    _leaveRequested = true;
                }

                // A request made while data was still being saved stands: the participant is not asked to press Enter a second time.
                if (_leaveRequested)
                {
                    // Leave only once the server has stored everything (otherwise a "saving" screen shows until it has); after the last
                    // session the run is also closed on the server.
                    if (GameManager.IsLastSession ? !DataPipeline.TryFinish() : !DataPipeline.TryLeave())
                    {
                        return;
                    }

                    _leaveRequested = false;
                    if (GameManager.IsLastSession)
                    {
                        if (DataPipeline.IsOnline)
                        {
                            DataPipeline.ShowStudyComplete();       // the completion code, feedback, and the way back to the experiment menu
                        }
                        else
                        {
                            DataPipeline.ReturnToMenu();
                        }
                    }
                    else
                    {
                        GameManager.AdvanceSession();
                        SceneManager.LoadScene(SceneManager.GetActiveScene().name);
                    }
                }
            }

            return;
        }

        // An Interlude shows the trial's countdown (whole seconds, rounded up) instead of the session clock.
        float remaining = sessionConfig.IsInterlude && interludeManager != null && interludeManager.Active
            ? Mathf.Ceil(interludeManager.TrialSecondsLeft)
            : Mathf.Max(0f, sunController.SessionTimeRemaining);

        int minutes = Mathf.FloorToInt(remaining / 60f);
        int seconds = Mathf.FloorToInt(remaining % 60f);

        timerText.text = $"{minutes:D2}:{seconds:D2}";
    }

    private void HandleScoreChanged(float runningTotal)
    {
        _lastTotalScore = runningTotal;
    }

    private void HandleSessionEnd()
    {
        if (_sessionEndHandled)
        {
            return;
        }
        _sessionEndHandled = true;

        // Freeze player and disable input.
        PlayerController player = FindFirstObjectByType<PlayerController>();
        if (player != null)
        {
            player.SetFrozen(true);
            PlayerInput input = player.GetComponent<PlayerInput>();
            if (input != null)
            {
                input.enabled = false;
            }
        }

        bool isInterlude = sessionConfig != null && sessionConfig.IsInterlude;

        // An Interlude's points appear only on its end screen, never trial by trial (the practice Interlude shows what it would have paid, and never which
        // choices were right). The totals are on the experiment's completion screen, after the last of these.
        float points = isInterlude ? (interludeManager != null ? interludeManager.Points : 0f) : _lastTotalScore + RankingBreak.Points;       // (a ranking break's hidden bonus shows only here)
        _score = ScoreScreen.Show(GameManager.PartLabel, points, "Press [Enter] to continue", FindFirstObjectByType<CameraController>());
        Music.PlayScore();
    }
}
