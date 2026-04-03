using UnityEngine;
using UnityEngine.InputSystem;

public class CameraController : MonoBehaviour
{
    public SessionConfig sessionConfig;
    [SerializeField] private Transform cameraTransform;
    [SerializeField] private PlayerController playerController;
    [SerializeField] private InputActionReference lookAction;

    private void Start()
    {
        Cursor.visible = false;
        Cursor.lockState = CursorLockMode.Locked;

        ApplyCameraMode();
    }

    public void ApplyCameraMode()
    {
        if (cameraTransform == null || sessionConfig == null)
        {
            return;
        }

        if (sessionConfig.CameraMode == CameraMode.Isometric)
        {
            cameraTransform.localPosition = sessionConfig.IsometricCameraPosition;
            cameraTransform.localRotation = Quaternion.Euler(sessionConfig.IsometricCameraRotation);
        }
        else
        {
            cameraTransform.localPosition = sessionConfig.ExplorationCameraPosition;
            cameraTransform.localRotation = Quaternion.Euler(sessionConfig.ExplorationCameraRotation);
        }
    }

    private void Update()
    {
        if (sessionConfig == null || playerController == null)
        {
            return;
        }

        if (sessionConfig.CameraMode == CameraMode.Isometric)
        {
            return;
        }

        float mouseDeltaX = Mouse.current != null ? Mouse.current.delta.ReadValue().x : 0f;
        float yaw = mouseDeltaX * Time.deltaTime * sessionConfig.MouseSensitivity;
        Rigidbody playerRb = playerController.GetComponent<Rigidbody>();
        if (playerRb != null)
        {
            playerRb.MoveRotation(playerRb.rotation * Quaternion.Euler(0f, yaw, 0f));
        }
        else
        {
            playerController.transform.Rotate(0f, yaw, 0f);
        }

        if (cameraTransform == null || cameraTransform.parent == null)
        {
            return;
        }

        Transform cameraParent = cameraTransform.parent;
        float t = Mathf.Clamp01(sessionConfig.CameraSmoothing * Time.deltaTime);
        cameraParent.rotation = Quaternion.Slerp(
            cameraParent.rotation,
            playerController.transform.rotation,
            t);
    }
}
