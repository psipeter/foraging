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
        public bool ShowPoints;    // online: the points column has an entry for this row
        public float Points;       // what the participant has earned in it so far (counted in the total only when CountsTowardTotal)
        public bool CountsTowardTotal = true;
        public int PillStyle;      // 0 accent, 1 good (completed), 2 muted (locked or closed)
        public float Progress = -1f;   // the share of its parts done, for a bar; negative: no bar
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
            var row = new Row { Code = s.code, Title = s.title, ShowPoints = true, Points = s.points, CountsTowardTotal = config == null || config.CountsTowardTotal };
            switch (s.status)
            {
                case "finished":
                    row.Action = "View code";
                    row.Enabled = true;
                    row.Progress = 1f;
                    row.PillStyle = 1;
                    break;
                case "in_progress":
                    row.Action = "Continue";
                    row.Enabled = s.unlocked;
                    row.Progress = s.n_sessions > 0 ? Mathf.Clamp01(s.sessions_done / (float)s.n_sessions) : 0f;
                    break;
                case "none":
                    row.Detail = s.unlocked ? $"{(config != null ? config.SessionCount : s.n_sessions)} sessions" : PrerequisiteText(config, standings).Replace("finish", "Finish");
                    row.PillStyle = s.unlocked ? 0 : 2;
                    row.Action = "Start";
                    row.Enabled = s.unlocked;
                    break;
                default:
                    row.Detail = "Closed";
                    row.Action = "Closed";
                    row.PillStyle = 2;
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
                    rows.Add(new Row { Code = experiment.Code, Title = experiment.Title, Detail = $"{experiment.SessionCount} sessions", Action = "Start", Enabled = true });
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

    private const string MenuTitle = "Foraging Study";

    private void Build(IList<Row> rows, string header, string footer)
    {
        UiStyle.Backdrop(transform);
        int n = Mathf.Min(rows.Count, MaxRows);
        bool anyPoints = false;
        float total = 0f;
        for (int i = 0; i < n; i++)
        {
            anyPoints |= rows[i].ShowPoints;
            total += rows[i].ShowPoints && rows[i].CountsTowardTotal ? rows[i].Points : 0f;
        }

        const float rowHeight = 150f, rowGap = 20f, headerHeight = 0f, totalHeight = 96f, pad = 56f;
        float height = pad * 2f + headerHeight + n * (rowHeight + rowGap) + (anyPoints ? totalHeight : 0f);
        Transform panel = UiStyle.Rounded(transform, "Panel", UiStyle.Glass, 0f, 0f, 1400f, height, UiStyle.PanelRadius).transform;
        float top = height / 2f - pad;
        float y = top - headerHeight - rowHeight / 2f;
        for (int i = 0; i < n; i++)
        {
            BuildRow(panel, rows[i], y, rowHeight);
            y -= rowHeight + rowGap;
        }

        if (anyPoints)
        {
            float lineY = y + rowHeight / 2f + rowGap / 2f - 6f;
            UiStyle.Rounded(panel, "TotalLine", new Color(1f, 1f, 1f, 0.18f), 0f, lineY, 1288f, 2f, 1f);
            UiStyle.Text(panel, "TotalLabel", "Total points", UiStyle.Heading, TextAlignmentOptions.MidlineLeft, -292f, lineY - 48f, 640f, 60f).font = UiStyle.DisplayFont;
            UiStyle.Text(panel, "TotalPoints", $"{total:F0}", UiStyle.Heading, TextAlignmentOptions.MidlineRight, 275f, lineY - 48f, 150f, 60f).font = UiStyle.DisplayFont;
        }

        UiStyle.Text(transform, "Title", MenuTitle, UiStyle.Title, TextAlignmentOptions.Center, 0f, height / 2f + 84f, 1288f, 100f).font = UiStyle.DisplayFont;

        if (!string.IsNullOrEmpty(footer))
        {
            UiStyle.Text(transform, "Footer", footer, UiStyle.Small, TextAlignmentOptions.Center, 0f, -height / 2f - 40f, 1288f, 36f, UiStyle.Muted);
        }
    }

    private void BuildRow(Transform panel, Row row, float y, float height)
    {
        Transform r = UiStyle.Rounded(panel, "Row_" + row.Code, UiStyle.FieldGlass, 0f, y, 1288f, height, 22f).transform;
        bool dim = !row.Enabled && row.Action != "View code";
        TextMeshProUGUI name = UiStyle.Text(r, "Name", row.Title, 42f, TextAlignmentOptions.MidlineLeft, -292f, 36f, 640f, 52f, dim ? UiStyle.Muted : UiStyle.Ink);
        name.font = UiStyle.DisplayFont;

        if (row.Progress >= 0f)
        {
            // a finished experiment is a full green bar, one under way a partly filled accent one; neither has a caption
            UiStyle.Rounded(r, "Bar", new Color(1f, 1f, 1f, 0.12f), -644f + 32f + 260f, -22f, 520f, 12f, 6f);
            float fillWidth = Mathf.Max(520f * row.Progress, 12f);
            UiStyle.Rounded(r, "BarFill", row.PillStyle == 1 ? UiStyle.Good : UiStyle.Accent, -644f + 32f + fillWidth / 2f, -22f, fillWidth, 12f, 6f);
        }
        else
        {
            float pillWidth = Mathf.Min(620f, 46f + row.Detail.Length * 14f);
            Color tint = row.PillStyle == 2 ? UiStyle.Muted : new Color(0.66f, 0.80f, 1f);
            Color fill = row.PillStyle == 2 ? new Color(1f, 1f, 1f, 0.10f) : new Color(0.36f, 0.62f, 0.95f, 0.20f);
            Transform pill = UiStyle.Rounded(r, "Pill", fill, -644f + 32f + pillWidth / 2f, -14f, pillWidth, 38f, 19f).transform;
            TextMeshProUGUI pillText = UiStyle.Text(pill, "Text", row.Detail, 24f, TextAlignmentOptions.Center, 0f, 0f, pillWidth, 38f, tint);
            pillText.font = UiStyle.BoldFont;
        }

        if (row.ShowPoints)
        {
            TextMeshProUGUI points = UiStyle.Text(r, "Points", row.CountsTowardTotal ? $"{row.Points:F0}" : "-", UiStyle.Heading, TextAlignmentOptions.MidlineRight, 275f, 0f, 150f, 60f,
                row.CountsTowardTotal ? UiStyle.Ink : UiStyle.Muted);
            points.font = UiStyle.DisplayFont;
        }

        string code = row.Code;
        Button button = UiStyle.Pill(r, "Button", row.Action, 497f, 0f, 230f, () =>
        {
            ChosenCode = code;
            Destroy(gameObject);
        }, row.Action == "View code", 68f);
        button.interactable = row.Enabled;
    }
}
