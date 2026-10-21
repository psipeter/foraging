using UnityEngine;
using UnityEngine.InputSystem;

[RequireComponent(typeof(Rigidbody))]
public class PlayerController : MonoBehaviour
{
    public float moveSpeed = 5f;
    public SessionConfig sessionConfig;
    [SerializeField] private TerrainManager terrainManager;
    [SerializeField] private float groundOffset = 1.0f;
    [SerializeField] private CameraController cameraController;

    private Rigidbody playerRigidbody;
    private CapsuleCollider _capsuleCollider;
    private Vector2 moveInput;
    private bool _frozen;
    private bool _movementLocked;
    private bool _harvestHeld;
    private bool _harvestPressed;

    // Session end: no movement and no looking.
    public bool IsFrozen => _frozen;
    public float GroundOffset => groundOffset;
    public bool HarvestHeld => _harvestHeld;
    // Raw W/S/A/D input (the DataLogger records which keys are held).
    public Vector2 MoveInput => moveInput;

    private void Awake()
    {
        playerRigidbody = GetComponent<Rigidbody>();
        if (cameraController == null)
        {
            cameraController = GetComponent<CameraController>();
        }

        // Non-kinematic physics, no gravity, locked rotation for capsule movement. Facing direction
        // lives on the camera (see CameraController), not on this body.
        playerRigidbody.isKinematic = false;
        playerRigidbody.useGravity = false;
        playerRigidbody.constraints = RigidbodyConstraints.FreezeRotationX |
                                      RigidbodyConstraints.FreezeRotationY |
                                      RigidbodyConstraints.FreezeRotationZ;
        playerRigidbody.interpolation = RigidbodyInterpolation.Interpolate;

        // Ensure a capsule collider with a low-friction physics material.
        _capsuleCollider = GetComponent<CapsuleCollider>();
        if (_capsuleCollider == null)
        {
            _capsuleCollider = gameObject.AddComponent<CapsuleCollider>();
        }

        PhysicsMaterial mat = new PhysicsMaterial("PlayerCapsuleMaterial")
        {
            dynamicFriction = 0f,
            staticFriction = 0f,
            bounciness = 0f,
            frictionCombine = PhysicsMaterialCombine.Minimum,
            bounceCombine = PhysicsMaterialCombine.Minimum
        };
        _capsuleCollider.material = mat;
    }

    private void FixedUpdate()
    {
        // Harvesting locks walking only (looking stays free); session end freezes everything.
        if (_frozen || _movementLocked)
        {
            if (playerRigidbody != null)
            {
                playerRigidbody.linearVelocity = Vector3.zero;
            }

            return;
        }

        Vector3 currentPos = playerRigidbody.position;
        // W/S move along the camera's heading at full speed; A/D are ignored. The WASD composite is normalized,
        // so W+A would read as y = 0.71; use only its sign so holding A/D never slows the walk.
        float forward = Mathf.Abs(moveInput.y) > 0.01f ? Mathf.Sign(moveInput.y) : 0f;
        float yaw = cameraController != null ? cameraController.Yaw : 0f;
        Vector3 desiredVelocity = Quaternion.Euler(0f, yaw, 0f) * new Vector3(0f, 0f, forward) * moveSpeed;

        // Mountains are unclimbable: refuse movement into non-walkable terrain, sliding along it when
        // one axis is still free. (Height is a raycast snap, so physics would not stop the player.)
        if (terrainManager != null && (desiredVelocity.x != 0f || desiredVelocity.z != 0f))
        {
            float nextX = currentPos.x + desiredVelocity.x * Time.fixedDeltaTime;
            float nextZ = currentPos.z + desiredVelocity.z * Time.fixedDeltaTime;
            if (!terrainManager.IsWalkable(nextX, nextZ))
            {
                if (terrainManager.IsWalkable(nextX, currentPos.z))
                {
                    desiredVelocity.z = 0f;
                }
                else if (terrainManager.IsWalkable(currentPos.x, nextZ))
                {
                    desiredVelocity.x = 0f;
                }
                else
                {
                    desiredVelocity.x = 0f;
                    desiredVelocity.z = 0f;
                }
            }
        }

        Vector3 v = playerRigidbody.linearVelocity;
        v.x = desiredVelocity.x;
        v.z = desiredVelocity.z;
        playerRigidbody.linearVelocity = v;

        float targetY = GroundTargetY(currentPos);

        float yDiff = Mathf.Abs(playerRigidbody.position.y - targetY);
        // Tight threshold: the camera sits at eye level, so larger height steps would read as jitter.
        if (yDiff > 0.001f)
        {
            Vector3 pos = playerRigidbody.position;
            pos.y = targetY;
            playerRigidbody.position = pos;

            v = playerRigidbody.linearVelocity;
            v.y = 0f;
            playerRigidbody.linearVelocity = v;
        }
    }

