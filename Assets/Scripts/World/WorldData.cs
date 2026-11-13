using System;
using System.Collections.Generic;
using System.IO;
using System.IO.Compression;
using System.Text;
using UnityEngine;

// A generated world, loaded from StreamingAssets/Experiments/<code>/<session>_seed<seed>.world. The files are written by
// scripts/world.py (the source of truth for placement, attributes, terrain fields and per-fruit rewards);
// Unity only renders and plays them. Format (version 2): "FWLD", uint32 version, uint32 header length, JSON header, then one gzip
// stream of the terrain grids (res * res each, index i * res + j, i across X, j across Z), each an array of little-endian 8 or 16 bit
// codes c (header gridBits) meaning gridMin + c * (gridMax - gridMin) / (2^bits - 1). Version 1 stored the grids as raw float32 and
// still loads.
public class WorldData
{
    public const int FormatVersion = 2;

    [Serializable]
    private class Header
    {
        public int version;
        public string session;
        public int seed;
        public int res;
        public float halfExtent;
        public int treeCount;
        public int fruitCount;
        public string[] grids;
        public int[] gridBits;
        public float[] gridMin;
        public float[] gridMax;
        public float[] treePos;
        public float[] shape;
        public float[] color;
        public float[] moisture;
        public float[] canopyRadius;
        public float[] value;
        public int[] fruitRewards;
        public string[] checkNames;
        public float[] checkValues;
        public float tileRadius;
        public float tileRamp;
        public float[] tileCentres;
    }

    public string Path { get; private set; }
    public string Session { get; private set; }
    public int Seed { get; private set; }
    public int Res { get; private set; }
    public float HalfExtent { get; private set; }

    public int TreeCount { get; private set; }
    public int FruitCount { get; private set; }
    public float[] TreePos { get; private set; }          // x0, z0, x1, z1, ...
    public float[] Shape { get; private set; }
    public float[] Color { get; private set; }
    public float[] Moisture { get; private set; }
    public float[] CanopyRadius { get; private set; }
    public float[] Value { get; private set; }            // R_bush, the true mean reward per fruit
    public int[] FruitRewards { get; private set; }       // TreeCount * FruitCount: reward of the k-th fruit taken

    // Terrain grids on the mesh vertices.
    public float[] MoistureGrid { get; private set; }
    public float[] ElevationGrid { get; private set; }
    public float[] RockGrid { get; private set; }
    public float[] SnowGrid { get; private set; }
    public float[] RampGrid { get; private set; }

    // A tiles layout (scripts/world.py): the tile centres (x0, z0, x1, z1, ...), circumradius and ramp width. The tile of a point is the one with the nearest centre.
    public float[] TileCentres { get; private set; }
    public float TileRadius { get; private set; }
    public float TileRamp { get; private set; }
    public bool HasTiles => TileCentres != null && TileCentres.Length >= 2;

    public int NearestTile(float x, float z)
    {
        int best = -1;
        float bestDistance = float.MaxValue;
        for (int i = 0; i + 1 < (TileCentres?.Length ?? 0); i += 2)
        {
            float dx = TileCentres[i] - x;
            float dz = TileCentres[i + 1] - z;
            float d = dx * dx + dz * dz;
            if (d < bestDistance)
            {
                bestDistance = d;
                best = i / 2;
            }
        }

        return best;
    }

    // How far (x, z) lies on the side of tile `to` of the edge it shares with tile `from` (negative on the other side): the distance to the perpendicular bisector of their centres.
    public float DepthIntoTile(float x, float z, int from, int to)
    {
        float fx = TileCentres[2 * from], fz = TileCentres[2 * from + 1], tx = TileCentres[2 * to], tz = TileCentres[2 * to + 1];
        float toFrom = (x - fx) * (x - fx) + (z - fz) * (z - fz);
        float toTo = (x - tx) * (x - tx) + (z - tz) * (z - tz);
        float apart = Mathf.Sqrt((tx - fx) * (tx - fx) + (tz - fz) * (tz - fz));
        return (toFrom - toTo) / (2f * Mathf.Max(apart, 0.0001f));
    }

    private string[] _checkNames;
    private float[] _checkValues;

