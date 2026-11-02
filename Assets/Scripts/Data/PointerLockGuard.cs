using System.Runtime.InteropServices;
using TMPro;
using UnityEngine;
using UnityEngine.InputSystem;

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

    // True on the final screen, where the participant types and clicks: the mouse is released and not captured again.
    public static bool Suspended { get; set; }

    [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.SubsystemRegistration)]
    private static void Reset() => Suspended = false;

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
        // Overlay sort orders: this one (4900) sits below the data gate (5000) so that the completion code and errors stay readable;
        // the consent screen (6000) is above both.
        TextMeshProUGUI text = UiStyle.MessageScreen("PointerGate", transform, 4900, true);
        _overlay = text.canvas.gameObject;
        text.text = "Paused\n\n<size=65%>The timer is stopped. Click to continue.</size>";
        _overlay.SetActive(false);
        _graceUntil = Time.unscaledTime + GraceSeconds;
    }

    private void Update()
    {
        if (Suspended)
        {
            _overlay.SetActive(false);
            PauseGate.Pointer = false;
            AudioListener.pause = false;
            Cursor.visible = true;
            Cursor.lockState = CursorLockMode.None;
            return;
        }

        bool held = Held();
        if (_wasHeld && !held)
        {
            _unlockedAt = Time.unscaledTime;
        }

        _wasHeld = held;
        bool paused = !held && Time.unscaledTime > _graceUntil;
        _overlay.SetActive(paused);
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
