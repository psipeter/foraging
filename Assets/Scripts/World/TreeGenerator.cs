using System.Collections.Generic;
using UnityEngine;

[DefaultExecutionOrder(10)]
public class TreeGenerator : MonoBehaviour
{
    [SerializeField] private SessionConfig sessionConfig;
    [SerializeField] private TerrainManager terrainManager;
    [SerializeField] private GameObject treePrefab;

    private const float MinTreeDistance = 5f;
    private const int MaxPlacementAttempts = 800;

    private void Start()
    {
        if (sessionConfig == null || treePrefab == null || terrainManager == null)
        {
            return;
        }

        Random.InitState(sessionConfig.WorldSeed);

        int targetCount = sessionConfig.TreeCount;
        var positions = new List<Vector3>(targetCount);

        int placed = 0;
        while (placed < targetCount)
        {
            Vector3? candidate = TryFindPosition(positions);
            if (!candidate.HasValue)
            {
                break;
            }

            Vector3 candidatePos = candidate.Value;
            float elevation = terrainManager.SampleElevation(candidatePos.x, candidatePos.z);
            Vector3 pos = new Vector3(candidatePos.x, elevation, candidatePos.z);
            GameObject instance = Instantiate(treePrefab, pos, Quaternion.identity);
            var tree = instance.GetComponent<Tree>();
            if (tree == null)
            {
                Destroy(instance);
                continue;
            }

            int treeIndex = placed;
            tree.sessionConfig = sessionConfig;
            tree.fruitCount = sessionConfig.FruitCount;
            tree.fruitRadius = sessionConfig.FruitRadius;
            tree.fruitSeed = sessionConfig.WorldSeed + treeIndex * 7;

            TreeAttributes attributes = new TreeAttributes
            {
                shape = Random.Range(0f, 1f),
                color = Random.Range(0f, 1f),
                moisture = terrainManager.SampleMoisture(pos.x, pos.z)
            };
            tree.attributes = attributes;
            tree.ApplyAttributes();
            positions.Add(pos);
            placed++;
        }
    }

    private Vector3? TryFindPosition(List<Vector3> existing)
    {
        float halfExtent = sessionConfig != null ? sessionConfig.WorldHalfExtent : 50f;

        for (int attempt = 0; attempt < MaxPlacementAttempts; attempt++)
        {
            float x = Random.Range(-halfExtent, halfExtent);
            float z = Random.Range(-halfExtent, halfExtent);
            var candidate = new Vector3(x, 0f, z);

            if (IsFarEnough(candidate, existing))
            {
                return candidate;
            }
        }

        return null;
    }

    private static bool IsFarEnough(Vector3 candidate, List<Vector3> existing)
    {
        for (int i = 0; i < existing.Count; i++)
        {
            Vector3 p = existing[i];
            float dx = candidate.x - p.x;
            float dz = candidate.z - p.z;
            if (dx * dx + dz * dz < MinTreeDistance * MinTreeDistance)
            {
                return false;
            }
        }

        return true;
    }
}
