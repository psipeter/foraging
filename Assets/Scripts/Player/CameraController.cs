using UnityEngine;

// First-person camera. Yaw and pitch live on the camera transform itself: the player Rigidbody is
// interpolated, which would overwrite any rotation applied to the player root every frame.
public class CameraController : MonoBehaviour
{
    public SessionConfig sessionConfig;
    [SerializeField] private Camera playerCamera;
    [SerializeField] private PlayerController playerController;

    private ILookInput _lookInput;
    private float _yaw;
    private float _pitch;

    // Heading (degrees about Y) that forward/back movement is relative to.
    public float Yaw => _yaw;

    private void Awake()
    {
        _lookInput = GetComponent<ILookInput>();
    }

    private void Start()
    {
        Cursor.visible = false;
        Cursor.lockState = CursorLockMode.Locked;

        ApplyCameraSettings();
    }

    public void ApplyCameraSettings()
    {
        if (playerCamera == null || sessionConfig == null)
        {
            return;
        }

        float groundOffset = playerController != null ? playerController.GroundOffset : 0f;
        playerCamera.transform.localPosition = new Vector3(0f, sessionConfig.EyeHeight - groundOffset, 0f);
        playerCamera.fieldOfView = sessionConfig.CameraFieldOfView;
        playerCamera.nearClipPlane = sessionConfig.CameraNearClip;
        ApplyRotation();
    }

    private void Update()
    {
        if (sessionConfig == null || _lookInput == null || playerCamera == null)
        {
            return;
        }

        // Mouse deltas are displacements, not rates: no Time.deltaTime. Skip while paused (instructions
        // screen) or frozen (harvesting, session end) so the pending delta is discarded, not applied late.
        if (Time.timeScale <= 0f || (playerController != null && playerController.IsFrozen))
        {
            return;
        }

        Vector2 delta = _lookInput.ReadLookDelta() * (sessionConfig.LookDegreesPerCount * sessionConfig.LookSensitivity);
        _yaw += delta.x;
        _pitch = Mathf.Clamp(_pitch - delta.y, -sessionConfig.LookPitchLimit, sessionConfig.LookPitchLimit);
        ApplyRotation();
    }

    private void ApplyRotation()
    {
        playerCamera.transform.localRotation = Quaternion.Euler(_pitch, _yaw, 0f);
    }
}
