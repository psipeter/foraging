using System.Collections;
using TMPro;
using UnityEngine;

// The screen at the end of a session: "Session 3 of 4", the points of that session very large in a panel, and under a rule the prompt
// as the last line of the panel. The world stays behind it and the camera turns slowly, so it is not a still frame. The music (UI/Music.cs) starts with it. Built at runtime.
public class ScoreScreen : MonoBehaviour
{
    private const float DegreesPerSecond = 3.5f;


    private TextMeshProUGUI _total, _ranking;
    private float _foraging, _rankingPoints;

    // `foraging` and `ranking` are the two parts of the session's points. With `split` (a session that has rankings) the total is shown in the middle with the two parts
    // smaller on either side, and after a moment the ranking part and the total count up together from the foraging score alone (the ranking points stay hidden until now).
    public static ScoreScreen Show(string partLabel, float foraging, float ranking, bool split, string prompt, CameraController camera)
    {
        Canvas canvas = UiStyle.Canvas("ScoreScreen", null, 4100);
        var screen = canvas.gameObject.AddComponent<ScoreScreen>();
        screen.Build(canvas.transform, partLabel, foraging, ranking, split, prompt);
        if (camera != null)
        {
            screen.StartCoroutine(screen.Drift(camera));
        }

        if (split)
        {
            screen.StartCoroutine(screen.CountUp());
        }

        return screen;
    }

    private void Build(Transform canvas, string partLabel, float foraging, float ranking, bool split, string prompt)
    {
        _foraging = foraging;
        _rankingPoints = ranking;
        UiStyle.Image(canvas, "Scrim", new Color(0.04f, 0.05f, 0.07f, 0.34f), Vector2.zero, Vector2.one, Vector2.zero, Vector2.zero).raycastTarget = false;
        Transform panel = UiStyle.Rounded(canvas, "Panel", UiStyle.Glass, 0f, 10f, 900f, 640f, UiStyle.PanelRadius).transform;
        UiStyle.Eyebrow(panel, $"{partLabel} complete", 0f, 262f, 780f, TextAlignmentOptions.Center);
        _total = UiStyle.Text(panel, "Points", $"{foraging + (split ? 0f : ranking):F0}", split ? 190f : 230f, TextAlignmentOptions.Center, 0f, 100f, split ? 460f : 780f, 260f);
        _total.font = UiStyle.DisplayFont;
        if (split)
        {
            const float sideX = 335f;
            UiStyle.Eyebrow(panel, "foraging", -sideX, 150f, 170f, TextAlignmentOptions.Center);
            TextMeshProUGUI left = UiStyle.Text(panel, "Foraging", $"{foraging:F0}", 66f, TextAlignmentOptions.Center, -sideX, 90f, 170f, 100f, UiStyle.Muted);
            left.font = UiStyle.DisplayFont;
            UiStyle.Eyebrow(panel, "ranking", sideX, 150f, 170f, TextAlignmentOptions.Center);
            _ranking = UiStyle.Text(panel, "Ranking", "0", 66f, TextAlignmentOptions.Center, sideX, 90f, 170f, 100f, UiStyle.Muted);
            _ranking.font = UiStyle.DisplayFont;
        }

        UiStyle.Text(panel, "Label", "points", UiStyle.Heading, TextAlignmentOptions.Center, 0f, -70f, 780f, 60f, UiStyle.Muted).font = UiStyle.DisplayFont;
        UiStyle.Rounded(panel, "Rule", new Color(1f, 1f, 1f, 0.16f), 0f, -150f, 780f, 2f, 1f);
        TextMeshProUGUI promptText = UiStyle.Text(panel, "Prompt", UiStyle.Chips(prompt), 34f, TextAlignmentOptions.Center, 0f, -222f, 780f, 56f, UiStyle.Ink);
        promptText.richText = true;
    }

    // The ranking points and the total count up together (ease-out); the total punches when they land.
    private IEnumerator CountUp()
    {
        const float delay = 0.8f, seconds = 1.4f;
        yield return new WaitForSecondsRealtime(delay);
        float elapsed = 0f;
        while (elapsed < seconds)
        {
            elapsed += Time.unscaledDeltaTime;
            float t = Mathf.Clamp01(elapsed / seconds);
            float eased = 1f - (1f - t) * (1f - t) * (1f - t);
            _ranking.text = $"{_rankingPoints * eased:F0}";
            _total.text = $"{_foraging + _rankingPoints * eased:F0}";
            yield return null;
        }

        _ranking.text = $"{_rankingPoints:F0}";
        _total.text = $"{_foraging + _rankingPoints:F0}";
        RectTransform rect = _total.rectTransform;
        for (float e = 0f; e < 0.25f; e += Time.unscaledDeltaTime)
        {
            rect.localScale = Vector3.one * Mathf.Lerp(1.12f, 1f, e / 0.25f);
            yield return null;
        }

        rect.localScale = Vector3.one;
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
