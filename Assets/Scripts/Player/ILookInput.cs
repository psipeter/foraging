using UnityEngine;

// Source of per-frame look input in raw device counts (x = right, y = up).
// CameraController converts counts to degrees. A VR implementation would return
// Vector2.zero and let the headset pose drive the camera instead.
public interface ILookInput
{
    Vector2 ReadLookDelta();
}
