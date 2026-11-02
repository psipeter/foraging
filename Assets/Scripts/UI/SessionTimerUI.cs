using UnityEngine;
using UnityEngine.InputSystem;
using UnityEngine.SceneManagement;
using TMPro;
#if UNITY_EDITOR
using UnityEditor;
#endif

public class SessionTimerUI : MonoBehaviour
{
    [SerializeField] private TextMeshProUGUI timerText;
    [SerializeField] private SunController sunController;
    public SessionConfig sessionConfig;
    public InterludeManager interludeManager;
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

        UiStyle.HudPlate(timerText, timerPosition, timerPlateSize, timerFontSize, plateColor, "TimerPlate");
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

            if (sessionEndPanel != null && sessionEndPanel.activeSelf)
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
                        if (StreamingData.NeedsPreload)
                        {
                            DataPipeline.ShowStudyComplete();       // a browser cannot close its page; quitting would leave it blank
                        }
                        else
                        {
                            Application.Quit();
#if UNITY_EDITOR
                            EditorApplication.isPlaying = false;
#endif
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
        bool isPractice = sessionConfig != null && sessionConfig.IsPractice;
        if (!isInterlude && !isPractice)
        {
            GameManager.SessionScoreTotal += _lastTotalScore;
        }

        bool isLast = GameManager.IsLastSession;

        if (sessionEndPanel != null)
        {
            sessionEndPanel.SetActive(true);
        }

        if (sessionCompleteText != null)
        {
            sessionCompleteText.text = isLast ? "Experiment complete"
                : isInterlude ? "Interlude complete"
                : isPractice ? "Practice session complete"
                : "Session complete";
        }

        if (nextSessionPromptText != null)
        {
            nextSessionPromptText.text = $"Press {UiStyle.Chip("Enter")} to {(isLast ? "exit" : "continue")}";
        }

        if (finalScoreText != null)
        {
            // An Interlude's points are hidden until the last screen (the practice Interlude shows what it would have paid, and never
            // which choices were right); the last screen adds the totals.
            bool showPoints = !isInterlude || isPractice || isLast;
            finalScoreText.gameObject.SetActive(showPoints);
            float points = isInterlude ? (interludeManager != null ? interludeManager.Points : 0f) : _lastTotalScore;
            finalScoreText.text = !isLast ? $"+{points:F0} points"
                : (isInterlude ? $"This interlude: +{points:F0} points\n" : "")
                  + $"Total: +{GameManager.SessionScoreTotal + GameManager.InterludeBonus:F0} points";
        }
    }
}
