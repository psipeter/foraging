using UnityEngine;

[DefaultExecutionOrder(10)]
public class TreeGenerator : MonoBehaviour
{
    public SessionConfig sessionConfig;
    public WorldData world;
    [SerializeField] private TerrainManager terrainManager;
    [SerializeField] private GameObject treePrefab;
    [Tooltip("Material for the rim-light highlight overlay (Foraging/CanopyRim). Referenced here so its shader is included in builds.")]
    [SerializeField] private Material rimMaterial;
    [Tooltip("Material for the harvest progress ring (Foraging/HarvestRing).")]
    [SerializeField] private Material ringMaterial;

    private void Start()
    {
        if (sessionConfig == null || world == null || treePrefab == null || terrainManager == null)
        {
            return;
        }

        // Bush positions, attributes and per-fruit rewards all come from the world file (scripts/world.py).
        int placed = 0;
        for (int s = 0; s < world.TreeCount; s++)
        {
            float px = world.TreePos[2 * s];
            float pz = world.TreePos[2 * s + 1];
            float elevation = terrainManager.SampleElevation(px, pz);
            Vector3 pos = new Vector3(px, elevation, pz);
            GameObject instance = Instantiate(treePrefab, pos, Quaternion.identity, transform);
            var treeComp = instance.GetComponent<Tree>();
            if (treeComp == null)
            {
                Destroy(instance);
                continue;
            }

            int treeIndex = placed;
            treeComp.treeId = treeIndex;
            treeComp.sessionConfig = sessionConfig;
            treeComp.rimMaterial = rimMaterial;
            treeComp.ringMaterial = ringMaterial;
            treeComp.fruitCount = world.FruitCount;
            treeComp.fruitRewards = new int[world.FruitCount];
            System.Array.Copy(world.FruitRewards, s * world.FruitCount, treeComp.fruitRewards, 0, world.FruitCount);
            treeComp.fruitRadius = sessionConfig.FruitRadius;
            treeComp.fruitSeed = sessionConfig.WorldSeed + treeIndex * 7;

            TreeAttributes attributes = new TreeAttributes
            {
                shape = world.Shape[s],
                color = world.Color[s],
                moisture = world.Moisture[s]
            };
            treeComp.attributes = attributes;

            treeComp.SetTerrainManager(terrainManager);
            treeComp.ApplyAttributes();

            int treeLayer = LayerMask.NameToLayer("Tree");
            if (treeLayer >= 0)
            {
                SetLayerRecursively(instance, treeLayer);
            }

            placed++;
        }
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
