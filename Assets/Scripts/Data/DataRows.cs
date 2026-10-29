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

// One Interlude trial: the cells of interlude_trials.csv after `seq`, in TrialColumns order, already formatted ('' = missing).
public class TrialRow
{
    public int Seq;
    public string[] Cells;

    // name, kind (I integer, F float, S text), in the order of the table.
    public static readonly (string name, char kind)[] Columns =
    {
        ("presented_order", 'I'), ("trial_index", 'I'), ("type", 'S'), ("varied_feature", 'S'), ("stage_x", 'F'), ("stage_z", 'F'),
        ("left_id", 'I'), ("left_shape", 'F'), ("left_color", 'F'), ("left_moisture", 'F'), ("left_value", 'F'),
        ("right_id", 'I'), ("right_shape", 'F'), ("right_color", 'F'), ("right_moisture", 'F'), ("right_value", 'F'),
        ("correct_side", 'S'), ("choice", 'S'), ("choice_correct", 'I'), ("timed_out", 'I'), ("response_time", 'F'),
        ("first_harvest_time", 'F'), ("first_harvest_side", 'S'), ("left_fruits", 'I'), ("right_fruits", 'I'), ("bonus", 'F'), ("locked_at", 'F'),
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
    public int[] Plan;                          // the Interlude's trial order, in its first batch
    public List<TrialRow> Trials = new List<TrialRow>();
    public float SubmitTime;                    // Time.realtimeSinceStartup when handed to the pipeline

    public bool IsEmpty => SessionJson == null && Events.Count == 0 && Frames.Count == 0 && Plan == null && Trials.Count == 0;
}

public interface IDataSink
{
    void Write(DataBatch batch);
}