    // Terrain following is a raycast in FixedUpdate, which does not run while the game is paused (instruction
    // screens set Time.timeScale to 0). Snap to the ground at startup and keep snapping while paused, so the
    // camera never shows a frame below (or above) the new world's terrain before the first step.
    private void Start()
    {
        SnapToTerrain();
    }

    private void Update()
    {
        if (Time.timeScale <= 0f)
        {
            SnapToTerrain();
        }
    }

    private void SnapToTerrain()
    {
        if (terrainManager == null || playerRigidbody == null)
        {
            return;
        }

        Vector3 pos = playerRigidbody.position;
        float targetY = GroundTargetY(pos);
        if (Mathf.Abs(pos.y - targetY) <= 0.001f)
        {
            return;
        }

        pos.y = targetY;
        playerRigidbody.position = pos;
        transform.position = pos;   // a paused physics step would not move the transform (interpolation)
    }

    // Height the player should stand at over `pos`: the terrain surface (collider raycast, falling back to the
    // terrain grid before the collider exists) plus the ground offset.
    private float GroundTargetY(Vector3 pos)
    {
        if (terrainManager == null)
        {
            return pos.y;
        }

        Vector3 rayOrigin = new Vector3(pos.x, pos.y + 5f, pos.z);
        int mask = terrainManager.GroundObject != null ? (1 << terrainManager.GroundObject.layer) : -1;

        if (Physics.Raycast(rayOrigin, Vector3.down, out RaycastHit hit, 100f, mask, QueryTriggerInteraction.Ignore))
        {
            return hit.point.y + groundOffset;
        }

        return terrainManager.SampleElevation(pos.x, pos.z) + groundOffset;
    }

    // Moves the player to (x, z) standing on the terrain (the Interlude teleports between trial stages).
    public void TeleportTo(float x, float z)
    {
        float y = terrainManager != null ? terrainManager.SampleElevation(x, z) + groundOffset : transform.position.y;
        Vector3 pos = new Vector3(x, y, z);
        if (playerRigidbody != null)
        {
            playerRigidbody.position = pos;
            playerRigidbody.linearVelocity = Vector3.zero;
        }

        transform.position = pos;
    }

    public void OnMove(InputAction.CallbackContext context)
    {

        if (context.canceled)
        {
            moveInput = Vector2.zero;
            return;
        }

        if (context.performed)
        {
            moveInput = context.ReadValue<Vector2>();
        }
    }

    // Space: started = pressed, canceled = released (Invoke Unity Events fires all phases).
    public void OnHarvest(InputAction.CallbackContext context)
    {
        if (context.started)
        {
            _harvestHeld = true;
            _harvestPressed = true;
        }
        else if (context.canceled)
        {
            _harvestHeld = false;
        }
    }

    // True once per Space press; the caller decides whether a press can start a harvest.
    public bool ConsumeHarvestPress()
    {
        bool pressed = _harvestPressed;
        _harvestPressed = false;
        return pressed;
    }

    public void SetMovementLocked(bool locked)
    {
        _movementLocked = locked;
    }

    public void SetFrozen(bool frozen)
    {
        _frozen = frozen;
        if (frozen)
        {
            moveInput = Vector2.zero;
            if (playerRigidbody != null)
            {
                playerRigidbody.linearVelocity = Vector3.zero;
            }
        }
    }
}
