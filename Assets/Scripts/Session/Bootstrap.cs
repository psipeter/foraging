using System.Collections;
using TMPro;
using UnityEngine;
using UnityEngine.InputSystem;
using UnityEngine.SceneManagement;

// The first scene of a build. On desktop it hands over to the game scene. In a browser it first fetches the
// StreamingAssets files into memory (StreamingData), then, when the build uploads (online.json), shows the consent / participant ID screen (ConsentScreen), then waits for a click: pointer lock and audio need a user gesture, and this is the
// one that starts them. It does not request fullscreen: changing the canvas size from inside the game left the picture black
// (real browser, and a headless reproduction); the participant may use the page's own fullscreen button.
public class Bootstrap : MonoBehaviour
{
    [SerializeField] private string gameScene = "SampleScene";

    private void Start()
    {
        StartCoroutine(Run());
    }

    private IEnumerator Run()
    {
        // Desktop builds are for lab use: no preload, and no consent screen (-pid on the command line).
        if (!StreamingData.NeedsPreload)
        {
            SceneManager.LoadScene(gameScene);
            yield break;
        }

        TextMeshProUGUI text = UiStyle.MessageScreen("BootCanvas", null, 0, false);
        string failure = null;
        text.text = "Loading...";
        yield return StreamingData.Preload(p => text.text = $"Loading... {Mathf.RoundToInt(p * 100f)}%", reason => failure = reason);
        if (failure != null)
        {
            text.text = failure + "\n\nPlease reload the page. If this continues, contact the researcher.";
            yield break;
        }

        OnlineSettings settings = OnlineSettings.Load();
        if (settings.Active)
        {
            text.gameObject.SetActive(false);
            ConsentScreen screen = ConsentScreen.Show(settings.prolificPid);
            yield return new WaitUntil(() => screen.Done);

            OnlineSettings.EnteredId = screen.ParticipantId;
            OnlineSettings.EnteredConsent = screen.Consent;
            text.gameObject.SetActive(true);
        }

        text.text = "Click anywhere to begin.\n\n<size=65%>The mouse will be captured by the game. Press Escape to release it.</size>";
        yield return null;
        yield return new WaitUntil(() => Mouse.current != null && Mouse.current.leftButton.wasPressedThisFrame);

        Cursor.lockState = CursorLockMode.Locked;
        var guard = new GameObject("PointerLockGuard", typeof(PointerLockGuard));
        DontDestroyOnLoad(guard);
        SceneManager.LoadScene(gameScene);
    }
}
