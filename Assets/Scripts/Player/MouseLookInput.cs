using UnityEngine;
using UnityEngine.InputSystem;

[RequireComponent(typeof(PlayerInput))]
public class MouseLookInput : MonoBehaviour, ILookInput
{
    private InputAction _look;

    private void Awake()
    {
        _look = GetComponent<PlayerInput>().actions["Look"];
    }

    public Vector2 ReadLookDelta()
    {
        return _look != null ? _look.ReadValue<Vector2>() : Vector2.zero;
    }
}
