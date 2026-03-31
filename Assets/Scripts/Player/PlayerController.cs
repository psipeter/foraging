using UnityEngine;
using UnityEngine.InputSystem;

[RequireComponent(typeof(Rigidbody))]
public class PlayerController : MonoBehaviour
{
    [SerializeField] private float moveSpeed = 5f;
    [SerializeField] private TerrainManager terrainManager;
    [SerializeField] private float groundOffset = 1.0f;

    private Rigidbody playerRigidbody;
    private Vector2 moveInput;
    private bool canHarvest;

    private void Awake()
    {
        playerRigidbody = GetComponent<Rigidbody>();

        // Terrain drives Y position, so ensure Y-position freezing is disabled.
        playerRigidbody.constraints &= ~RigidbodyConstraints.FreezePositionY;

        playerRigidbody.isKinematic = true;
        playerRigidbody.useGravity = false;
    }

    private void FixedUpdate()
    {
        Vector3 currentPos = playerRigidbody.position;
        Vector3 delta = new Vector3(moveInput.x, 0f, moveInput.y) * moveSpeed * Time.fixedDeltaTime;

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

        playerRigidbody.position = new Vector3(currentPos.x + delta.x, targetY, currentPos.z + delta.z);
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
        if (!context.performed || !canHarvest)
        {
            return;
        }

        Harvest();
    }

    private void OnTriggerEnter(Collider other)
    {
        if (other.CompareTag("Interactable"))
        {
            canHarvest = true;
        }
    }

    private void OnTriggerExit(Collider other)
    {
        if (other.CompareTag("Interactable"))
        {
            canHarvest = false;
        }
    }

    private void Harvest()
    {
    }
}
