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
            var rewards = new int[world.FruitCount];
            System.Array.Copy(world.FruitRewards, s * world.FruitCount, rewards, 0, world.FruitCount);
            var attributes = new TreeAttributes
            {
                shape = world.Shape[s],
                color = world.Color[s],
                moisture = world.Moisture[s]
            };
            if (CreateTree(placed, world.TreePos[2 * s], world.TreePos[2 * s + 1], attributes, rewards) != null)
            {
                placed++;
            }
        }
    }

    // One bush standing on the terrain at (x, z): the world's bushes at the start, and the ranking break's bushes later (their ids follow the world's).
    public Tree CreateTree(int treeId, float x, float z, TreeAttributes attributes, int[] fruitRewards)
    {
        float elevation = terrainManager.SampleElevation(x, z);
        GameObject instance = Instantiate(treePrefab, new Vector3(x, elevation, z), Quaternion.identity, transform);
        var treeComp = instance.GetComponent<Tree>();
        if (treeComp == null)
        {
            Destroy(instance);
            return null;
        }

        treeComp.treeId = treeId;
        treeComp.sessionConfig = sessionConfig;
        treeComp.rimMaterial = rimMaterial;
        treeComp.ringMaterial = ringMaterial;
        treeComp.fruitCount = fruitRewards.Length;
        treeComp.fruitRewards = fruitRewards;
        treeComp.fruitRadius = sessionConfig.FruitRadius;
        treeComp.fruitSeed = sessionConfig.WorldSeed + treeId * 7;
        treeComp.attributes = attributes;
        treeComp.SetTerrainManager(terrainManager);
        treeComp.ApplyAttributes();

        int treeLayer = LayerMask.NameToLayer("Tree");
        if (treeLayer >= 0)
        {
            SetLayerRecursively(instance, treeLayer);
        }

        return treeComp;
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
