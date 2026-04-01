using System;
using UnityEngine;
using UnityEngine.InputSystem;
using UnityEngine.SceneManagement;
using TMPro;

public class SessionTimerUI : MonoBehaviour
{
    [SerializeField] private TextMeshProUGUI timerText;
    [SerializeField] private SunController sunController;
    public SessionConfig sessionConfig;
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

    private void OnEnable()
    {
        SunController.OnSessionEnd += HandleSessionEnd;
        HarvestManager.OnHarvestComplete += HandleHarvestComplete;
    }

    private void OnDisable()
    {
        SunController.OnSessionEnd -= HandleSessionEnd;
        HarvestManager.OnHarvestComplete -= HandleHarvestComplete;
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

            if (sessionEndPanel != null && sessionEndPanel.activeSelf && !GameManager.IsLastSession)
            {
                if (Keyboard.current != null &&
                    (Keyboard.current.spaceKey.wasPressedThisFrame ||
                     Keyboard.current.enterKey.wasPressedThisFrame ||
                     Keyboard.current.numpadEnterKey.wasPressedThisFrame))
                {
                    GameManager.AdvanceSession();
                    Scene current = SceneManager.GetActiveScene();
                    SceneManager.LoadScene(current.name);
                }
            }

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

        if (sessionEndPanel != null)
        {
            sessionEndPanel.SetActive(true);
        }

        bool isLast = GameManager.IsLastSession;

        if (sessionCompleteText != null)
        {
            sessionCompleteText.text = isLast ? "Experiment Complete" : "Session Complete";
        }

        if (nextSessionPromptText != null)
        {
            nextSessionPromptText.gameObject.SetActive(!isLast);
            if (!isLast)
            {
                nextSessionPromptText.text = "Press Space to continue";
            }
        }

        if (finalScoreText != null)
        {
            finalScoreText.text = $"Final Score: {_lastTotalScore:F1}";
        }
    }
}

