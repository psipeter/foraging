using System;
using System.Collections;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Text;
using UnityEngine;

[DefaultExecutionOrder(20)]
public class DataLogger : MonoBehaviour
{
    [SerializeField] private SessionConfig sessionConfig;
    [SerializeField] private SunController sunController;
    [SerializeField] private PlayerController playerController;
    [SerializeField] private Camera mainCamera;
    [SerializeField] private TerrainManager terrainManager;
    [SerializeField] private float movementSampleInterval = 0.1f;
    [SerializeField] private float maxVisibilityDistance = 80f;
    [SerializeField] private LayerMask terrainOcclusionMask;

    private string _sessionId;
    private string _sessionDataPath;
    private StreamWriter _movementWriter;
    private StreamWriter _harvestWriter;
    private readonly List<Tree> _allTrees = new List<Tree>();

    private int _harvestIndex;
    private readonly List<float> _currentFruitRewards = new List<float>();
    private float _harvestStartTime = -1f;
    private float _runningTotal = 0f;

    private void OnEnable()
    {
        HarvestManager.OnFruitCollected += HandleFruitCollected;
        HarvestManager.OnHarvestSummary += HandleHarvestSummary;
        HarvestManager.OnHarvestComplete += HandleHarvestComplete;
        SunController.OnSessionEnd += HandleSessionEnd;
    }

    private void OnDisable()
    {
        HarvestManager.OnFruitCollected -= HandleFruitCollected;
        HarvestManager.OnHarvestSummary -= HandleHarvestSummary;
        HarvestManager.OnHarvestComplete -= HandleHarvestComplete;
        SunController.OnSessionEnd -= HandleSessionEnd;
        CloseWriters();
    }

    private void Start()
    {
        _sessionId = Guid.NewGuid().ToString("N").Substring(0, 8);
        string root = Path.Combine(Application.persistentDataPath, "ForagingData");
        _sessionDataPath = Path.Combine(root, _sessionId);

        try
        {
            Directory.CreateDirectory(_sessionDataPath);

            _movementWriter = new StreamWriter(Path.Combine(_sessionDataPath, "movement.csv"), false, Encoding.UTF8);
            _harvestWriter = new StreamWriter(Path.Combine(_sessionDataPath, "harvests.csv"), false, Encoding.UTF8);

            WriteMovementHeader();
            WriteHarvestHeader();
            WriteSessionMetadata();
        }
        catch (Exception e)
        {
            Debug.LogError($"DataLogger failed to initialize IO: {e}");
        }

        _allTrees.Clear();
        _allTrees.AddRange(FindObjectsByType<Tree>(FindObjectsSortMode.None));

        StartCoroutine(MovementSamplingLoop());
    }

    private void WriteMovementHeader()
    {
        _movementWriter?.WriteLine("time,player_x,player_y,player_z,player_heading,camera_x,camera_y,camera_z,camera_rot_x,camera_rot_y,camera_rot_z,visible_bush_ids,visible_bush_distances");
        _movementWriter?.Flush();
    }

    private void WriteHarvestHeader()
    {
        _harvestWriter?.WriteLine("harvest_index,time_start,time_end,bush_id,bush_x,bush_y,bush_z,shape,color,moisture,true_reward,total_received,running_total,time_remaining,fruit_rewards");
        _harvestWriter?.Flush();
    }

    private IEnumerator MovementSamplingLoop()
    {
        WaitForSeconds wait = new WaitForSeconds(movementSampleInterval);
        while (sunController == null || !sunController.SessionComplete)
        {
            SampleMovement();
            yield return wait;
        }
    }

    private void SampleMovement()
    {
        if (_movementWriter == null || playerController == null || mainCamera == null)
        {
            return;
        }

        float time = sunController != null ? sunController.SessionTimeRemaining : Time.time;
        Transform playerTransform = playerController.transform;
        Vector3 pPos = playerTransform.position;
        float heading = playerTransform.eulerAngles.y;

        Transform camT = mainCamera.transform;
        Vector3 cPos = camT.position;
        Vector3 cRot = camT.eulerAngles;

        // Visible bushes
        List<int> visibleIds = new List<int>();
        List<float> visibleDistances = new List<float>();

        Plane[] planes = GeometryUtility.CalculateFrustumPlanes(mainCamera);

        foreach (Tree tree in _allTrees)
        {
            if (tree == null) continue;

            Vector3 center = tree.GetWorldCenter();
            float dist = Vector3.Distance(cPos, center);
            if (dist > maxVisibilityDistance) continue;

            Bounds bounds = new Bounds(center, Vector3.one * 2f);
            if (!GeometryUtility.TestPlanesAABB(planes, bounds)) continue;

            Vector3 dir = (center - cPos);
            float rayDist = dir.magnitude;
            if (rayDist <= 0.001f) continue;
            dir /= rayDist;

            if (Physics.Raycast(cPos, dir, out RaycastHit hit, rayDist, terrainOcclusionMask, QueryTriggerInteraction.Ignore))
            {
                // Occluded by terrain
                continue;
            }

            visibleIds.Add(tree.treeId);
            visibleDistances.Add(dist);
        }

        string ids = string.Join(";", visibleIds);
        string dists = string.Join(";", visibleDistances.ConvertAll(d => d.ToString("F2", CultureInfo.InvariantCulture)));

        string line = string.Format(CultureInfo.InvariantCulture,
            "{0:F3},{1:F3},{2:F3},{3:F3},{4:F1},{5:F3},{6:F3},{7:F3},{8:F1},{9:F1},{10:F1},{11},{12}",
            time,
            pPos.x, pPos.y, pPos.z, heading,
            cPos.x, cPos.y, cPos.z,
            cRot.x, cRot.y, cRot.z,
            ids, dists);

        _movementWriter.WriteLine(line);
        _movementWriter.Flush();
    }

