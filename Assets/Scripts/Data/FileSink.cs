using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Text;

// The local copy of a run: the database's tables as files, <root>/<run_id>/<session:00>/ (scripts/rundata.py reads this
// layout; docs/ONLINE_DATA_PLAN.md, section 2b). Always written, so a participant's computer keeps a backup of what was
// uploaded and an offline run is complete on its own.
public class FileSink : IDataSink, IDisposable
{
    private class SessionFiles
    {
        public string Folder;
        public StreamWriter Events, Trajectory, Trials;
    }

    private static readonly CultureInfo Inv = CultureInfo.InvariantCulture;
    private readonly string _runFolder;
    private readonly string _runId;
    private readonly Dictionary<int, SessionFiles> _sessions = new Dictionary<int, SessionFiles>();
    private readonly HashSet<int> _resumed = new HashSet<int>();

    public FileSink(string root, string runId, string runJson)
    {
        _runId = runId;
        _runFolder = Path.Combine(root, runId);
        Directory.CreateDirectory(_runFolder);
        string runFile = Path.Combine(_runFolder, "run.json");
        if (!File.Exists(runFile))        // a continued run keeps the file from its start
        {
            File.WriteAllText(runFile, runJson);
        }
    }

    // The session continues an interrupted one: keep only the local rows the server also holds (the first `next` rows of each
    // file) so the sequence numbers carry on without a gap or a repeat, and append from there. Missing files (the participant
    // is on another computer) are created when the first row arrives, starting at the server's sequence number.
    public void PrepareResume(int sessionIndex, int eventsNext, int trajectoryNext, int trialsNext)
    {
        string folder = Path.Combine(_runFolder, sessionIndex.ToString("00", Inv));
        TruncateRows(Path.Combine(folder, "events.csv"), eventsNext);
        TruncateRows(Path.Combine(folder, "trajectory.csv"), trajectoryNext);
        TruncateRows(Path.Combine(folder, "interlude_trials.csv"), trialsNext);
        _resumed.Add(sessionIndex);
    }

    private static void TruncateRows(string path, int keep)
    {
        if (!File.Exists(path))
        {
            return;
        }

        string[] lines = File.ReadAllLines(path);
        if (lines.Length - 1 > keep)
        {
            var kept = new string[keep + 1];
            Array.Copy(lines, kept, keep + 1);
            File.WriteAllLines(path, kept);
        }
    }

    public void Write(DataBatch batch)
    {
        SessionFiles s = Open(batch.SessionIndex);
        if (batch.SessionJson != null)
        {
            // the sessions row plus the identifiers the database takes from the request
            File.WriteAllText(Path.Combine(s.Folder, "session.json"),
                "{\"run_id\":" + Json.Quote(_runId) + "," + batch.SessionJson.Substring(1));
        }

        foreach (EventRow e in batch.Events)
        {
            s.Events.Write(string.Join(",", e.Seq.ToString(Inv), e.T.ToString("F6", Inv),
                float.IsNaN(e.Real) ? "" : e.Real.ToString("F3", Inv), e.Type,
                e.TreeId >= 0 ? e.TreeId.ToString(Inv) : "", e.K >= 0 ? e.K.ToString(Inv) : "",
                float.IsNaN(e.Reward) ? "" : e.Reward.ToString("F0", Inv),
                float.IsNaN(e.RunningTotal) ? "" : e.RunningTotal.ToString("F0", Inv),
                e.Payload != null ? Csv(e.Payload) : ""));
            s.Events.Write('\n');
        }

        for (int i = 0; i < batch.Frames.Count; i++)
        {
            FrameQ f = batch.Frames[i];
            s.Trajectory.Write(string.Join(",", (batch.FirstFrameSeq + i).ToString(Inv), (f.T * TrajectoryCodec.TStep).ToString("F6", Inv),
                (f.X * TrajectoryCodec.XzStep).ToString("F2", Inv), (f.Z * TrajectoryCodec.XzStep).ToString("F2", Inv),
                (f.Yaw * TrajectoryCodec.AngleStep).ToString("F2", Inv), (f.Pitch * TrajectoryCodec.AngleStep).ToString("F2", Inv),
                f.Keys.ToString(Inv)));
            s.Trajectory.Write('\n');
        }

        if (batch.Plan != null)
        {
            File.WriteAllText(Path.Combine(s.Folder, "interlude_plan.json"), "{\"trial_order\":[" + string.Join(",", batch.Plan) + "]}");
        }

        foreach (TrialRow t in batch.Trials)
        {
            var cells = new string[t.Cells.Length + 1];
            cells[0] = t.Seq.ToString(Inv);
            for (int i = 0; i < t.Cells.Length; i++)
            {
                cells[i + 1] = Csv(t.Cells[i]);
            }

            if (s.Trials == null)
            {
                s.Trials = Writer(s.Folder, "interlude_trials.csv",
                    "seq," + string.Join(",", Array.ConvertAll(TrialRow.Columns, c => c.name)), _resumed.Contains(batch.SessionIndex));
            }

            s.Trials.Write(string.Join(",", cells));
            s.Trials.Write('\n');
        }

        s.Events.Flush();
        s.Trajectory.Flush();
        s.Trials?.Flush();
    }

    public void Dispose()
    {
        foreach (SessionFiles s in _sessions.Values)
        {
            s.Events?.Dispose();
            s.Trajectory?.Dispose();
            s.Trials?.Dispose();
        }

        _sessions.Clear();
    }

    private SessionFiles Open(int index)
    {
        if (!_sessions.TryGetValue(index, out SessionFiles s))
        {
            string folder = Path.Combine(_runFolder, index.ToString("00", Inv));
            Directory.CreateDirectory(folder);
            s = new SessionFiles
            {
                Folder = folder,
                Events = Writer(folder, "events.csv", "seq,t,real,type,tree_id,k,reward,running_total,payload", _resumed.Contains(index)),
                Trajectory = Writer(folder, "trajectory.csv", "seq,t,x,z,yaw,pitch,keys", _resumed.Contains(index)),
            };
            _sessions[index] = s;
        }

        return s;
    }

    // `append`: continue an existing file (a resumed session) instead of starting it with its header.
    private static StreamWriter Writer(string folder, string name, string header, bool append = false)
    {
        string path = Path.Combine(folder, name);
        bool existing = append && File.Exists(path);
        var writer = new StreamWriter(path, existing, new UTF8Encoding(false), 1 << 16);
        if (!existing)
        {
            writer.Write(header);
            writer.Write('\n');
        }

        return writer;
    }

    private static string Csv(string value)
    {
        return value.IndexOfAny(new[] { ',', '"', '\n' }) >= 0 ? "\"" + value.Replace("\"", "\"\"") + "\"" : value;
    }
}
