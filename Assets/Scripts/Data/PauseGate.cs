using UnityEngine;

// The one place that sets Time.timeScale. Three things can hold the game still: a screen the participant has to dismiss
// (InstructionsPanel), the data service (connecting, or waiting for the server to acknowledge data) and, in a browser, a
// released mouse capture. The game runs only when none does, so one releasing never un-pauses another.
public static class PauseGate
{
    private static bool _instructions;
    private static bool _upload;
    private static bool _pointer;

    public static bool Instructions
    {
        set { _instructions = value; Apply(); }
    }

    public static bool Upload
    {
        set { _upload = value; Apply(); }
    }

    // In a browser: the mouse is not captured (the participant pressed Escape), so looking around would not work.
    public static bool Pointer
    {
        set { _pointer = value; Apply(); }
    }

    // Why the game is held, for the `pause` event ("instructions", "upload", "instructions+upload"); "" when running.
    public static string Reason
    {
        get
        {
            var reasons = new System.Collections.Generic.List<string>();
            if (_instructions) reasons.Add("instructions");
            if (_upload) reasons.Add("upload");
            if (_pointer) reasons.Add("pointer");
            return string.Join("+", reasons);
        }
    }

    private static void Apply()
    {
        Time.timeScale = _instructions || _upload || _pointer ? 0f : 1f;
    }

    [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.SubsystemRegistration)]
    private static void Reset()
    {
        _instructions = _upload = _pointer = false;
    }
}
