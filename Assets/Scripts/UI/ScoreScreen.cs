using System.Collections;
using TMPro;
using UnityEngine;

// The screen at the end of a part, a session's or an Interlude's: "Part 3 of 14 complete", the points of that part very large in a panel, and under a rule the prompt
// as the last line of the panel. The world stays behind it and the camera turns slowly, so it is not a still frame. The music (UI/Music.cs) starts with it. Built at runtime.
public class ScoreScreen : MonoBehaviour
{
    private const float DegreesPerSecond = 3.5f;


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
        Transform panel = UiStyle.Rounded(canvas, "Panel", UiStyle.Glass, 0f, 10f, 900f, 640f, UiStyle.PanelRadius).transform;
        UiStyle.Eyebrow(panel, $"Part {part} of {partCount} complete", 0f, 262f, 780f, TextAlignmentOptions.Center);
        TextMeshProUGUI number = UiStyle.Text(panel, "Points", $"{points:F0}", 230f, TextAlignmentOptions.Center, 0f, 100f, 780f, 260f);
        number.font = UiStyle.DisplayFont;
        UiStyle.Text(panel, "Label", "points", UiStyle.Heading, TextAlignmentOptions.Center, 0f, -70f, 780f, 60f, UiStyle.Muted).font = UiStyle.DisplayFont;
        UiStyle.Rounded(panel, "Rule", new Color(1f, 1f, 1f, 0.16f), 0f, -150f, 780f, 2f, 1f);
        TextMeshProUGUI promptText = UiStyle.Text(panel, "Prompt", UiStyle.Chips(prompt), 34f, TextAlignmentOptions.Center, 0f, -222f, 780f, 56f, UiStyle.Ink);
        promptText.richText = true;
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
