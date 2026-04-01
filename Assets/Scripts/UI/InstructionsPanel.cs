using TMPro;
using UnityEngine;
using UnityEngine.InputSystem;

public class InstructionsPanel : MonoBehaviour
{
    [SerializeField] private GameObject panel;
    [SerializeField] private TextMeshProUGUI bodyText;
    [SerializeField] private TextMeshProUGUI sessionLabel;

    private static bool _instructionsShown = false;

    private void Start()
    {
        int currentIndex = GameManager.CurrentSessionIndex;
        int total = GameManager.TotalSessions;

        if (sessionLabel != null)
        {
            if (currentIndex > 0)
            {
                sessionLabel.gameObject.SetActive(true);
                sessionLabel.text = $"Session {currentIndex + 1} of {Mathf.Max(1, total)}";
            }
            else
            {
                sessionLabel.gameObject.SetActive(false);
            }
        }

        if (bodyText != null && string.IsNullOrWhiteSpace(bodyText.text))
        {
            bodyText.text =
                "Welcome to the Foraging Task\n\n" +
                "Navigate using WASD.\n" +
                "Press Space when near a bush to harvest it.\n" +
                "Collect as much reward as possible before sunset.\n\n" +
                "Press Space to begin.";
        }

        if (!_instructionsShown)
        {
            if (panel != null)
            {
                panel.SetActive(true);
            }
            Time.timeScale = 0f;
            _instructionsShown = true;
        }
        else
        {
            if (panel != null)
            {
                panel.SetActive(false);
            }
            Time.timeScale = 1f;
        }
    }

    private void Update()
    {
        if (panel == null || !panel.activeSelf)
        {
            return;
        }

        if (Keyboard.current.spaceKey.wasPressedThisFrame ||
            Keyboard.current.enterKey.wasPressedThisFrame ||
            Keyboard.current.numpadEnterKey.wasPressedThisFrame)
        {
            panel.SetActive(false);
            Time.timeScale = 1f;
        }
    }
}

