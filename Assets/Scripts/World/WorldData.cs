using System;
using System.Collections.Generic;
using System.IO;
using System.Text;
using UnityEngine;

// A generated world, loaded from StreamingAssets/Worlds/<session>_seed<seed>.world. The files are written by
// scripts/world.py (the source of truth for placement, attributes, terrain fields and per-fruit rewards);
// Unity only renders and plays them. Format: "FWLD", uint32 version, uint32 header length, JSON header, then
// float32 little-endian grids (res * res each, index i * res + j, i across X, j across Z).
public class WorldData
{
    public const int FormatVersion = 1;

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
        public float[] treePos;
        public float[] shape;
        public float[] color;
        public float[] moisture;
        public float[] canopyRadius;
        public float[] value;
        public int[] fruitRewards;
        public string[] checkNames;
        public float[] checkValues;
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

    private string[] _checkNames;
    private float[] _checkValues;

    public static string PathFor(SessionConfig config)
    {
        return System.IO.Path.Combine(Application.streamingAssetsPath, "Worlds", $"{config.name}_seed{config.WorldSeed}.world");
    }

    // Returns null (after logging why) when the file is missing or unreadable.
    public static WorldData Load(SessionConfig config)
    {
        string path = PathFor(config);
        if (!File.Exists(path))
        {
            Debug.LogError($"World file not found: {path}. Generate it with: ./venv/bin/python scripts/world.py {config.name} --unity");
            return null;
        }

        try
        {
            byte[] bytes = File.ReadAllBytes(path);
            if (bytes.Length < 12 || Encoding.ASCII.GetString(bytes, 0, 4) != "FWLD")
            {
                Debug.LogError($"Not a world file: {path}");
                return null;
            }

            int version = BitConverter.ToInt32(bytes, 4);
            if (version != FormatVersion)
            {
                Debug.LogError($"World file {path} has format version {version}; expected {FormatVersion}.");
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
                _checkValues = h.checkValues
            };

            int gridBytes = h.res * h.res * sizeof(float);
            int offset = 12 + headerLength;
            for (int g = 0; g < h.grids.Length; g++)
            {
                var grid = new float[h.res * h.res];
                Buffer.BlockCopy(bytes, offset, grid, 0, gridBytes);
                offset += gridBytes;
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

            return world;
        }
        catch (Exception e)
        {
            Debug.LogError($"Failed to read world file {path}: {e}");
            return null;
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
            { "rewardStd", config.RewardStd }
        };
        AddReward(current, "shape", config.RewardFunction.ShapeComponent);
        AddReward(current, "color", config.RewardFunction.ColorComponent);
        AddReward(current, "moisture", config.RewardFunction.MoistureComponent);

        var mismatches = new List<string>();
        for (int i = 0; i < _checkNames.Length; i++)
        {
            if (!current.TryGetValue(_checkNames[i], out float value) || !Mathf.Approximately(value, _checkValues[i]))
            {
                mismatches.Add(_checkNames[i]);
            }
        }

        return mismatches;
    }

    private static void AddReward(Dictionary<string, float> values, string part, RewardComponent component)
    {
        values[$"reward.{part}.basisFunctionType"] = (int)Enum.Parse(typeof(BasisFunctionType), component.TypeName);
        values[$"reward.{part}.weight"] = component.Weight;
        values[$"reward.{part}.peak"] = component.Peak;
        values[$"reward.{part}.width"] = component.Width;
    }
}