    // The world file supplying the terrain, relative to StreamingAssets (read through StreamingData). An Interlude uses the
    // terrain of the session it probes.
    public static string PathFor(SessionConfig config)
    {
        if (config.IsRanking)
        {
            return StagePath(config.InterludeStageSeed);
        }

        string owner = config.IsInterlude ? config.InterludeFor : config.name;
        return $"Experiments/{config.ExperimentCode}/{owner}_seed{config.WorldSeed}.world";
    }

    // The flat stage every ranking Interlude is played on (scripts/ranking.py stage): one world file at the root of StreamingAssets, so a browser
    // build fetches it with the common files.
    public static string StagePath(int seed)
    {
        return $"stage_seed{seed}.world";
    }

    // An Interlude's bush table and trial list (written by scripts/interlude.py), relative to StreamingAssets.
    public static string InterludePathFor(SessionConfig config)
    {
        return $"Experiments/{config.ExperimentCode}/{config.name}_seed{config.WorldSeed}.interlude.json";
    }

    // A session's ranking-break pool (written by scripts/ranking.py pool), relative to StreamingAssets.
    public static string RankingPoolPathFor(SessionConfig config)
    {
        return $"Experiments/{config.ExperimentCode}/{config.name}_seed{config.WorldSeed}.ranking.json";
    }

    [Serializable]
    private class InterludeBushes
    {
        public int fruitCount;
        public float[] treePos;
        public float[] shape;
        public float[] color;
        public float[] moisture;
        public float[] canopyRadius;
        public float[] value;
        public int[] fruitRewards;
    }

    // Replaces this world's bushes with an Interlude's (the terrain stays the session's own).
    private bool ApplyInterludeBushes(SessionConfig config)
    {
        string path = InterludePathFor(config);
        if (!StreamingData.Exists(path))
        {
            Debug.LogError($"Interlude file not found: {path}. Generate it with: ./venv/bin/python scripts/interlude.py {config.name}");
            return false;
        }

        InterludeBushes b = JsonUtility.FromJson<InterludeBushes>(StreamingData.ReadText(path));
        if (b == null || b.treePos == null || b.treePos.Length == 0)
        {
            Debug.LogError($"Interlude file has no bush table: {path}");
            return false;
        }

        TreeCount = b.treePos.Length / 2;
        FruitCount = b.fruitCount;
        TreePos = b.treePos;
        Shape = b.shape;
        Color = b.color;
        Moisture = b.moisture;
        CanopyRadius = b.canopyRadius;
        Value = b.value;
        FruitRewards = b.fruitRewards;
        return true;
    }

