using UnityEngine;
using UnityEngine.InputSystem;

[RequireComponent(typeof(Rigidbody))]
public class PlayerController : MonoBehaviour
{
    public float moveSpeed = 5f;
    public SessionConfig sessionConfig;
    [SerializeField] private TerrainManager terrainManager;
    [SerializeField] private float groundOffset = 1.0f;
    [SerializeField] private HarvestManager harvestManager;
    [SerializeField] private CameraController cameraController;

    private Rigidbody playerRigidbody;
    private CapsuleCollider _capsuleCollider;
    private Vector2 moveInput;
    private bool canHarvest;
    private bool _frozen;
    public bool IsFrozen => _frozen;
    public float GroundOffset => groundOffset;
    private Tree _targetTree;

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
        if (_frozen)
        {
            if (playerRigidbody != null)
            {
                playerRigidbody.linearVelocity = Vector3.zero;
            }

            return;
        }

        Vector3 currentPos = playerRigidbody.position;
        // W/S move along the camera's heading; A/D are ignored.
        float yaw = cameraController != null ? cameraController.Yaw : 0f;
        Vector3 desiredVelocity = Quaternion.Euler(0f, yaw, 0f) * new Vector3(0f, 0f, moveInput.y) * moveSpeed;

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

        float targetY = currentPos.y;
        if (terrainManager != null)
        {
            Vector3 rayOrigin = new Vector3(currentPos.x, currentPos.y + 5f, currentPos.z);
            int mask = terrainManager.GroundObject != null ? (1 << terrainManager.GroundObject.layer) : -1;

            if (Physics.Raycast(rayOrigin, Vector3.down, out RaycastHit hit, 100f, mask, QueryTriggerInteraction.Ignore))
            {
                targetY = hit.point.y + groundOffset;
            }
            else
            {
                targetY = terrainManager.SampleElevation(currentPos.x, currentPos.z) + groundOffset;
            }
        }

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

    public void OnHarvest(InputAction.CallbackContext context)
    {
        if (!context.performed)
        {
            return;
        }

        if (!canHarvest)
        {
            return;
        }

        if (harvestManager != null && harvestManager.IsHarvesting)
        {
            return;
        }

        if (harvestManager != null && _targetTree != null)
        {
            harvestManager.StartHarvest(_targetTree);
        }
    }

    private void OnTriggerEnter(Collider other)
    {
        Tree tree = other.GetComponentInParent<Tree>();
        if (tree != null)
        {
            canHarvest = true;
            _targetTree = tree;
            _targetTree.SetHighlight(true);
        }
    }

    private void OnTriggerExit(Collider other)
    {
        Tree tree = other.GetComponentInParent<Tree>();
        if (tree != null)
        {
            canHarvest = false;
            tree.SetHighlight(false);
            _targetTree = null;
        }
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

    public void ClearTarget()
    {
        if (_targetTree != null)
        {
            _targetTree.SetHighlight(false);
        }

        _targetTree = null;
        canHarvest = false;
    }
}
