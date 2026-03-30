using UnityEngine;
using UnityEngine.InputSystem;

[RequireComponent(typeof(Rigidbody))]
public class PlayerController : MonoBehaviour
{
    [SerializeField] private float moveSpeed = 5f;

    private Rigidbody playerRigidbody;
    private Vector2 moveInput;
    private bool canHarvest;

    private void Awake()
    {
        playerRigidbody = GetComponent<Rigidbody>();
    }

    private void FixedUpdate()
    {
        Vector3 movement = new Vector3(moveInput.x, 0f, moveInput.y) * moveSpeed;
        playerRigidbody.linearVelocity = new Vector3(movement.x, playerRigidbody.linearVelocity.y, movement.z);
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
