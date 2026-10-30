using System.Collections;
using TMPro;
using UnityEngine;
using UnityEngine.InputSystem;
using UnityEngine.SceneManagement;
using UnityEngine.UI;

// The first scene of a build. On desktop it hands over to the game scene. In a browser it first fetches the
// StreamingAssets files into memory (StreamingData), then, when the build uploads (online.json), shows the consent / participant ID screen (ConsentScreen), then waits for a click: pointer lock and audio need a user gesture, and this is the
// one that starts them. It does not request fullscreen: changing the canvas size from inside the game left the picture black
// (real browser, and a headless reproduction); the participant may use the page's own fullscreen button.
public class Bootstrap : MonoBehaviour
{
    [SerializeField] private string gameScene = "SampleScene";

    private TextMeshProUGUI _text;

    private void Start()
    {
        StartCoroutine(Run());
    }

    private IEnumerator Run()
    {
        bool browser = StreamingData.NeedsPreload;
        if (browser)
        {
            BuildUi();
            string failure = null;
            _text.text = "Loading...";
            yield return StreamingData.Preload(p => _text.text = $"Loading... {Mathf.RoundToInt(p * 100f)}%", reason => failure = reason);
            if (failure != null)
            {
                _text.text = failure + "\n\nPlease reload the page. If this continues, contact the researcher.";
                yield break;
            }
        }

        // Consent and an ID are collected in a browser only: desktop builds are for lab use (-pid on the command line).
        if (browser && OnlineSettings.Load().Active)
        {
            _text.gameObject.SetActive(false);
            ConsentScreen screen = ConsentScreen.Show(OnlineSettings.Load().prolificPid);
            while (!screen.Done)
            {
                yield return null;
            }

            OnlineSettings.EnteredId = screen.ParticipantId;
            OnlineSettings.EnteredConsent = screen.Consent;
            _text.gameObject.SetActive(true);
        }

        if (!browser)
        {
            SceneManager.LoadScene(gameScene);
            yield break;
        }

        _text.text = "Click anywhere to begin.\n\n<size=65%>The mouse will be captured by the game. Press Escape to release it.</size>";
        yield return null;
        while (Mouse.current == null || !Mouse.current.leftButton.wasPressedThisFrame)
        {
            yield return null;
        }

        Cursor.lockState = CursorLockMode.Locked;
        Cursor.visible = false;
        var guard = new GameObject("PointerLockGuard", typeof(PointerLockGuard));
        DontDestroyOnLoad(guard);
        SceneManager.LoadScene(gameScene);
    }

    private void BuildUi()
    {
        var canvasObject = new GameObject("BootCanvas", typeof(RectTransform), typeof(Canvas), typeof(CanvasScaler));
        var canvas = canvasObject.GetComponent<Canvas>();
        canvas.renderMode = RenderMode.ScreenSpaceOverlay;
        var scaler = canvasObject.GetComponent<CanvasScaler>();
        scaler.uiScaleMode = CanvasScaler.ScaleMode.ScaleWithScreenSize;
        scaler.referenceResolution = UiStyle.ReferenceResolution;

        var label = new GameObject("Message", typeof(RectTransform), typeof(TextMeshProUGUI));
        label.transform.SetParent(canvasObject.transform, false);
        RectTransform rect = label.GetComponent<RectTransform>();
        rect.anchorMin = new Vector2(0.2f, 0.3f);
        rect.anchorMax = new Vector2(0.8f, 0.7f);
        rect.offsetMin = rect.offsetMax = Vector2.zero;
        _text = label.GetComponent<TextMeshProUGUI>();
        _text.alignment = TextAlignmentOptions.Center;
        UiStyle.Apply(_text, UiStyle.Title);
        _text.color = Color.white;
        _text.raycastTarget = false;
    }
}
