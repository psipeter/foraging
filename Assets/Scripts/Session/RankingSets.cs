using System.Collections.Generic;
using System.Globalization;

// What a ranking break (RankingBreak) uses to score a set and to log its ranking_sets row (in SetRow.Columns order; `bushes` holds one object per bush in slot order).
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

    // The cells of a set's ranking_sets row, in SetRow.Columns order.
    public static string[] RowCells(int position, int poolIndex, float startX, float startZ, bool timedOut, float response, float firstHarvestTime, float bonus,
        float pausedSeconds, int setSize, int correct, int total, IEnumerable<string> bushObjects)
    {
        return new[]
        {
            position.ToString(), poolIndex.ToString(), F(startX), F(startZ), timedOut ? "1" : "0", F(response),
            firstHarvestTime < 0f ? "" : F(firstHarvestTime), F(bonus), F(pausedSeconds),
            setSize.ToString(), correct.ToString(), total.ToString(), "[" + string.Join(",", bushObjects) + "]",
        };
    }
}
