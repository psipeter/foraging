using System.IO;
using TMPro;
using UnityEngine;
using UnityEngine.InputSystem;

public class InstructionsPanel : MonoBehaviour
{
    private const string FallbackInstructions =
        "<size=28><b>Welcome to the Foraging Task</b></size>\n\n" +
        "Navigate the environment using WASD.\n" +
        "Press Space when near a bush to harvest it.\n" +
        "Collect as much reward as possible before sunset.\n\n" +
        "<i>Press Space to begin.</i>";

    [SerializeField] private GameObject panel;
    [SerializeField] private TextMeshProUGUI bodyText;
    [SerializeField] private TextMeshProUGUI sessionLabel;

    private void Start()
    {
        if (sessionLabel != null)
        {
            sessionLabel.gameObject.SetActive(false);
        }

        if (GameManager.CurrentSessionIndex == 0)
        {
            if (bodyText != null)
            {
                bodyText.gameObject.SetActive(true);
                bodyText.richText = true;
                string path = Path.Combine(Application.streamingAssetsPath, "instructions.txt");
                string text = FallbackInstructions;
                try
                {
                    if (File.Exists(path))
                    {
                        text = File.ReadAllText(path);
                    }
                }
                catch (IOException)
                {
                    text = FallbackInstructions;
                }

                bodyText.text = text;
            }

            if (panel != null)
            {
                panel.SetActive(true);
            }

            Time.timeScale = 0f;
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

        if (Keyboard.current == null)
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
