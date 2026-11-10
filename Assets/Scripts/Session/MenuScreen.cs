using System.Collections.Generic;
using TMPro;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.InputSystem.UI;
using UnityEngine.UI;

// The experiment menu, shown by the Boot scene after the login and again whenever the participant comes back from an experiment: one row per
// experiment on one line: its name, its length (sessions and minutes, or the progress and the time left), its prerequisite (the experiments to finish first) and a button
// (Start, Continue, or View code for a finished one); the ones whose prerequisites are not finished are locked. Near the bottom of the screen, buttons open the introduction
// and the consent form again: they end the menu with a ChosenCode that is not an experiment (IntroductionCode, ConsentCode) and the caller shows the page and the menu again.
// Sessions are counted without their Interludes (a session and its Interlude are Part A and Part B of one session); a reduced run (RunModes) shows its own lengths.
// Built at runtime like the other overlays. Without a data server (the Editor, a lab build) every experiment of the catalog is offered.
public class MenuScreen : MonoBehaviour
{
    public class Row
    {
        public string Code;
        public string Title;
        public string Detail;      // the length column: "21 sessions · ~65 min", the progress, or "Completed"
        public string Action;      // the button's caption
        public bool Enabled;
        public string Requires;    // the titles of the experiments to finish first, "-" for none
        public bool Unmet;         // locked: a prerequisite is not finished
        public int PillStyle;      // 0 accent, 1 good (completed), 2 muted (locked or closed): the colour of the length column
        public float Progress = -1f;   // the share of its parts done, for a bar under the length; negative: no bar
    }

    private const int MaxRows = 6;

    public const string IntroductionCode = "@introduction";
    public const string ConsentCode = "@consent";

    public string ChosenCode { get; private set; }
    public bool Done => ChosenCode != null;

    public static MenuScreen Show(IList<Row> rows, string header, string footer, bool consentLink = false)
    {
        Canvas canvas = UiStyle.Canvas("MenuScreen", null, 6000);
        canvas.gameObject.AddComponent<GraphicRaycaster>();
        if (FindAnyObjectByType<EventSystem>() == null)
        {
            new GameObject("EventSystem", typeof(EventSystem), typeof(InputSystemUIInputModule));
        }

        var screen = canvas.gameObject.AddComponent<MenuScreen>();
        screen.Build(rows, header, footer, consentLink);
        return screen;
    }

    // The sessions (not their Interludes) among the first `parts` entries of a list of sessions and Interludes.
    private static int CountSessions(IList<SessionConfig> list, int parts = int.MaxValue)
    {
        int count = 0;
        for (int i = 0; i < list.Count && i < parts; i++)
        {
            count += list[i] != null && list[i].IsInterlude ? 0 : 1;
        }

        return count;
    }

    // The minutes of what a participant plays now: the experiment's estimate, or, for a reduced run, worked out from what is played.
    private static float MinutesOf(ExperimentConfig config, IList<SessionConfig> played)
    {
        return RunModes.Active ? ExperimentConfig.MinutesOf(played, RunModes.Short) : config.EstimatedMinutes;
    }

    // "21 sessions · ~65 min", or without the time when the experiment is not in this build.
    private static string LengthText(ExperimentConfig config, int sessions)
    {
        string count = sessions == 1 ? "1 session" : $"{sessions} sessions";
        return config != null ? $"{count} · ~{MinutesOf(config, RunModes.Apply(config.Sessions)):F0} min" : count;
    }

