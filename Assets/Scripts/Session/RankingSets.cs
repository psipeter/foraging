using System.Collections.Generic;
using System.Globalization;

// What the ranking Interlude (InterludeManager) and the in-session ranking break (RankingBreak) share: the scoring of a set's implied pairs and its
// interlude_trials row (in TrialRow.Columns order; the pair columns are empty and `bushes` holds one object per bush in slot order).
public static class RankingSets
{
    public static string F(float value)
    {
        return value.ToString("0.####", CultureInfo.InvariantCulture);
    }

    // The pairs a ranking implies: every picked bush above every bush not picked, the picked ones in the order picked; a pair whose true values differ by
    // less than `tie` is not counted. `correct` are those whose higher-ranked bush is worth more.
    public static void ScorePairs(IReadOnlyList<int> setIds, IReadOnlyDictionary<int, float> values, IReadOnlyList<int> picks, float tie, out int correct, out int total)
    {
        var rest = new List<int>();
        foreach (int id in setIds)
        {
            if (!ContainsId(picks, id))
            {
                rest.Add(id);
            }
        }

        correct = 0;
        total = 0;
        for (int i = 0; i < picks.Count; i++)
        {
            var below = new List<int>();
            for (int j = i + 1; j < picks.Count; j++)
            {
                below.Add(picks[j]);
            }

            below.AddRange(rest);
            foreach (int other in below)
            {
                float gap = values[picks[i]] - values[other];
                if (UnityEngine.Mathf.Abs(gap) >= tie)
                {
                    total++;
                    if (gap > 0f)
                    {
                        correct++;
                    }
                }
            }
        }
    }

    private static bool ContainsId(IReadOnlyList<int> ids, int id)
    {
        for (int i = 0; i < ids.Count; i++)
        {
            if (ids[i] == id)
            {
                return true;
            }
        }

        return false;
    }

    // One bush of a set's `bushes` column. `rank` 0, `startTime` and `finishTime` below 0 mean not finished / not started.
    public static string BushObject(int id, int slot, float shape, float color, float moisture, float value, int rank, float startTime, float finishTime, int fruits)
    {
        return Json.Obj(("id", id), ("slot", slot), ("shape", shape), ("color", color), ("moisture", moisture), ("value", value),
            ("rank", rank > 0 ? (object)rank : null), ("start_time", startTime >= 0f ? (object)startTime : null),
            ("finish_time", finishTime >= 0f ? (object)finishTime : null), ("fruits", fruits));
    }

    // The cells of a set's interlude_trials row.
    public static string[] RowCells(int position, int trialIndex, float startX, float startZ, bool timedOut, float response, float firstHarvestTime, float bonus,
        float pausedSeconds, int setSize, int correct, int total, IEnumerable<string> bushObjects)
    {
        var cells = new List<string> { position.ToString(), trialIndex.ToString(), "ranking", "", F(startX), F(startZ) };
        for (int i = 0; i < 10; i++)
        {
            cells.Add("");                                  // left_* and right_*
        }

        cells.Add("");                                      // correct_side
        cells.Add("");                                      // choice
        cells.Add("");                                      // choice_correct
        cells.Add(timedOut ? "1" : "0");
        cells.Add(F(response));
        cells.Add(firstHarvestTime < 0f ? "" : F(firstHarvestTime));
        cells.Add("");                                      // first_harvest_side
        cells.Add("");                                      // left_fruits
        cells.Add("");                                      // right_fruits
        cells.Add(F(bonus));
        cells.Add("");                                      // locked_at
        cells.Add(F(pausedSeconds));
        cells.Add(setSize.ToString());
        cells.Add(correct.ToString());
        cells.Add(total.ToString());
        cells.Add("[" + string.Join(",", bushObjects) + "]");
        return cells.ToArray();
    }
}
