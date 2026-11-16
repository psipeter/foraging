using UnityEngine;

// Fades a full-screen overlay (the "Paused" screen, the data gate) in and out instead of switching it on and off: `OverlayFade.SetShown` is the way to show or hide one.
// Real time, since the game is held still behind it. The object stays active while it fades out and is deactivated when it is gone.
public class OverlayFade : MonoBehaviour
{
    private const float Seconds = 0.2f;

    private CanvasGroup _group;
    private bool _shown;

    // An overlay that is on screen from now (at full opacity) and fades out when SetShown(false) is called: a cover over a scene that is not ready yet.
    public static void Prepare(GameObject overlay)
    {
        OverlayFade fade = overlay.AddComponent<OverlayFade>();
        fade._group = overlay.AddComponent<CanvasGroup>();
        fade._group.alpha = 1f;
        fade._shown = true;
    }

    public static void SetShown(GameObject overlay, bool shown)
    {
        OverlayFade fade = overlay.GetComponent<OverlayFade>();
        if (fade == null)
        {
            if (!shown)
            {
                return;
            }

            fade = overlay.AddComponent<OverlayFade>();
            fade._group = overlay.AddComponent<CanvasGroup>();
            fade._group.alpha = 0f;
        }

        fade._shown = shown;
        if (shown && !overlay.activeSelf)
        {
            fade._group.alpha = 0f;
            overlay.SetActive(true);
        }
    }

    private void Update()
    {
        _group.alpha = Mathf.MoveTowards(_group.alpha, _shown ? 1f : 0f, Time.unscaledDeltaTime / Seconds);
        if (!_shown && _group.alpha <= 0f)
        {
            gameObject.SetActive(false);
        }
    }
}
