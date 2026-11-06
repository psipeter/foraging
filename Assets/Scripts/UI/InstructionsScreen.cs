using TMPro;
using UnityEngine;

// The instruction screen of a part (and the "welcome back" screen): a wide panel centred on the screen (its text left-aligned) with the part number, the central instruction as a title, the
// text, and under a rule the prompt ("Press Enter to begin") as the last line of the text, over the world. Built at runtime; [Key] in
// the text becomes a key chip.
public class InstructionsScreen : MonoBehaviour
{
    private const float PanelWidth = 1640f;
    private const float BodySize = 36f;

    private GameObject _root;
    public bool Visible => _root != null && _root.activeSelf;

    public static InstructionsScreen Create()
    {
        Canvas canvas = UiStyle.Canvas("InstructionsScreen", null, 4000);
        var screen = canvas.gameObject.AddComponent<InstructionsScreen>();
        screen._root = canvas.gameObject;
        canvas.gameObject.SetActive(false);
        return screen;
    }

    public void Show(string eyebrow, string title, string body, string prompt)
    {
        foreach (Transform child in _root.transform)
        {
            Destroy(child.gameObject);
        }

        _root.SetActive(true);
        UiStyle.Image(_root.transform, "Scrim", new Color(0.04f, 0.05f, 0.07f, 0.34f), Vector2.zero, Vector2.one, Vector2.zero, Vector2.zero).raycastTarget = false;

        const float pad = 56f, textWidth = PanelWidth - 2f * pad;
        body = UiStyle.Chips(body.Trim());
        TextMeshProUGUI measure = UiStyle.Text(_root.transform, "Measure", body, BodySize, TextAlignmentOptions.TopLeft, 0f, 0f, textWidth, 100f, UiStyle.Ink);
        measure.richText = true;
        measure.textWrappingMode = TextWrappingModes.Normal;
        measure.lineSpacing = 8f;
        float bodyHeight = measure.GetPreferredValues(body, textWidth, 0f).y + 12f;
        Destroy(measure.gameObject);

        // eyebrow, title, text, a rule, the prompt
        float height = pad * 2f + 36f + 20f + 90f + 20f + bodyHeight + 28f + 2f + 28f + 48f;
        Transform panel = UiStyle.Rounded(_root.transform, "Panel", UiStyle.Glass, 0f, 0f, PanelWidth, height, UiStyle.PanelRadius).transform;
        float y = height / 2f - pad;
        if (!string.IsNullOrEmpty(eyebrow))
        {
            UiStyle.Eyebrow(panel, eyebrow, 0f, y - 18f, textWidth);
        }

        y -= 36f + 20f;
        UiStyle.Text(panel, "Title", title, UiStyle.Title, TextAlignmentOptions.Left, 0f, y - 45f, textWidth, 90f);
        y -= 90f + 20f;
        TextMeshProUGUI text = UiStyle.Text(panel, "Body", body, BodySize, TextAlignmentOptions.TopLeft, 0f, y - bodyHeight / 2f, textWidth, bodyHeight, UiStyle.Ink);
        text.richText = true;
        text.textWrappingMode = TextWrappingModes.Normal;
        text.lineSpacing = 8f;
        y -= bodyHeight + 28f;
        UiStyle.Rounded(panel, "Rule", new Color(1f, 1f, 1f, 0.16f), 0f, y, textWidth, 2f, 1f);
        y -= 2f + 28f;
        TextMeshProUGUI promptText = UiStyle.Text(panel, "Prompt", UiStyle.Chips(prompt), 34f, TextAlignmentOptions.MidlineLeft, 0f, y - 24f, textWidth, 48f, UiStyle.Ink);
        promptText.richText = true;
    }

    public void Hide()
    {
        _root.SetActive(false);
    }
}