    // The rows for a logged-in participant: the server's experiments in its order, each with the standing it reported.
    public static List<Row> OnlineRows(IReadOnlyList<ExperimentStanding> standings, ExperimentCatalog catalog)
    {
        var rows = new List<Row>();
        foreach (ExperimentStanding s in standings)
        {
            ExperimentConfig config = catalog != null ? catalog.Find(s.code) : null;
            List<SessionConfig> played = config != null ? RunModes.Apply(config.Sessions) : null;
            int sessions = played != null ? CountSessions(played) : s.n_sessions;
            var row = new Row { Code = s.code, Title = s.title, Requires = RequiresText(config, catalog), Unmet = !s.unlocked };
            switch (s.status)
            {
                case "finished":
                    row.Action = "View code";
                    row.Enabled = true;
                    row.Detail = "Completed";
                    row.Progress = 1f;
                    row.PillStyle = 1;
                    break;
                case "in_progress":
                    // the server counts completed sessions and Interludes alike (sessions_done), so the bar follows that and the caption counts the sessions
                    row.Action = "Continue";
                    row.Enabled = s.unlocked;
                    if (played != null)
                    {
                        row.Progress = played.Count > 0 ? Mathf.Clamp01(s.sessions_done / (float)played.Count) : 0f;
                        row.Detail = $"{CountSessions(played, s.sessions_done)} of {sessions} · ~{MinutesOf(config, played) * (1f - row.Progress):F0} min left";
                    }
                    else
                    {
                        row.Progress = s.n_sessions > 0 ? Mathf.Clamp01(s.sessions_done / (float)s.n_sessions) : 0f;
                        row.Detail = "In progress";
                    }

                    break;
                case "none":
                    row.Detail = LengthText(config, sessions);
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
                    rows.Add(new Row
                    {
                        Code = experiment.Code, Title = experiment.Title, Detail = LengthText(experiment, CountSessions(RunModes.Apply(experiment.Sessions))), Action = "Start", Enabled = true,
                        Requires = RequiresText(experiment, catalog)
                    });
                }
            }
        }

