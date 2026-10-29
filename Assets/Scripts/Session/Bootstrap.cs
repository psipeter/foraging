using System.Collections;
using TMPro;
using UnityEngine;
using UnityEngine.InputSystem;
using UnityEngine.SceneManagement;
using UnityEngine.UI;

// The first scene of a build. On desktop it only hands over to the game scene. In a browser it first fetches the
// StreamingAssets files into memory (StreamingData), then waits for a click: pointer lock, fullscreen and audio all need a
// user gesture, and this is the one that starts them.
public class Bootstrap : MonoBehaviour
{
    [SerializeField] private string gameScene = "SampleScene";

    private TextMeshProUGUI _text;

    private void Start()
    {
        if (!StreamingData.NeedsPreload)
        {
            SceneManager.LoadScene(gameScene);
            return;
        }

        BuildUi();
        StartCoroutine(Run());
    }

    private IEnumerator Run()
    {
        string failure = null;
        _text.text = "Loading...";
        yield return StreamingData.Preload(p => _text.text = $"Loading... {Mathf.RoundToInt(p * 100f)}%", reason => failure = reason);
        if (failure != null)
        {
            _text.text = failure + "\n\nPlease reload the page. If this continues, contact the researcher.";
            yield break;
        }

        _text.text = "Click anywhere to begin.\n\n<size=60%>The mouse will be captured by the game. Press Escape to release it.</size>";
        while (Mouse.current == null || !Mouse.current.leftButton.wasPressedThisFrame)
        {
            yield return null;
        }

        if (OnlineSettings.UrlParameter("fullscreen") != "0")        // ?fullscreen=0 keeps the page layout (testing)
        {
            Screen.fullScreen = true;
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
        scaler.referenceResolution = new Vector2(1920f, 1080f);

        var label = new GameObject("Message", typeof(RectTransform), typeof(TextMeshProUGUI));
        label.transform.SetParent(canvasObject.transform, false);
        RectTransform rect = label.GetComponent<RectTransform>();
        rect.anchorMin = new Vector2(0.2f, 0.3f);
        rect.anchorMax = new Vector2(0.8f, 0.7f);
        rect.offsetMin = rect.offsetMax = Vector2.zero;
        _text = label.GetComponent<TextMeshProUGUI>();
        _text.alignment = TextAlignmentOptions.Center;
        _text.fontSize = 36f;
        _text.color = Color.white;
        _text.raycastTarget = false;
    }
}