    // Returns null (after logging why) when the file is missing or unreadable.
    public static WorldData Load(SessionConfig config)
    {
        string path = PathFor(config);
        if (!StreamingData.Exists(path))
        {
            Debug.LogError($"World file not found: {path}. Generate it with: ./venv/bin/python scripts/world.py {config.name} --unity");
            return null;
        }

        try
        {
            byte[] bytes = StreamingData.ReadBytes(path);
            if (bytes.Length < 12 || Encoding.ASCII.GetString(bytes, 0, 4) != "FWLD")
            {
                Debug.LogError($"Not a world file: {path}");
                return null;
            }

            int version = BitConverter.ToInt32(bytes, 4);
            if (version != 1 && version != FormatVersion)
            {
                Debug.LogError($"World file {path} has format version {version}; expected 1 or {FormatVersion}.");
                return null;
            }

            int headerLength = BitConverter.ToInt32(bytes, 8);
            Header h = JsonUtility.FromJson<Header>(Encoding.UTF8.GetString(bytes, 12, headerLength));

            var world = new WorldData
            {
                Path = path,
                Session = h.session,
                Seed = h.seed,
                Res = h.res,
                HalfExtent = h.halfExtent,
                TreeCount = h.treeCount,
                FruitCount = h.fruitCount,
                TreePos = h.treePos,
                Shape = h.shape,
                Color = h.color,
                Moisture = h.moisture,
                CanopyRadius = h.canopyRadius,
                Value = h.value,
                FruitRewards = h.fruitRewards,
                _checkNames = h.checkNames,
                _checkValues = h.checkValues,
                TileCentres = h.tileCentres,
                TileRadius = h.tileRadius,
                TileRamp = h.tileRamp
            };

            int cells = h.res * h.res;
            int offset = 12 + headerLength;
            byte[] block = bytes;
            if (version == FormatVersion)
            {
                block = Inflate(bytes, offset);
                offset = 0;
            }

            for (int g = 0; g < h.grids.Length; g++)
            {
                var grid = new float[cells];
                if (version == 1)
                {
                    Buffer.BlockCopy(block, offset, grid, 0, cells * sizeof(float));
                    offset += cells * sizeof(float);
                }
                else
                {
                    int bits = h.gridBits[g];
                    float lo = h.gridMin[g];
                    float step = (h.gridMax[g] - lo) / ((1 << bits) - 1);
                    for (int c = 0; c < cells; c++)
                    {
                        int code = bits == 16 ? BitConverter.ToUInt16(block, offset + 2 * c) : block[offset + c];
                        grid[c] = lo + code * step;
                    }

                    offset += cells * (bits / 8);
                }

                switch (h.grids[g])
                {
                    case "moisture": world.MoistureGrid = grid; break;
                    case "elevation": world.ElevationGrid = grid; break;
                    case "rock": world.RockGrid = grid; break;
                    case "snow": world.SnowGrid = grid; break;
                    case "ramp": world.RampGrid = grid; break;
                }
            }

            if (world.MoistureGrid == null || world.ElevationGrid == null || world.RockGrid == null
                || world.SnowGrid == null || world.RampGrid == null)
            {
                Debug.LogError($"World file {path} is missing a terrain grid.");
                return null;
            }

            if (config.IsInterlude && !world.ApplyInterludeBushes(config))
            {
                return null;
            }

            return world;
        }
        catch (Exception e)
        {
            Debug.LogError($"Failed to read world file {path}: {e}");
            return null;
        }
    }

    // The gzip stream that starts at `offset` of the file, decompressed.
    private static byte[] Inflate(byte[] bytes, int offset)
    {
        using (var input = new MemoryStream(bytes, offset, bytes.Length - offset))
        using (var gzip = new GZipStream(input, CompressionMode.Decompress))
        using (var output = new MemoryStream())
        {
            gzip.CopyTo(output);
            return output.ToArray();
        }
    }

    // Bilinear sample of a mesh-grid field at a world position (clamped to the grid).
    public float Sample(float[] grid, float worldX, float worldZ)
    {
        float scale = (Res - 1) / (2f * HalfExtent);
        float fx = Mathf.Clamp((worldX + HalfExtent) * scale, 0f, Res - 1f);
        float fz = Mathf.Clamp((worldZ + HalfExtent) * scale, 0f, Res - 1f);
        int i = Mathf.Min((int)fx, Res - 2);
        int j = Mathf.Min((int)fz, Res - 2);
        float tx = fx - i;
        float tz = fz - j;
        float a = Mathf.Lerp(grid[i * Res + j], grid[i * Res + j + 1], tz);
        float b = Mathf.Lerp(grid[(i + 1) * Res + j], grid[(i + 1) * Res + j + 1], tz);
        return Mathf.Lerp(a, b, tx);
    }

