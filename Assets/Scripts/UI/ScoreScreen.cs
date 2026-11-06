using System.Collections;
using TMPro;
using UnityEngine;

// The screen at the end of a part, a session's or an Interlude's: "Part 3 of 14 complete", the points of that part very large in a panel, and the prompt. The
// world stays behind it and the camera turns slowly, so it is not a still frame. The music (UI/Music.cs) starts with it. Built at runtime.
public class ScoreScreen : MonoBehaviour
{
    private const float DegreesPerSecond = 3.5f;

    private Transform _promptHolder;

    public static ScoreScreen Show(int part, int partCount, float points, string prompt, CameraController camera)
    {
        Canvas canvas = UiStyle.Canvas("ScoreScreen", null, 4100);
        var screen = canvas.gameObject.AddComponent<ScoreScreen>();
        screen.Build(canvas.transform, part, partCount, points, prompt);
        if (camera != null)
        {
            screen.StartCoroutine(screen.Drift(camera));
        }

        return screen;
    }

    private void Build(Transform canvas, int part, int partCount, float points, string prompt)
    {
        UiStyle.Image(canvas, "Scrim", new Color(0.04f, 0.05f, 0.07f, 0.34f), Vector2.zero, Vector2.one, Vector2.zero, Vector2.zero).raycastTarget = false;
        Transform panel = UiStyle.Rounded(canvas, "Panel", UiStyle.Glass, 0f, 20f, 900f, 520f, UiStyle.PanelRadius).transform;
        UiStyle.Eyebrow(panel, $"Part {part} of {partCount} complete", 0f, 190f, 780f, TextAlignmentOptions.Center);
        TextMeshProUGUI number = UiStyle.Text(panel, "Points", $"{points:F0}", 230f, TextAlignmentOptions.Center, 0f, 20f, 780f, 260f);
        number.font = UiStyle.DisplayFont;
        UiStyle.Text(panel, "Label", "points", UiStyle.Heading, TextAlignmentOptions.Center, 0f, -150f, 780f, 60f, UiStyle.Muted).font = UiStyle.DisplayFont;
        _promptHolder = InstructionsScreen.Prompt(canvas, prompt);
    }

    // Replaces the prompt ("Loading the next part...").
    public void SetPrompt(string prompt)
    {
        if (_promptHolder != null)
        {
            Destroy(_promptHolder.gameObject);
        }

        _promptHolder = InstructionsScreen.Prompt(transform, prompt);
    }

    private IEnumerator Drift(CameraController camera)
    {
        float yaw = camera.Yaw;
        float pitch = camera.Pitch;
        while (true)
        {
            yaw += DegreesPerSecond * Time.unscaledDeltaTime;
            camera.SetView(yaw, pitch);
            yield return null;
        }
    }
}
