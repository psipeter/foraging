using System.Runtime.InteropServices;
using TMPro;
using UnityEngine;
using UnityEngine.InputSystem;
using UnityEngine.UI;

// In a browser the mouse is captured (pointer lock) only after a click, and the browser releases it whenever the participant
// presses Escape or leaves the tab or window. While it is not held the game is paused behind "Paused: click to continue" (PauseGate:
// the clock stops, the sound is muted, the system cursor is shown so the participant can switch tabs or click away), and a click
// captures the mouse again and resumes. Unity's own Cursor.lockState does not notice the browser releasing the capture, so the
// state is read from the page (Plugins/WebGL/PointerLock.jslib). Created by the Bootstrap scene on WebGL only.
public class PointerLockGuard : MonoBehaviour
{
#if UNITY_WEBGL && !UNITY_EDITOR
    [DllImport("__Internal")]
    private static extern int IsPointerLocked();
#endif

    // The first capture request (the click in the Boot scene) is granted a few frames after the click; do not pause on that gap.
    private const float GraceSeconds = 0.5f;

    // Chrome refuses a capture request made within about a second of the participant leaving the capture (Escape): the request
    // fails with a SecurityError, which Unity would surface as an error pop-up. Clicks in that window are ignored.
    private const float RelockCooldownSeconds = 1.3f;

    private GameObject _overlay;
    private float _graceUntil;
    private float _unlockedAt = float.NegativeInfinity;
    private bool _wasHeld;

    private static bool Held()
    {
#if UNITY_WEBGL && !UNITY_EDITOR
        return IsPointerLocked() == 1;
#else
        return Cursor.lockState == CursorLockMode.Locked;
#endif
    }

    private void Awake()
    {
        _overlay = new GameObject("PointerGate", typeof(RectTransform), typeof(Canvas), typeof(CanvasScaler));
        _overlay.transform.SetParent(transform, false);
        var canvas = _overlay.GetComponent<Canvas>();
        canvas.renderMode = RenderMode.ScreenSpaceOverlay;
        canvas.sortingOrder = 5100;
        var scaler = _overlay.GetComponent<CanvasScaler>();
        scaler.uiScaleMode = CanvasScaler.ScaleMode.ScaleWithScreenSize;
        scaler.referenceResolution = UiStyle.ReferenceResolution;

        var dim = new GameObject("Dim", typeof(RectTransform), typeof(Image));
        dim.transform.SetParent(_overlay.transform, false);
        RectTransform dimRect = dim.GetComponent<RectTransform>();
        dimRect.anchorMin = Vector2.zero;
        dimRect.anchorMax = Vector2.one;
        dimRect.offsetMin = dimRect.offsetMax = Vector2.zero;
        dim.GetComponent<Image>().color = Color.black;

        var label = new GameObject("Message", typeof(RectTransform), typeof(TextMeshProUGUI));
        label.transform.SetParent(_overlay.transform, false);
        RectTransform rect = label.GetComponent<RectTransform>();
        rect.anchorMin = new Vector2(0.2f, 0.3f);
        rect.anchorMax = new Vector2(0.8f, 0.7f);
        rect.offsetMin = rect.offsetMax = Vector2.zero;
        var text = label.GetComponent<TextMeshProUGUI>();
        text.alignment = TextAlignmentOptions.Center;
        UiStyle.Apply(text, UiStyle.Title);
        text.color = Color.white;
        text.raycastTarget = false;
        text.text = "Paused\n\n<size=65%>The timer is stopped. Click to continue.</size>";
        _overlay.SetActive(false);
        _graceUntil = Time.unscaledTime + GraceSeconds;
    }

    private void Update()
    {
        bool held = Held();
        if (_wasHeld && !held)
        {
            _unlockedAt = Time.unscaledTime;
        }

        _wasHeld = held;
        bool paused = !held && Time.unscaledTime > _graceUntil;
        if (_overlay.activeSelf != paused)
        {
            _overlay.SetActive(paused);
        }

        PauseGate.Pointer = paused;
        AudioListener.pause = paused;
        Cursor.visible = paused;
        if (!held && Mouse.current != null && Mouse.current.leftButton.wasPressedThisFrame &&
            Time.unscaledTime - _unlockedAt >= RelockCooldownSeconds)
        {
            // Ask for the capture and stay paused until the browser confirms it holds it (Held): resuming on the click itself, with a
            // grace period, let the game run for a moment when the browser refused the request and then pause again.
            Cursor.lockState = CursorLockMode.Locked;
        }
    }
}