    // Names of the generation parameters whose value in the SessionConfig differs from the one the file was
    // generated with (the file is then stale: re-run scripts/world.py). Empty when consistent.
    public List<string> FindMismatches(SessionConfig config)
    {
        var current = new Dictionary<string, float>
        {
            { "worldHalfExtent", config.WorldHalfExtent },
            { "terrainMeshResolution", config.TerrainMeshResolution },
            { "terrainNoiseFrequency", config.TerrainNoiseFrequency },
            { "terrainNoiseOctaves", config.TerrainNoiseOctaves },
            { "terrainMaxElevation", config.TerrainMaxElevation },
            { "moistureTerraceLevels", config.MoistureTerraceLevels },
            { "moistureTerraceSharpness", config.MoistureTerraceSharpness },
            { "moistureTerraceResidual", config.MoistureTerraceResidual },
            { "mountainBandWidth", config.MountainBandWidth },
            { "mountainBoundaryJitter", config.MountainBoundaryJitter },
            { "mountainHeight", config.MountainHeight },
            { "mountainNoiseScale", config.MountainNoiseScale },
            { "snowLineFraction", config.SnowLineFraction },
            { "treeSpacing", config.TreeSpacing },
            { "placementJitter", config.PlacementJitter },
            { "startClearingRadius", config.StartClearingRadius },
            { "treeEdgeMargin", config.TreeEdgeMargin },
            { "fruitCount", config.FruitCount },
            { "rewardStd", config.RewardStd },
            { "canopyWidthRange.min", config.CanopyWidthRange.x },
            { "canopyWidthRange.max", config.CanopyWidthRange.y },
            { "shapeRange.min", config.ShapeRange.x },
            { "shapeRange.max", config.ShapeRange.y },
            { "spatialBalance", (float)(int)config.SpatialBalance },
            { "shapeVaries", config.ShapeVaries ? 1f : 0f },
            { "colorVaries", config.ColorVaries ? 1f : 0f },
            { "shapeWhenFixed", config.ShapeWhenFixed },
            { "colorWhenFixed", config.ColorWhenFixed },
            { "moistureVaries", config.MoistureVaries ? 1f : 0f },
            { "moistureWhenFixed", config.MoistureWhenFixed },
            { "moistureTerraceUnevenness", config.MoistureTerraceUnevenness },
            { "moistureTerraceMode", (float)(int)config.MoistureTerraceMode },
            { "featureBalance", (float)(int)config.FeatureBalance },
            { "featureCoverage", (float)(int)config.FeatureCoverage },
            { "featureBalanceTarget", config.FeatureBalanceTarget },
            { "featureBalanceScales.count", config.FeatureBalanceScales != null ? config.FeatureBalanceScales.Length : 0 },
            { "featureBalanceScales.sum", SumOf(config.FeatureBalanceScales) },
            { "tileRadius", config.TileRadius },        // (scripts/world.py writes the tile names only for a tiles layout, so a file of another layout does not mention them)
            { "tileRampWidth", config.TileRampWidth },
            { "tileMoistureLevels", config.TileMoistureLevels },
            { "tileBushes", config.TileBushes },
            { "tileClusterRadius", config.TileClusterRadius },
            { "tileClusterSpacing", config.TileClusterSpacing },
            { "tileSpread", config.TileSpread },
            { "tileGoodFraction", config.TileGoodFraction },
            { "tileSmoothness", config.TileSmoothness },
            { "tileGradient", config.TileGradient },
            { "tileGradientAngle", config.TileGradientAngle },
            { "tileCoverageMin", config.TileCoverageMin },
            { "tileStartSpreadMin", config.TileStartSpreadMin },
            { "terraceMeanWidth", config.TerraceMeanWidth },
            { "terraceWidthSpread", config.TerraceWidthSpread },
            { "terraceMaxBand", config.TerraceMaxBand },
            { "terraceMinStep", config.TerraceMinStep },
            { "terracePhaseShift", config.TerracePhaseShift },
            { "terracePhaseFrequency", config.TerracePhaseFrequency },
            { "terraceStrength", config.TerraceStrength },
            { "terraceDiffusionIterations", config.TerraceDiffusionIterations },
            { "terraceDiffusionEdge", config.TerraceDiffusionEdge },
            { "randomBushValueRange.min", config.RandomBushValueRange.x },
            { "randomBushValueRange.max", config.RandomBushValueRange.y }
        };
        AddReward(current, "shape", config.RewardFunction.ShapeComponent);
        AddReward(current, "color", config.RewardFunction.ColorComponent);
        AddReward(current, "moisture", config.RewardFunction.MoistureComponent);
        RewardBump[] bumps = config.RewardFunction.Bumps;
        for (int i = 0; i < bumps.Length; i++)
        {
            current[$"reward.bump{i}.centerShape"] = bumps[i].CenterShape;
            current[$"reward.bump{i}.centerColor"] = bumps[i].CenterColor;
            current[$"reward.bump{i}.width"] = bumps[i].Width;
            current[$"reward.bump{i}.height"] = bumps[i].Height;
            current[$"reward.bump{i}.widthColor"] = bumps[i].WidthColor;
            current[$"reward.bump{i}.angle"] = bumps[i].Angle;
        }

        RewardProduct[] products = config.RewardFunction.Products;
        for (int i = 0; i < products.Length; i++)
        {
            current[$"reward.product{i}.linearInShape"] = products[i].LinearInShape ? 1f : 0f;
            current[$"reward.product{i}.linearInverted"] = products[i].LinearInverted ? 1f : 0f;
            current[$"reward.product{i}.center"] = products[i].Center;
            current[$"reward.product{i}.width"] = products[i].Width;
            current[$"reward.product{i}.height"] = products[i].Height;
        }

        RewardFactors[] factors = config.RewardFunction.Factors;
        for (int i = 0; i < factors.Length; i++)
        {
            current[$"reward.factor{i}.combine"] = (float)(int)factors[i].Combine;
            current[$"reward.factor{i}.height"] = factors[i].Height;
            AddFactor(current, $"reward.factor{i}.shape", factors[i].ShapeFactor);
            AddFactor(current, $"reward.factor{i}.color", factors[i].ColorFactor);
        }

        var mismatches = new List<string>();
        for (int i = 0; i < _checkNames.Length; i++)
        {
            if (!current.TryGetValue(_checkNames[i], out float value) || !Mathf.Approximately(value, _checkValues[i]))
            {
                mismatches.Add(_checkNames[i]);
            }
        }

        // Reward terms newer than the first world files: a product or factor term, and a bump's color spread or angle when it is not 0, are written only when present, so a file
        // without them was made without them and a config that has them now is stale.
        foreach (KeyValuePair<string, float> entry in current)
        {
            bool newer = entry.Key.StartsWith("reward.product") || entry.Key.StartsWith("reward.factor")
                || ((entry.Key.EndsWith(".widthColor") || entry.Key.EndsWith(".angle")) && !Mathf.Approximately(entry.Value, 0f));
            if (newer && Array.IndexOf(_checkNames, entry.Key) < 0)
            {
                mismatches.Add(entry.Key);
            }
        }

        // Names the generator writes only when they differ from the default (1 for the "varies" flags, 0.5 for the "when fixed" values, 0 for the random value range):
        // a file without one was made with the default, so a config that now differs is stale.
        foreach (string name in new[] { "shapeVaries", "colorVaries", "moistureVaries", "shapeWhenFixed", "colorWhenFixed", "moistureWhenFixed", "moistureTerraceUnevenness", "moistureTerraceMode", "featureBalance", "featureCoverage", "randomBushValueRange.min", "randomBushValueRange.max", "spatialBalance" })
        {
            float fallback = name.StartsWith("randomBushValueRange") || name == "spatialBalance" || name == "moistureTerraceUnevenness" || name == "moistureTerraceMode" || name == "featureBalance" || name == "featureCoverage" ? 0f : name.EndsWith("WhenFixed") ? 0.5f : 1f;
            if (Array.IndexOf(_checkNames, name) < 0 && current.TryGetValue(name, out float now) && !Mathf.Approximately(now, fallback))
            {
                mismatches.Add(name);
            }
        }

        return mismatches;
    }

    private static void AddFactor(Dictionary<string, float> current, string prefix, RewardFactor factor)
    {
        current[$"{prefix}.kind"] = (float)(int)factor.Kind;
        current[$"{prefix}.center"] = factor.Center;
        current[$"{prefix}.scale"] = factor.Scale;
        current[$"{prefix}.inverted"] = factor.Inverted ? 1f : 0f;
    }

    private static float SumOf(float[] values)
    {
        float sum = 0f;
        if (values != null)
        {
            foreach (float value in values)
            {
                sum += value;
            }
        }

        return sum;
    }

    private static void AddReward(Dictionary<string, float> values, string part, RewardComponent component)
    {
        values[$"reward.{part}.basisFunctionType"] = (int)Enum.Parse(typeof(BasisFunctionType), component.TypeName);
        values[$"reward.{part}.weight"] = component.Weight;
        values[$"reward.{part}.peak"] = component.Peak;
        values[$"reward.{part}.width"] = component.Width;
    }
}
