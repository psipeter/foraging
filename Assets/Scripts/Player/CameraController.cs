using UnityEngine;

// First-person camera. Yaw and pitch live on the camera transform itself: the player Rigidbody is
// interpolated, which would overwrite any rotation applied to the player root every frame.
public class CameraController : MonoBehaviour
{
    public SessionConfig sessionConfig;
    [SerializeField] private Camera playerCamera;
    [SerializeField] private PlayerController playerController;
    [SerializeField] private HarvestManager harvestManager;

    private ILookInput _lookInput;
    private float _yaw;
    private float _pitch;

    // Heading (degrees about Y) that forward/back movement is relative to.
    public float Yaw => _yaw;
    public Camera PlayerCamera => playerCamera;

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

    // Sets the heading and pitch directly (the Interlude faces the player toward the bushes at each trial start).
    public void SetView(float yaw, float pitch)
    {
        _yaw = yaw;
        _pitch = pitch;
        if (playerCamera != null)
        {
            ApplyRotation();
        }
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
        // screen) or frozen (session end only; harvesting locks walking, not looking) so the pending delta is discarded, not applied late.
        if (Time.timeScale <= 0f || (playerController != null && playerController.IsFrozen))
        {
            return;
        }

        Vector2 delta = _lookInput.ReadLookDelta() * (sessionConfig.LookDegreesPerCount * sessionConfig.LookSensitivity);
        _yaw += ApplyHarvestResistance(delta.x);
        _pitch = Mathf.Clamp(_pitch - delta.y, -sessionConfig.LookPitchLimit, sessionConfig.LookPitchLimit);
        ApplyRotation();
    }

    // Optional (config, off by default): while harvesting, yaw slows toward zero as the player turns away from
    // the bush; turning back toward it is unaffected. Pitch is never touched.
    private float ApplyHarvestResistance(float yawDelta)
    {
        float resistance = sessionConfig.HarvestLookResistance;
        if (resistance <= 0f || harvestManager == null || !harvestManager.TryGetHarvestOffAngle(out float offAngle))
        {
            return yawDelta;
        }

        if (yawDelta * offAngle >= 0f)
        {
            return yawDelta;
        }

        float full = sessionConfig.HighlightFullAngle;
        float fade = Mathf.Max(sessionConfig.HighlightFadeAngle, full + 0.01f);
        float t = Mathf.Clamp01(Mathf.InverseLerp(full, fade, Mathf.Abs(offAngle)));
        t = t * t * (3f - 2f * t);
        return yawDelta * (1f - resistance * t);
    }

    private void ApplyRotation()
    {
        playerCamera.transform.localRotation = Quaternion.Euler(_pitch, _yaw, 0f);
    }
}
