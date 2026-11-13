using System.Collections.Generic;
using System.Globalization;
using System.Text;

// What the recorder produces and the sinks consume. The columns are those of the database tables and of the local
// layout scripts/rundata.py reads (docs/ONLINE_DATA_PLAN.md, section 1).
public class EventRow
{
    public int Seq;
    public double T;            // unpaused session seconds
    public float Real;          // seconds since the logger started
    public string Type;
    public int TreeId = -1;
    public int K = -1;
    public float Reward = float.NaN;
    public float RunningTotal = float.NaN;
    public string Payload;      // a JSON object, or null

    public string ToJson()
    {
        return Json.Obj(("seq", Seq), ("t", T), ("real", Real), ("type", Type), ("tree_id", TreeId >= 0 ? (object)TreeId : null),
            ("k", K >= 0 ? (object)K : null), ("reward", Reward), ("running_total", RunningTotal),
            ("payload", Payload != null ? new Json.Raw(Payload) : (object)null));
    }
}

// One ranking set: the cells of ranking_sets.csv after `seq`, in Columns order, already formatted ('' = missing).
public class SetRow
{
    public int Seq;
    public string[] Cells;

    // name, kind (I integer, F float, S text, J raw JSON), in the order of the table.
    public static readonly (string name, char kind)[] Columns =
    {
        ("set_index", 'I'), ("pool_index", 'I'), ("start_x", 'F'), ("start_z", 'F'), ("timed_out", 'I'), ("response_time", 'F'),
        ("first_harvest_time", 'F'), ("bonus", 'F'), ("paused_seconds", 'F'),
        // the set's size, the implied pairs ordered right and counted, and one JSON object per bush (J: raw JSON)
        ("set_size", 'I'), ("correct_pairs", 'I'), ("total_pairs", 'I'), ("bushes", 'J'),
    };

    public string ToJson()
    {
        var sb = new StringBuilder("{").Append("\"seq\":").Append(Seq.ToString(CultureInfo.InvariantCulture));
        for (int i = 0; i < Columns.Length; i++)
        {
            string cell = i < Cells.Length ? Cells[i] : "";
            sb.Append(',').Append(Json.Quote(Columns[i].name)).Append(':');
            sb.Append(cell == "" ? "null" : Columns[i].kind == 'S' ? Json.Quote(cell) : cell);
        }

        return sb.Append('}').ToString();
    }
}

// Everything recorded since the last flush, for one session.
public class DataBatch
{
    public int SessionIndex;
    public string SessionJson;                  // the session row (first and last batch of a session), or null
    public List<EventRow> Events = new List<EventRow>();
    public List<FrameQ> Frames = new List<FrameQ>();
    public int FirstFrameSeq;
    public List<SetRow> Sets = new List<SetRow>();
    public float SubmitTime;                    // Time.realtimeSinceStartup when handed to the pipeline

    public bool IsEmpty => SessionJson == null && Events.Count == 0 && Frames.Count == 0 && Sets.Count == 0;
}
