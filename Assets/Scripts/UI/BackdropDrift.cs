using UnityEngine;

// A very slow zoom and sway of a full-screen image (the backdrop of the screens before the game), so it is not a still picture.
public class BackdropDrift : MonoBehaviour
{
    private RectTransform _rect;

    private void Awake()
    {
        _rect = GetComponent<RectTransform>();
    }

    private void Update()
    {
        float t = Time.unscaledTime;
        _rect.localScale = Vector3.one * (1.06f + 0.025f * Mathf.Sin(t * 0.05f));
        _rect.anchoredPosition = new Vector2(Mathf.Sin(t * 0.04f) * 26f, Mathf.Cos(t * 0.031f) * 12f);
    }
}