    private void HandleFruitCollected(float reward, Vector3 worldPos)
    {
        if (_harvestStartTime < 0f)
        {
            _harvestStartTime = sunController != null ? sunController.SessionTimeRemaining : Time.time;
        }
        _currentFruitRewards.Add(reward);
    }

    private void HandleHarvestSummary(float totalReward, Vector3 worldPos)
    {
        if (_harvestWriter == null || sessionConfig == null)
        {
            _currentFruitRewards.Clear();
            _harvestStartTime = -1f;
            return;
        }

        Tree tree = FindClosestTree(worldPos);
        if (tree == null)
        {
            _currentFruitRewards.Clear();
            _harvestStartTime = -1f;
            return;
        }

        float timeEnd = sunController != null ? sunController.SessionTimeRemaining : Time.time;
        float timeStart = _harvestStartTime >= 0f ? _harvestStartTime : timeEnd;

        float trueReward = sessionConfig.EvaluateReward(tree.attributes);
        float timeRemaining = sunController != null ? sunController.SessionTimeRemaining : 0f;

        string fruitRewards = string.Join(";", _currentFruitRewards.ConvertAll(v => v.ToString("F3", CultureInfo.InvariantCulture)));

        string line = string.Format(CultureInfo.InvariantCulture,
            "{0},{1:F3},{2:F3},{3},{4:F3},{5:F3},{6:F3},{7:F3},{8:F3},{9:F3},{10:F3},{11:F3},{12:F3},{13:F3},\"{14}\"",
            _harvestIndex,
            timeStart,
            timeEnd,
            tree.treeId,
            worldPos.x, worldPos.y, worldPos.z,
            tree.attributes.shape,
            tree.attributes.color,
            tree.attributes.moisture,
            trueReward,
            totalReward,
            _runningTotal + totalReward,
            timeRemaining,
            fruitRewards);

        _harvestWriter.WriteLine(line);
        _harvestWriter.Flush();

        _harvestIndex++;
        _currentFruitRewards.Clear();
        _harvestStartTime = -1f;
    }

    private Tree FindClosestTree(Vector3 worldPos)
    {
        Tree closest = null;
        float bestDist = float.MaxValue;
        foreach (Tree tree in _allTrees)
        {
            if (tree == null) continue;
            float d = Vector3.SqrMagnitude(tree.GetWorldCenter() - worldPos);
            if (d < bestDist)
            {
                bestDist = d;
                closest = tree;
            }
        }
        return closest;
    }

    private void HandleSessionEnd()
    {
        CloseWriters();
    }

    private void HandleHarvestComplete(float runningTotal)
    {
        _runningTotal = runningTotal;
    }

    private void OnDestroy()
    {
        CloseWriters();
    }

    private void CloseWriters()
    {
        try
        {
            _movementWriter?.Flush();
            _movementWriter?.Close();
            _movementWriter = null;
        }
        catch { }

        try
        {
            _harvestWriter?.Flush();
            _harvestWriter?.Close();
            _harvestWriter = null;
        }
        catch { }
    }

