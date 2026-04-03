using System.Collections.Generic;
using UnityEngine;

[DefaultExecutionOrder(10)]
public class TreeGenerator : MonoBehaviour
{
    public SessionConfig sessionConfig;
    [SerializeField] private TerrainManager terrainManager;
    [SerializeField] private GameObject treePrefab;

    private const float MinTreeDistance = 5f;
    private const int MaxPlacementAttempts = 800;

    private void Start()
    {
        GameManager.LogDiagnostic($"TreeGenerator.Start: sessionConfig={sessionConfig != null}, treePrefab={treePrefab != null}, terrainManager={terrainManager != null}, treeCount={sessionConfig?.TreeCount}");

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
            GameManager.LogDiagnostic($"Attempting placement {placed + 1}...");

            Vector3? candidate = TryFindPosition(positions);
            GameManager.LogDiagnostic($"TryFindPosition result: hasValue={candidate.HasValue}");
            if (!candidate.HasValue)
            {
                break;
            }

            Vector3 candidatePos = candidate.Value;
            float elevation = terrainManager.SampleElevation(candidatePos.x, candidatePos.z);
            Vector3 pos = new Vector3(candidatePos.x, elevation, candidatePos.z);
            GameObject instance = Instantiate(treePrefab, pos, Quaternion.identity);
            var treeComp = instance.GetComponent<Tree>();
            GameManager.LogDiagnostic($"instance={instance != null}, treeComp={treeComp != null}, prefabName={instance?.name}");
            if (treeComp == null)
            {
                GameManager.LogDiagnostic($"Tree component missing on prefab instance {placed}");
                Destroy(instance);
                continue;
            }

            int treeIndex = placed;
            treeComp.treeId = treeIndex;
            treeComp.sessionConfig = sessionConfig;
            treeComp.fruitCount = sessionConfig.FruitCount;
            treeComp.fruitRadius = sessionConfig.FruitRadius;
            treeComp.fruitSeed = sessionConfig.WorldSeed + treeIndex * 7;

            TreeAttributes attributes = new TreeAttributes
            {
                shape = Random.Range(0f, 1f),
                color = Random.Range(0f, 1f),
                moisture = terrainManager.SampleMoisture(pos.x, pos.z)
            };
            treeComp.attributes = attributes;

            Vector3 terrainNormal = terrainManager.SampleNormal(pos.x, pos.z);
            treeComp.SetTerrainNormal(terrainNormal);
            treeComp.SetTerrainManager(terrainManager);
            treeComp.ApplyAttributes();

            GameManager.LogDiagnostic($"Tree {placed}: FruitCount={treeComp.FruitCount}, sessionConfig={treeComp.sessionConfig != null}, terrainManager={treeComp.TerrainManager != null}");

            int treeLayer = LayerMask.NameToLayer("Tree");
            if (treeLayer >= 0)
            {
                SetLayerRecursively(instance, treeLayer);
            }

            positions.Add(pos);
            placed++;
        }

        GameManager.LogDiagnostic($"Placement loop complete: placed={placed}");
        GameManager.LogDiagnostic($"TreeGenerator finished: placed={placed} trees out of {targetCount}");
    }

    private Vector3? TryFindPosition(List<Vector3> existing)
    {
        GameManager.LogDiagnostic($"TryFindPosition called: halfExtent={sessionConfig?.WorldHalfExtent}, existing={existing.Count}");

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

        GameManager.LogDiagnostic($"TryFindPosition failed after {MaxPlacementAttempts} attempts, existing={existing.Count}");
        GameManager.LogDiagnostic($"TryFindPosition returning null after {MaxPlacementAttempts} attempts");
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

    private static void SetLayerRecursively(GameObject obj, int layer)
    {
        obj.layer = layer;
        foreach (Transform child in obj.transform)
        {
            SetLayerRecursively(child.gameObject, layer);
        }
    }
}
