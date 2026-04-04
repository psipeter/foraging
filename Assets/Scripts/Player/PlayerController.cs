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
    [SerializeField] private Animator animator;
    [SerializeField] private Transform characterModel;
    [SerializeField] private CameraController cameraController;
    [SerializeField] private float harvestAnimationClipLength = 6.2f;

    private Rigidbody playerRigidbody;
    private CapsuleCollider _capsuleCollider;
    private Vector2 moveInput;
    private bool canHarvest;
    private bool _frozen;
    public bool IsFrozen => _frozen;
    private Tree _targetTree;

    private void Awake()
    {
        playerRigidbody = GetComponent<Rigidbody>();

        // Non-kinematic physics, no gravity, locked rotation for capsule movement.
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

        if (sessionConfig != null && sessionConfig.CameraMode == CameraMode.Exploration)
        {
            playerRigidbody.constraints = RigidbodyConstraints.FreezeRotationX |
                                          RigidbodyConstraints.FreezeRotationZ;
        }
    }

    private void FixedUpdate()
    {
        if (_frozen)
        {
            if (playerRigidbody != null)
            {
                playerRigidbody.linearVelocity = Vector3.zero;
            }

            if (animator != null)
            {
                animator.SetFloat("Speed", _frozen ? 0f : new Vector3(moveInput.x, 0f, moveInput.y).magnitude);
            }

            return;
        }

        Vector3 currentPos = playerRigidbody.position;
        Vector3 desiredVelocity;
        if (sessionConfig != null && sessionConfig.CameraMode == CameraMode.Exploration)
        {
            Vector3 localMove = new Vector3(moveInput.x, 0f, moveInput.y);
            Vector3 worldMove = transform.rotation * localMove;
            desiredVelocity = worldMove * moveSpeed;
        }
        else
        {
            desiredVelocity = new Vector3(moveInput.x, 0f, moveInput.y) * moveSpeed;
        }

        Vector3 v = playerRigidbody.linearVelocity;
        v.x = desiredVelocity.x;
        v.z = desiredVelocity.z;
        playerRigidbody.linearVelocity = v;

        if (characterModel != null && !_frozen && moveInput.sqrMagnitude > 0.01f)
        {
            Vector3 moveDir = sessionConfig != null && sessionConfig.CameraMode == CameraMode.Exploration
                ? (transform.rotation * new Vector3(moveInput.x, 0f, moveInput.y)).normalized
                : new Vector3(moveInput.x, 0f, moveInput.y).normalized;
            Quaternion targetRot = Quaternion.LookRotation(moveDir, Vector3.up);
            characterModel.rotation = Quaternion.Slerp(characterModel.rotation, targetRot, Time.fixedDeltaTime * 10f);
        }

        if (animator != null)
        {
            animator.SetFloat("Speed", _frozen ? 0f : new Vector3(moveInput.x, 0f, moveInput.y).magnitude);
        }

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
        if (yDiff > 0.05f)
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

            if (animator != null)
            {
                animator.SetTrigger("Harvest");
            }
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

    public void SetHarvestAnimationSpeed(float totalHarvestDuration)
    {
        if (animator != null && totalHarvestDuration > 0f)
        {
            animator.speed = harvestAnimationClipLength / totalHarvestDuration;
        }
    }

    public void ResetAnimationSpeed()
    {
        if (animator != null)
        {
            animator.speed = 1f;
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
