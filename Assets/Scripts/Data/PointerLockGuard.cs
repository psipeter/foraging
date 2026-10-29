using TMPro;
using UnityEngine;
using UnityEngine.InputSystem;
using UnityEngine.UI;

// In a browser the mouse is captured (pointer lock) only after a click, and Escape releases it whenever the participant
// presses it. While it is not held the game stands still behind "click to continue" (PauseGate), so looking around never
// stops working silently. Created by the Bootstrap scene on WebGL only.
public class PointerLockGuard : MonoBehaviour
{
    private GameObject _overlay;

    private void Awake()
    {
        _overlay = new GameObject("PointerGate", typeof(RectTransform), typeof(Canvas), typeof(CanvasScaler));
        _overlay.transform.SetParent(transform, false);
        var canvas = _overlay.GetComponent<Canvas>();
        canvas.renderMode = RenderMode.ScreenSpaceOverlay;
        canvas.sortingOrder = 5100;
        var scaler = _overlay.GetComponent<CanvasScaler>();
        scaler.uiScaleMode = CanvasScaler.ScaleMode.ScaleWithScreenSize;
        scaler.referenceResolution = new Vector2(1920f, 1080f);

        var dim = new GameObject("Dim", typeof(RectTransform), typeof(Image));
        dim.transform.SetParent(_overlay.transform, false);
        RectTransform dimRect = dim.GetComponent<RectTransform>();
        dimRect.anchorMin = Vector2.zero;
        dimRect.anchorMax = Vector2.one;
        dimRect.offsetMin = dimRect.offsetMax = Vector2.zero;
        dim.GetComponent<Image>().color = Color.black;

        var label = new GameObject("Message", typeof(RectTransform), typeof(TextMeshProUGUI));
        label.transform.SetParent(_overlay.transform, false);
        RectTransform rect = label.GetComponent<RectTransform>();
        rect.anchorMin = new Vector2(0.2f, 0.3f);
        rect.anchorMax = new Vector2(0.8f, 0.7f);
        rect.offsetMin = rect.offsetMax = Vector2.zero;
        var text = label.GetComponent<TextMeshProUGUI>();
        text.alignment = TextAlignmentOptions.Center;
        text.fontSize = 36f;
        text.color = Color.white;
        text.raycastTarget = false;
        text.text = "Click to continue";
        _overlay.SetActive(false);
    }

    private void Update()
    {
        bool held = Cursor.lockState == CursorLockMode.Locked;
        if (_overlay.activeSelf == held)
        {
            _overlay.SetActive(!held);
        }

        PauseGate.Pointer = !held;
        if (!held && Mouse.current != null && Mouse.current.leftButton.wasPressedThisFrame)
        {
            Cursor.lockState = CursorLockMode.Locked;
            Cursor.visible = false;
        }
    }
}
