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

    private float _lastTotalScore;
    private bool _sessionEndHandled;

    private void Awake()
    {
        if (sessionEndPanel != null)
        {
            sessionEndPanel.SetActive(false);
        }
    }

    [Header("Timer display")]
    [SerializeField] private float timerFontSize = 32f;
    [SerializeField] private Vector2 timerPosition = new Vector2(150f, -44f);
    [SerializeField] private Vector2 timerPlateSize = new Vector2(230f, 60f);
    [SerializeField] private Color plateColor = new Color(0f, 0f, 0f, 0.38f);

    private void Start()
    {
        if (timerText == null)
        {
            return;
        }

        RectTransform rect = timerText.rectTransform;
        rect.anchoredPosition = timerPosition;
        rect.sizeDelta = timerPlateSize - new Vector2(20f, 10f);
        timerText.fontSize = timerFontSize;
        timerText.fontStyle = FontStyles.Bold;
        timerText.alignment = TextAlignmentOptions.Center;
        HudWidgets.CreatePlate(rect, timerPlateSize, plateColor, "TimerPlate");
    }

    private void OnEnable()
    {
        SunController.OnSessionEnd += HandleSessionEnd;
        HarvestManager.OnScoreChanged += HandleHarvestComplete;
    }

    private void OnDisable()
    {
        SunController.OnSessionEnd -= HandleSessionEnd;
        HarvestManager.OnScoreChanged -= HandleHarvestComplete;
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
                    // Leave only once the server has stored everything (otherwise a "saving" screen shows until it has); after the last
                    // session the run is also closed on the server.
                    if (GameManager.IsLastSession ? !DataPipeline.TryFinish() : !DataPipeline.TryLeave())
                    {
                        return;
                    }

                    if (GameManager.IsLastSession)
                    {
                        Application.Quit();
#if UNITY_EDITOR
                        EditorApplication.isPlaying = false;
#endif
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

        // An Interlude shows the per-trial countdown here instead of the session clock.
        if (sessionConfig.IsInterlude && interludeManager != null && interludeManager.Active)
        {
            timerText.text = interludeManager.TimerLabel;
            return;
        }

        float remaining = sunController.SessionTimeRemaining;
        remaining = Mathf.Max(0f, remaining);

        int minutes = Mathf.FloorToInt(remaining / 60f);
        int seconds = Mathf.FloorToInt(remaining % 60f);

        timerText.text = $"{minutes:D2}:{seconds:D2}";
    }

    private void HandleHarvestComplete(float runningTotal)
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

        GameManager.LastSessionScore = _lastTotalScore;

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
            sessionCompleteText.text = isLast ? "Experiment Complete"
                : isInterlude ? "Interlude Complete"
                : isPractice ? "Practice Complete"
                : "Session Complete";
        }

        if (nextSessionPromptText != null)
        {
            nextSessionPromptText.gameObject.SetActive(true);
            nextSessionPromptText.text = isLast
                ? "Press Enter to exit"
                : $"Press Enter to continue to {GameManager.NextStageLabel()}";
        }

        if (finalScoreText != null)
        {
            // An Interlude shows only its own count correct and bonus (never which trials, nor the reward
            // function); the practice Interlude shows nothing. The final screen adds the totals.
            finalScoreText.gameObject.SetActive(isLast || !isInterlude || !sessionConfig.IsPractice);
            if (isInterlude && !isLast)
            {
                finalScoreText.text = $"{GameManager.ThisInterludeCorrect} / {GameManager.ThisInterludeTrials} correct\nBonus: +{GameManager.ThisInterludeBonus:F0}";
            }
            else if (isLast)
            {
                float total = GameManager.SessionScoreTotal + GameManager.InterludeBonus;
                string thisInterlude = isInterlude ? $"This Interlude: {GameManager.ThisInterludeCorrect} / {GameManager.ThisInterludeTrials} correct, +{GameManager.ThisInterludeBonus:F0}\n" : "";
                finalScoreText.text = $"{thisInterlude}Total Score: {total:F0}\nSessions {GameManager.SessionScoreTotal:F0}  +  Interlude bonus {GameManager.InterludeBonus:F0} ({GameManager.InterludeCorrectCount}/{GameManager.InterludeTrialsScored} correct)";
            }
            else
            {
                finalScoreText.text = $"Final Score: {_lastTotalScore:F1}";
            }
        }
    }
}
