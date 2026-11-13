using System.Collections.Generic;
using System.Globalization;

// What a ranking break (RankingBreak) uses to score a set and to log its ranking_sets row (in SetRow.Columns order; `bushes` holds one object per bush in slot order).
public static class RankingSets
{
    public static string F(float value)
    {
        return value.ToString("0.####", CultureInfo.InvariantCulture);
    }

    // The payout rule: a set has one pair per two of its bushes, those whose true values differ by less than `tie` left out (`total`). A pair is `correct` only when
    // both bushes were picked and the one picked first is worth more; a pair with an unpicked bush (a timed-out set) is never correct, so leaving bushes unranked
    // costs every pair they are in. (scripts/ranking.py pair_scores is the same rule.)
    public static void ScorePairs(IReadOnlyList<int> setIds, IReadOnlyDictionary<int, float> values, IReadOnlyList<int> picks, float tie, out int correct, out int total)
    {
        correct = 0;
        total = 0;
        for (int i = 0; i < setIds.Count; i++)
        {
            for (int j = i + 1; j < setIds.Count; j++)
            {
                float gap = values[setIds[i]] - values[setIds[j]];
                if (UnityEngine.Mathf.Abs(gap) < tie)
                {
                    continue;
                }

                total++;
                int first = IndexOf(picks, setIds[i]);
                int second = IndexOf(picks, setIds[j]);
                if (first >= 0 && second >= 0 && (first < second) == (gap > 0f))
                {
                    correct++;
                }
            }
        }
    }

    private static int IndexOf(IReadOnlyList<int> ids, int id)
    {
        for (int i = 0; i < ids.Count; i++)
        {
            if (ids[i] == id)
            {
                return i;
            }
        }

        return -1;
    }

    // One bush of a set's `bushes` column. `rank` 0, `startTime` and `finishTime` below 0 mean not finished / not started.
    public static string BushObject(int id, int slot, float shape, float color, float moisture, float value, int rank, float startTime, float finishTime, int fruits)
    {
        return Json.Obj(("id", id), ("slot", slot), ("shape", shape), ("color", color), ("moisture", moisture), ("value", value),
            ("rank", rank > 0 ? (object)rank : null), ("start_time", startTime >= 0f ? (object)startTime : null),
            ("finish_time", finishTime >= 0f ? (object)finishTime : null), ("fruits", fruits));
    }

    // The cells of a set's ranking_sets row, in SetRow.Columns order.
    public static string[] RowCells(int position, int poolIndex, float startX, float startZ, bool timedOut, float response, float firstHarvestTime, float points,
        float pausedSeconds, int setSize, int correct, int total, IEnumerable<string> bushObjects)
    {
        return new[]
        {
            position.ToString(), poolIndex.ToString(), F(startX), F(startZ), timedOut ? "1" : "0", F(response),
            firstHarvestTime < 0f ? "" : F(firstHarvestTime), F(points), F(pausedSeconds),
            setSize.ToString(), correct.ToString(), total.ToString(), "[" + string.Join(",", bushObjects) + "]",
        };
    }
}