        return rows;
    }

    // The titles of the experiments to finish first, "-" for none.
    private static string RequiresText(ExperimentConfig config, ExperimentCatalog catalog)
    {
        if (config == null || config.Requires.Count == 0)
        {
            return "-";
        }

        var titles = new List<string>();
        foreach (string code in config.Requires)
        {
            ExperimentConfig required = catalog != null ? catalog.Find(code) : null;
            titles.Add(required != null ? required.Title : code);
        }

        return string.Join(", ", titles);
    }

    private const string MenuTitle = "Foraging Study";

    // The panel's columns (x from the row's centre): the name at the left edge, then the length, the prerequisite and the actions (the button).
    private const float RowWidth = 1388f, NameX = -482f, NameWidth = 360f, LengthX = -100f, LengthWidth = 360f, RequiresX = 270f, RequiresWidth = 340f, ButtonX = 575f, ButtonWidth = 190f;

    private void Build(IList<Row> rows, string header, string footer, bool consentLink)
    {
        UiStyle.Backdrop(transform);
        int n = Mathf.Min(rows.Count, MaxRows);
        const float rowHeight = 96f, rowGap = 16f, headerHeight = 44f, pad = 48f;
        float height = pad * 2f + headerHeight + n * (rowHeight + rowGap) - rowGap;
        Transform panel = UiStyle.Rounded(transform, "Panel", UiStyle.Glass, 0f, 0f, 1500f, height, UiStyle.PanelRadius).transform;
        float top = height / 2f - pad;
        Header(panel, "Experiment", NameX, NameWidth, top - headerHeight / 2f);
        Header(panel, "Length", LengthX, LengthWidth, top - headerHeight / 2f);
        Header(panel, "Prerequisite", RequiresX, RequiresWidth, top - headerHeight / 2f);
        Header(panel, "Actions", ButtonX, ButtonWidth, top - headerHeight / 2f);
        float y = top - headerHeight - rowHeight / 2f;
        for (int i = 0; i < n; i++)
        {
            BuildRow(panel, rows[i], y, rowHeight);
            y -= rowHeight + rowGap;
        }

        UiStyle.Text(transform, "Title", MenuTitle, UiStyle.Title, TextAlignmentOptions.Center, 0f, height / 2f + 84f, 1288f, 100f).font = UiStyle.DisplayFont;

        // near the bottom of the screen: the pages the participant may open again (the consent form to the left of the introduction)
        float buttonsY = -UiStyle.ReferenceResolution.y / 2f + 130f;
        const float spacing = 290f;
        float x = consentLink ? spacing / 2f : 0f;
        UiStyle.Pill(transform, "Introduction", "Introduction", x, buttonsY, 260f, () => Choose(IntroductionCode), true, 64f);
        if (consentLink)
        {
            UiStyle.Pill(transform, "Consent", "Consent form", x - spacing, buttonsY, 260f, () => Choose(ConsentCode), true, 64f);
        }

        if (!string.IsNullOrEmpty(footer))
        {
            UiStyle.Text(transform, "Footer", footer, UiStyle.Small, TextAlignmentOptions.Center, 0f, buttonsY + 60f, 1288f, 36f, UiStyle.Muted);
        }
    }

    private void Choose(string code)
    {
        ChosenCode = code;
        Destroy(gameObject);
    }

    private static void Header(Transform panel, string caption, float x, float width, float y)
    {
        UiStyle.Text(panel, "Header_" + caption, caption, 22f, TextAlignmentOptions.MidlineLeft, x, y, width, 34f, UiStyle.Muted).font = UiStyle.BoldFont;
    }

    private void BuildRow(Transform panel, Row row, float y, float height)
    {
        Transform r = UiStyle.Rounded(panel, "Row_" + row.Code, UiStyle.FieldGlass, 0f, y, RowWidth, height, 22f).transform;
        bool dim = !row.Enabled && row.Action != "View code";
        TextMeshProUGUI name = UiStyle.Text(r, "Name", row.Title, 38f, TextAlignmentOptions.MidlineLeft, NameX, 0f, NameWidth, 56f, dim ? UiStyle.Muted : UiStyle.Ink);
        name.font = UiStyle.DisplayFont;
        name.enableAutoSizing = true;                                  // a long title shrinks to its column
        name.fontSizeMin = 24f;
        name.fontSizeMax = 38f;
        name.textWrappingMode = TextWrappingModes.NoWrap;

        Color tint = row.PillStyle == 1 ? UiStyle.Good : row.PillStyle == 2 ? UiStyle.Muted : new Color(0.66f, 0.80f, 1f);
        bool bar = row.Progress >= 0f;
        TextMeshProUGUI length = UiStyle.Text(r, "Length", row.Detail, 26f, TextAlignmentOptions.MidlineLeft, LengthX, bar ? 12f : 0f, LengthWidth, 40f, tint);
        length.font = UiStyle.BoldFont;
        length.textWrappingMode = TextWrappingModes.NoWrap;
        if (bar)
        {
            // a finished experiment is a full green bar, one under way a partly filled accent one
            const float barWidth = 300f;
            float left = LengthX - LengthWidth / 2f;
            UiStyle.Rounded(r, "Bar", new Color(1f, 1f, 1f, 0.12f), left + barWidth / 2f, -22f, barWidth, 10f, 5f);
            float fillWidth = Mathf.Max(barWidth * row.Progress, 10f);
            UiStyle.Rounded(r, "BarFill", row.PillStyle == 1 ? UiStyle.Good : UiStyle.Accent, left + fillWidth / 2f, -22f, fillWidth, 10f, 5f);
        }

        TextMeshProUGUI requires = UiStyle.Text(r, "Requires", row.Requires, 26f, TextAlignmentOptions.MidlineLeft, RequiresX, 0f, RequiresWidth, 56f,
            row.Unmet ? new Color(0.95f, 0.62f, 0.45f) : row.Requires == "-" ? UiStyle.Muted : UiStyle.Ink);
        requires.font = UiStyle.DisplayFont;
        requires.enableAutoSizing = true;
        requires.fontSizeMin = 18f;
        requires.fontSizeMax = 26f;
        requires.textWrappingMode = TextWrappingModes.NoWrap;

        string code = row.Code;
        Button button = UiStyle.Pill(r, "Button", row.Action, ButtonX, 0f, ButtonWidth, () => Choose(code), row.Action == "View code", 64f);
        button.interactable = row.Enabled;
    }
}
