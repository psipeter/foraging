using System.Text.RegularExpressions;
using TMPro;
using UnityEngine;

// The instruction screen of a part (and the "welcome back" screen): a panel at the left of the screen with the part number, the central instruction as a title,
// the text, and a prompt at the bottom ("Press Enter to begin"), over the world, which stays visible to its right. Built at runtime; [Key] in the text becomes a key chip.
public class InstructionsScreen : MonoBehaviour
{
    private GameObject _root;
    private Transform _panelHolder;
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

        const float width = 1060f, pad = 56f, textWidth = width - 2f * pad;
        body = Regex.Replace(body.Trim(), @"\[([^\]]+)\]", m => UiStyle.Chip(m.Groups[1].Value));
        TextMeshProUGUI measure = UiStyle.Text(_root.transform, "Measure", body, UiStyle.Body, TextAlignmentOptions.TopLeft, 0f, 0f, textWidth, 100f, UiStyle.Ink);
        measure.richText = true;
        measure.textWrappingMode = TextWrappingModes.Normal;
        measure.lineSpacing = 8f;
        float bodyHeight = measure.GetPreferredValues(body, textWidth, 0f).y + 12f;
        Destroy(measure.gameObject);

        float height = pad * 2f + 36f + 20f + 90f + 20f + bodyHeight;
        Transform panel = UiStyle.Rounded(_root.transform, "Panel", UiStyle.Glass, -270f, 0f, width, height, UiStyle.PanelRadius).transform;
        float top = height / 2f - pad;
        if (!string.IsNullOrEmpty(eyebrow))
        {
            UiStyle.Eyebrow(panel, eyebrow, 0f, top - 18f, textWidth);
        }

        UiStyle.Text(panel, "Title", title, UiStyle.Title, TextAlignmentOptions.Left, 0f, top - 36f - 20f - 45f, textWidth, 90f);
        TextMeshProUGUI text = UiStyle.Text(panel, "Body", body, UiStyle.Body, TextAlignmentOptions.TopLeft, 0f, top - 36f - 20f - 90f - 20f - bodyHeight / 2f, textWidth, bodyHeight, UiStyle.Ink);
        text.richText = true;
        text.textWrappingMode = TextWrappingModes.Normal;
        text.lineSpacing = 8f;
        Prompt(_root.transform, prompt);
    }

    // The pill at the bottom of the screen, the same on every part's screens.
    public static Transform Prompt(Transform parent, string prompt)
    {
        string text = Regex.Replace(prompt, @"\[([^\]]+)\]", m => UiStyle.Chip(m.Groups[1].Value));
        float width = Mathf.Min(1100f, 150f + Regex.Replace(prompt, @"\[|\]", "").Length * 17f);
        Transform pill = UiStyle.Rounded(parent, "Prompt", new Color(0.078f, 0.086f, 0.118f, 0.78f), 0f, -440f, width, 68f, 34f).transform;
        TextMeshProUGUI label = UiStyle.Text(pill, "Text", text, 32f, TextAlignmentOptions.Center, 0f, 0f, width, 68f, UiStyle.Ink);
        label.richText = true;
        return pill;
    }

    public void Hide()
    {
        _root.SetActive(false);
    }
}
