using UnityEngine;
using UnityEngine.InputSystem;
#if UNITY_EDITOR
using UnityEditor;
#endif

public class QuitHandler : MonoBehaviour
{
    private void Update()
    {
        // In a browser Escape is the browser's: it releases the mouse capture (PointerLockGuard then asks for a click), and
        // Application.Quit() would stop the whole runtime and leave a blank page.
        if (Application.platform == RuntimePlatform.WebGLPlayer)
        {
            return;
        }

        if (Keyboard.current == null || !Keyboard.current.escapeKey.wasPressedThisFrame)
        {
            return;
        }

        Cursor.lockState = CursorLockMode.None;
        Cursor.visible = true;

#if UNITY_EDITOR
        EditorApplication.isPlaying = false;
#else
        Application.Quit();
#endif
    }
}
