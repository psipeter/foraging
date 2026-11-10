using System.Text;
using TMPro;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.InputSystem.UI;
using UnityEngine.UI;

// The introduction: the page a participant sees after logging in and before the menu, and again whenever they open it from the menu (or from the (i) beside the points).
// It tells them what to know before playing: how they are paid, how long things take and whether they may stop, the sound. The text is StreamingAssets/introduction.txt: the
// first line is the title, then sections separated by a blank line, each a heading line followed by its text. Built at runtime like the other overlays.
public class IntroScreen : MonoBehaviour
{
    public const string File = "introduction.txt";

    public bool Done { get; private set; }

    // `buttonCaption`: "Continue" the first time, "Back to the menu" when opened from the menu.
    public static IntroScreen Show(string buttonCaption)
    {
        Canvas canvas = UiStyle.Canvas("IntroScreen", null, 6000);
        canvas.gameObject.AddComponent<GraphicRaycaster>();
        if (FindAnyObjectByType<EventSystem>() == null)
        {
            new GameObject("EventSystem", typeof(EventSystem), typeof(InputSystemUIInputModule));
        }

        var screen = canvas.gameObject.AddComponent<IntroScreen>();
        screen.Build(buttonCaption);
        return screen;
    }

    // The title and the body (the headings bold in the accent colour) of the text file.
    private static void Parse(out string title, out string body)
    {
        title = "Before you begin";
        body = "Introduction text not found (StreamingAssets/" + File + ").";
        if (!StreamingData.Exists(File))
        {
            return;
        }

        string[] sections = StreamingData.ReadText(File).Replace("\r", "").Trim().Split(new[] { "\n\n" }, System.StringSplitOptions.RemoveEmptyEntries);
        if (sections.Length == 0)
        {
            return;
        }

        title = sections[0].Trim();
        string accent = ColorUtility.ToHtmlStringRGB(UiStyle.Accent);
        var text = new StringBuilder();
        for (int i = 1; i < sections.Length; i++)
        {
            string[] lines = sections[i].Trim().Split('\n');
            text.Append($"<b><color=#{accent}>{lines[0].Trim()}</color></b>\n");
            text.Append(string.Join("\n", lines, 1, lines.Length - 1).Trim());
            text.Append(i < sections.Length - 1 ? "\n\n" : "");
        }

        body = text.ToString();
    }

    private void Build(string buttonCaption)
    {
        Parse(out string title, out string body);
        UiStyle.Backdrop(transform);
        Transform panel = UiStyle.Rounded(transform, "Panel", UiStyle.Glass, 0f, 0f, 1340f, 900f, UiStyle.PanelRadius).transform;
        UiStyle.Eyebrow(panel, "Introduction", 0f, 376f, 1228f);
        UiStyle.Text(panel, "Title", title, 60f, TextAlignmentOptions.Left, 0f, 306f, 1228f, 80f);
        ConsentScreen.BuildScroll(panel, body, 0f, -4f, 1228f, 540f);
        UiStyle.Pill(panel, "Continue", buttonCaption, 414f, -358f, 400f, () =>
        {
            Done = true;
            Destroy(gameObject);
        });
    }
}
