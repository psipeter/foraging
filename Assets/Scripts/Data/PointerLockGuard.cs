using System.Runtime.InteropServices;
using UnityEngine;
using UnityEngine.InputSystem;
using UnityEngine.SceneManagement;

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

    [DllImport("__Internal")]
    private static extern void RequestPointerLock();
#endif

    // Asks the browser for the capture now: called in the frame of the click that starts an experiment (a browser build only), while that click still counts as a user gesture.
    public static void Request()
    {
        Cursor.lockState = CursorLockMode.Locked;
#if UNITY_WEBGL && !UNITY_EDITOR
        RequestPointerLock();
#endif
    }

    // A capture request (the click in the Boot scene, or a scene that asks for the capture as it starts) is granted a few frames later; do not pause on that gap. The window
    // opens again whenever the guard stops being suspended (the click that begins an experiment) and whenever a scene loads.
    private const float GraceSeconds = 0.5f;

    // Chrome refuses a capture request made within about a second of the participant leaving the capture (Escape): the request
    // fails with a SecurityError, which Unity would surface as an error pop-up. Clicks in that window are ignored.
    private const float RelockCooldownSeconds = 1.3f;

    // True on the final screen, where the participant types and clicks: the mouse is released and not captured again.
    public static bool Suspended { get; set; }

    [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.SubsystemRegistration)]
    private static void Reset() => Suspended = false;

    private InstructionsScreen _screen;               // "Paused": the same screen as the instruction pages and hints
    private bool _screenShown;
    private float _graceUntil;
    private float _unlockedAt = float.NegativeInfinity;
    private bool _wasHeld;
    private bool _wasSuspended = true;

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
        // Sort order 4900: below the data gate (5000) so that the completion code and errors stay readable, above the instruction pages and hints (4000).
        _screen = InstructionsScreen.Create(transform, 4900);
        _graceUntil = Time.unscaledTime + GraceSeconds;
        SceneManager.sceneLoaded += HandleSceneLoaded;
    }

    private void OnDestroy()
    {
        SceneManager.sceneLoaded -= HandleSceneLoaded;
    }

    private void HandleSceneLoaded(Scene scene, LoadSceneMode mode)
    {
        _graceUntil = Time.unscaledTime + GraceSeconds;
    }

    private void Update()
    {
        if (_wasSuspended && !Suspended)
        {
            _graceUntil = Time.unscaledTime + GraceSeconds;          // the click that begins an experiment has just asked for the capture
        }

        _wasSuspended = Suspended;
        if (Suspended)
        {
            SetScreen(false);
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
        SetScreen(paused);
        PauseGate.Pointer = paused;
        AudioListener.pause = paused;
        Cursor.visible = paused;
        if (!held && Mouse.current != null && Mouse.current.leftButton.wasPressedThisFrame &&
            Time.unscaledTime - _unlockedAt >= RelockCooldownSeconds)
        {
            // Ask for the capture and stay paused until the browser confirms it holds it (Held): resuming on the click itself, with a
            // grace period, let the game run for a moment when the browser refused the request and then pause again.
            Request();
        }
    }

    // The pause screen: shown while paused.
    private void SetScreen(bool shown)
    {
        if (shown == _screenShown)
        {
            return;
        }

        _screenShown = shown;
        if (shown)
        {
            _screen.Show(GameManager.SessionCount > 0 ? GameManager.PartLabel : "", "Paused", "", "[Click] to continue");
        }
        else
        {
            _screen.Hide();
        }
    }
}
