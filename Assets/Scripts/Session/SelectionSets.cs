using System.Collections.Generic;
using System.Globalization;
using UnityEngine;

// What a selection break (SelectionBreak) uses to score a set and to log its ranking_sets row (in SetRow.Columns order; `bushes` holds one object per bush in slot order).
public static class SelectionSets
{
    public static string F(float value)
    {
        return value.ToString("0.####", CultureInfo.InvariantCulture);
    }

    // The payout rule: a set has one pair per two of its bushes, those whose true values differ by less than `tie` left out (`total`). A pair is `correct` only when
    // both bushes were picked and the one picked first is worth more; a pair with an unpicked bush (a timed-out set) is never correct, so leaving bushes unranked
    // costs every pair they are in. `weight` is the sum of `PairWeight` over the correct pairs: the set pays the bonus times it. (scripts/selection.py selections_to_points is the same rule.)
    public static void ScorePairs(IReadOnlyList<int> setIds, IReadOnlyDictionary<int, float> values, IReadOnlyList<int> picks, float tie, string mode, out int correct, out int total, out float weight)
    {
        correct = 0;
        total = 0;
        weight = 0f;
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
                    weight += PairWeight(mode, values[setIds[i]], values[setIds[j]]);
                }
            }
        }
    }

    // What a correct pair is worth, in units of the bonus: "pair_mean_value" the mean of its two true values, any other mode (the default "pair") one. (scripts/selection.py pair_weight.)
    public static float PairWeight(string mode, float valueA, float valueB)
    {
        return mode == "pair_mean_value" ? (valueA + valueB) * 0.5f : 1f;
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

    // The dense design's score (scripts/selection.py top_k_score is the same rule): 0 to `scale`, the picked values' sum against the best `k` of the grid, from the expected sum of k random bushes
    // (k times the grid's mean value); fewer picks than k (a timed-out selection) simply sum fewer values.
    public static float TopKScore(IReadOnlyList<float> pickedValues, IReadOnlyList<float> allValues, int k, float scale)
    {
        var sorted = new List<float>(allValues);
        sorted.Sort((a, b) => b.CompareTo(a));
        float best = 0f, mean = 0f;
        for (int i = 0; i < sorted.Count; i++)
        {
            mean += sorted[i];
            if (i < k)
            {
                best += sorted[i];
            }
        }

        float baseline = k * (sorted.Count > 0 ? mean / sorted.Count : 0f);
        if (best - baseline <= 1e-9f)
        {
            return 0f;
        }

        float got = 0f;
        for (int i = 0; i < pickedValues.Count && i < k; i++)
        {
            got += pickedValues[i];
        }

        return scale * Mathf.Clamp01((got - baseline) / (best - baseline));
    }

    // How many of the picked bushes are among the grid's best k (the ranking_sets row's `correct_pairs` in the dense design; `total_pairs` is k).
    public static int TopKHits(IReadOnlyList<int> pickedIds, IReadOnlyDictionary<int, float> valuesById, int k)
    {
        var ids = new List<int>(valuesById.Keys);
        ids.Sort((a, b) => valuesById[b].CompareTo(valuesById[a]));
        int hits = 0;
        foreach (int id in pickedIds)
        {
            if (ids.IndexOf(id) >= 0 && ids.IndexOf(id) < k)
            {
                hits++;
            }
        }

        return hits;
    }

    // Which selection (0-based) pays when only one does: drawn from the world seed (scripts/selection.py paid_set_index).
    public static int PaidSetIndex(int seed, int count)
    {
        ulong h = ((ulong)(uint)seed * 2654435761UL) >> 8;
        return (int)(h % (ulong)System.Math.Max(count, 1));
    }
}
