using UnityEngine;
using UnityEngine.InputSystem;
using UnityEngine.InputSystem.LowLevel;
using UnityEngine.SceneManagement;

// Development builds only. ?autopilot=1 (with ?perf=1) plays a fixed route through the game scene by sending the game the same input a participant would (the W key
// and mouse movement, through the Input System), so that frame times of different settings are measured on the same views:
//   walk     (first 50% of the recorded time): walk forward, turning slowly (a wide arc, through the bushes and the tiles)
//   horizon  (next 25%): stand still and turn a full circle with the view level (sky, far terrain, mountains, the whole canopy field)
//   ground   (last 25%): stand still and turn a full circle looking down (the near terrain, bushes and fruits up close)
// PerfProbe.Mark tags each phase in the results. A route that meets a mountain slides along it, so the walk is repeatable only to within the world's geometry.
public class PerfAutopilot : MonoBehaviour
{
    private const float WalkTurnDegPerSecond = 9f;
    private const float PanDegPerSecond = 30f;
    private const float GroundPitchDeg = 22f;
    private const float Horizon = 0.5f;
    private const float Ground = 0.75f;

    private int _phase = -1;
    private bool _keyDown;
    private CameraController _camera;

    [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.BeforeSceneLoad)]
    private static void Begin()
    {
        if (!Debug.isDebugBuild || OnlineSettings.UrlParameter("perf") == null || OnlineSettings.UrlParameter("autopilot") == null)
        {
            return;
        }

        var host = new GameObject("PerfAutopilot");
        DontDestroyOnLoad(host);
        host.AddComponent<PerfAutopilot>();
    }

    private void Update()
    {
        if (Keyboard.current == null || Mouse.current == null || !PerfProbe.Recording || SceneManager.GetActiveScene().name != "SampleScene" || Time.timeScale <= 0f)
        {
            SetKey(false);
            return;
        }

        SessionConfig config = GameManager.AllSessionConfigs != null && GameManager.CurrentSessionIndex < GameManager.AllSessionConfigs.Count
            ? GameManager.AllSessionConfigs[GameManager.CurrentSessionIndex] : null;
        float degreesPerCount = config != null ? config.LookDegreesPerCount * config.LookSensitivity : 0.1f;
        float elapsed = PerfProbe.Elapsed;
        float fraction = PerfProbe.Duration > 0f ? elapsed / PerfProbe.Duration : 0f;
        int phase = fraction < Horizon ? 0 : fraction < Ground ? 1 : 2;
        if (phase != _phase)
        {
            _phase = phase;
            PerfProbe.Mark(phase == 0 ? "walk" : phase == 1 ? "horizon" : "ground");
        }

        SetKey(phase == 0);
        float yawDegrees = (phase == 0 ? WalkTurnDegPerSecond : PanDegPerSecond) * Time.unscaledDeltaTime;
        float pitchDegrees = phase == 2 ? Mathf.Clamp(GroundPitchDeg - Pitch(), -1f, 1f) : 0f;     // eases down to the ground view, then holds it

        // Mouse y is "up positive" in the look input and pitch is "down positive" (CameraController: _pitch - delta.y).
        var counts = new Vector2(yawDegrees / degreesPerCount, -pitchDegrees / degreesPerCount);
        InputSystem.QueueDeltaStateEvent(Mouse.current.delta, counts);
    }

    private float Pitch()
    {
        if (_camera == null)
        {
            _camera = FindFirstObjectByType<CameraController>();
        }

        return _camera != null ? _camera.Pitch : 0f;
    }

    private void SetKey(bool down)
    {
        if (Keyboard.current == null || down == _keyDown)
        {
            return;
        }

        _keyDown = down;
        InputSystem.QueueStateEvent(Keyboard.current, down ? new KeyboardState(Key.W) : new KeyboardState());
    }
}