    private void WriteSessionMetadata()
    {
        if (sessionConfig == null || mainCamera == null)
        {
            return;
        }

        string path = Path.Combine(_sessionDataPath, "session_metadata.json");

        StringBuilder sb = new StringBuilder();
        sb.AppendLine("{");
        sb.AppendLine($"  \"sessionId\": \"{_sessionId}\",");
        sb.AppendLine($"  \"timestamp\": \"{DateTime.UtcNow:O}\",");
        sb.AppendLine($"  \"sessionDuration\": {sessionConfig.SessionDuration.ToString(CultureInfo.InvariantCulture)},");
        sb.AppendLine($"  \"worldSeed\": {sessionConfig.WorldSeed},");
        sb.AppendLine($"  \"treeCount\": {sessionConfig.TreeCount},");
        sb.AppendLine($"  \"fruitCount\": {sessionConfig.FruitCount},");
        sb.AppendLine($"  \"fruitHarvestDuration\": {sessionConfig.FruitHarvestDuration.ToString(CultureInfo.InvariantCulture)},");
        sb.AppendLine($"  \"rewardNoiseMagnitude\": {sessionConfig.RewardNoiseMagnitude.ToString(CultureInfo.InvariantCulture)},");
        sb.AppendLine($"  \"playerMoveSpeed\": {sessionConfig.PlayerMoveSpeed.ToString(CultureInfo.InvariantCulture)},");
        sb.AppendLine($"  \"maxVisibilityDistance\": {maxVisibilityDistance.ToString(CultureInfo.InvariantCulture)},");
        sb.AppendLine($"  \"movementSampleInterval\": {movementSampleInterval.ToString(CultureInfo.InvariantCulture)},");
        sb.AppendLine("  \"camera\": {");
        sb.AppendLine($"    \"fieldOfView\": {mainCamera.fieldOfView.ToString(CultureInfo.InvariantCulture)},");
        sb.AppendLine($"    \"localPosition\": {{ \"x\": {mainCamera.transform.localPosition.x.ToString(CultureInfo.InvariantCulture)}, \"y\": {mainCamera.transform.localPosition.y.ToString(CultureInfo.InvariantCulture)}, \"z\": {mainCamera.transform.localPosition.z.ToString(CultureInfo.InvariantCulture)} }},");
        Vector3 euler = mainCamera.transform.localEulerAngles;
        sb.AppendLine($"    \"localRotation\": {{ \"x\": {euler.x.ToString(CultureInfo.InvariantCulture)}, \"y\": {euler.y.ToString(CultureInfo.InvariantCulture)}, \"z\": {euler.z.ToString(CultureInfo.InvariantCulture)} }},");
        sb.AppendLine($"    \"nearClipPlane\": {mainCamera.nearClipPlane.ToString(CultureInfo.InvariantCulture)},");
        sb.AppendLine($"    \"farClipPlane\": {mainCamera.farClipPlane.ToString(CultureInfo.InvariantCulture)}");
        sb.AppendLine("  },");

        // Reward function
        sb.AppendLine("  \"rewardFunction\": {");
        AppendRewardComponentJson(sb, "shape", sessionConfig.RewardFunction.ShapeComponent);
        sb.AppendLine(",");
        AppendRewardComponentJson(sb, "color", sessionConfig.RewardFunction.ColorComponent);
        sb.AppendLine(",");
        AppendRewardComponentJson(sb, "moisture", sessionConfig.RewardFunction.MoistureComponent);
        sb.AppendLine();
        sb.AppendLine("  },");

        // Bush registry
        _allTrees.Clear();
        _allTrees.AddRange(FindObjectsByType<Tree>(FindObjectsSortMode.None));
        sb.AppendLine("  \"bushRegistry\": [");
        for (int i = 0; i < _allTrees.Count; i++)
        {
            Tree tree = _allTrees[i];
            if (tree == null) continue;
            Vector3 pos = tree.GetWorldCenter();
            float trueReward = sessionConfig.EvaluateReward(tree.attributes);
            sb.Append("    { ");
            sb.AppendFormat(CultureInfo.InvariantCulture, "\"id\": {0}, ", tree.treeId);
            sb.AppendFormat(CultureInfo.InvariantCulture, "\"x\": {0}, \"y\": {1}, \"z\": {2}, ", pos.x, pos.y, pos.z);
            sb.AppendFormat(CultureInfo.InvariantCulture, "\"shape\": {0}, \"color\": {1}, \"moisture\": {2}, ", tree.attributes.shape, tree.attributes.color, tree.attributes.moisture);
            sb.AppendFormat(CultureInfo.InvariantCulture, "\"trueReward\": {0}", trueReward);
            sb.Append(" }");
            if (i < _allTrees.Count - 1)
            {
                sb.Append(",");
            }
            sb.AppendLine();
        }
        sb.AppendLine("  ]");
        sb.AppendLine("}");

        File.WriteAllText(path, sb.ToString());
    }

    private static void AppendRewardComponentJson(StringBuilder sb, string name, RewardComponent component)
    {
        sb.Append("    ");
        sb.AppendFormat("\"{0}\": {{ \"type\": \"{1}\", \"weight\": {2}, \"peak\": {3}, \"width\": {4} }}",
            name,
            component.TypeName,
            component.Weight.ToString(CultureInfo.InvariantCulture),
            component.Peak.ToString(CultureInfo.InvariantCulture),
            component.Width.ToString(CultureInfo.InvariantCulture));
    }
}

