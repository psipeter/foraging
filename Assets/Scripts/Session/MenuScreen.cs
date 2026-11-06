using System.Collections.Generic;
using TMPro;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.InputSystem.UI;
using UnityEngine.UI;

// The experiment menu, shown by the Boot scene after the login and again whenever the participant comes back from an experiment: one row per
// experiment with its standing and a button (Start, Continue, or View code for a finished one), the ones whose prerequisites are not finished locked.
// Built at runtime like the other overlays. Without a data server (the Editor, a lab build) every experiment of the catalog is offered.
public class MenuScreen : MonoBehaviour
{
    public class Row
    {
        public string Code;
        public string Title;
        public string Detail;
        public string Action;      // the button's caption
        public bool Enabled;
    }

    private const int MaxRows = 6;

    public string ChosenCode { get; private set; }
    public bool Done => ChosenCode != null;

    public static MenuScreen Show(IList<Row> rows, string header, string footer)
    {
        Canvas canvas = UiStyle.Canvas("MenuScreen", null, 6000);
        canvas.gameObject.AddComponent<GraphicRaycaster>();
        if (FindAnyObjectByType<EventSystem>() == null)
        {
            new GameObject("EventSystem", typeof(EventSystem), typeof(InputSystemUIInputModule));
        }

        var screen = canvas.gameObject.AddComponent<MenuScreen>();
        screen.Build(rows, header, footer);
        return screen;
    }

    // The rows for a logged-in participant: the server's experiments in its order, each with the standing it reported.
    public static List<Row> OnlineRows(IReadOnlyList<ExperimentStanding> standings, ExperimentCatalog catalog)
    {
        var rows = new List<Row>();
        foreach (ExperimentStanding s in standings)
        {
            ExperimentConfig config = catalog != null ? catalog.Find(s.code) : null;
            var row = new Row { Code = s.code, Title = s.title };
            switch (s.status)
            {
                case "finished":
                    row.Detail = "Completed";
                    row.Action = "View code";
                    row.Enabled = true;
                    break;
                case "in_progress":
                    row.Detail = $"In progress: {s.sessions_done} of {s.n_sessions} parts done";
                    row.Action = "Continue";
                    row.Enabled = s.unlocked;
                    break;
                case "none":
                    row.Detail = s.unlocked ? $"{s.n_sessions} parts" : "Locked: " + PrerequisiteText(config, standings);
                    row.Action = "Start";
                    row.Enabled = s.unlocked;
                    break;
                default:
                    row.Detail = "Closed";
                    row.Action = "Closed";
                    break;
            }

            if (config == null && row.Enabled && s.status != "finished")
            {
                row.Detail = "Not available in this version of the game";
                row.Enabled = false;
            }

            rows.Add(row);
        }

        return rows;
    }

    // Without a server: every experiment of the catalog, unlocked.
    public static List<Row> OfflineRows(ExperimentCatalog catalog)
    {
        var rows = new List<Row>();
        if (catalog != null)
        {
            foreach (ExperimentConfig experiment in catalog.Experiments)
            {
                if (experiment != null)
                {
                    rows.Add(new Row { Code = experiment.Code, Title = experiment.Title, Detail = $"{experiment.Sessions.Count} parts", Action = "Start", Enabled = true });
                }
            }
        }

        return rows;
    }

    private static string PrerequisiteText(ExperimentConfig config, IReadOnlyList<ExperimentStanding> standings)
    {
        if (config == null || config.Requires.Count == 0)
        {
            return "not available yet";
        }

        var titles = new List<string>();
        foreach (string code in config.Requires)
        {
            string title = code;
            foreach (ExperimentStanding s in standings)
            {
                if (s.code == code)
                {
                    title = s.title;
                }
            }

            titles.Add(title);
        }

        return "finish " + string.Join(" and ", titles) + " first";
    }

    private void Build(IList<Row> rows, string header, string footer)
    {
        UiStyle.Image(transform, "Background", UiStyle.Panel, Vector2.zero, Vector2.one, Vector2.zero, Vector2.zero);
        UiStyle.Label(transform, "Title", "Experiments", UiStyle.Title, TextAlignmentOptions.Left, new Vector2(0.1f, 0.86f), new Vector2(0.9f, 0.96f));
        UiStyle.Label(transform, "Header", header, UiStyle.Small, TextAlignmentOptions.Left, new Vector2(0.1f, 0.8f), new Vector2(0.9f, 0.86f), UiStyle.Muted);
        const float rowHeight = 0.105f, gap = 0.02f;
        float top = 0.77f;
        for (int i = 0; i < rows.Count && i < MaxRows; i++)
        {
            BuildRow(rows[i], top - i * (rowHeight + gap), rowHeight);
        }

        UiStyle.Label(transform, "Footer", footer, UiStyle.Small, TextAlignmentOptions.Left, new Vector2(0.1f, 0.03f), new Vector2(0.9f, 0.09f), UiStyle.Muted);
    }

    private void BuildRow(Row row, float top, float height)
    {
        float bottom = top - height;
        UiStyle.Image(transform, "Row_" + row.Code, UiStyle.Field, new Vector2(0.1f, bottom), new Vector2(0.9f, top), Vector2.zero, Vector2.zero);
        UiStyle.Label(transform, "Title_" + row.Code, row.Title, UiStyle.Body, TextAlignmentOptions.BottomLeft,
            new Vector2(0.12f, bottom + height * 0.45f), new Vector2(0.62f, top - 0.005f), row.Enabled || row.Action == "View code" ? UiStyle.Ink : UiStyle.Muted);
        UiStyle.Label(transform, "Detail_" + row.Code, row.Detail, UiStyle.Small, TextAlignmentOptions.TopLeft,
            new Vector2(0.12f, bottom + 0.005f), new Vector2(0.62f, bottom + height * 0.5f), UiStyle.Muted);

        Image background = UiStyle.Image(transform, "Button_" + row.Code, UiStyle.Accent, new Vector2(0.68f, bottom + 0.012f), new Vector2(0.88f, top - 0.012f), Vector2.zero, Vector2.zero);
        UiStyle.Label(background.transform, "Text", row.Action, UiStyle.Body, TextAlignmentOptions.Center, Vector2.zero, Vector2.one, UiStyle.Panel);
        var button = background.gameObject.AddComponent<Button>();
        button.targetGraphic = background;
        ColorBlock colors = button.colors;
        colors.disabledColor = new Color(0.35f, 0.4f, 0.48f, 0.6f);
        button.colors = colors;
        button.interactable = row.Enabled;
        string code = row.Code;
        button.onClick.AddListener(() =>
        {
            ChosenCode = code;
            Destroy(gameObject);
        });
    }
}
