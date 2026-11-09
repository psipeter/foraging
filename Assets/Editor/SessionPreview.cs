using System.Reflection;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;

// Foraging > Session preview: builds a real session's world (the terrain and every bush of its world file) in the open game scene in edit mode, so the Scene
// and Game views show the session instead of an empty scene. It uses the game's own components (TerrainManager for the ground, Tree for the bushes) and
// the same scene references (terrain material, bush prefab, rim and ring materials), but puts everything under one object that is never saved with the scene
// and is cleared before Play, before a recompile, before the scene is saved and when the Editor quits (the game builds the world itself at Start; objects
// built in edit mode do not survive a domain reload intact: their materials are lost and the bushes turn pink). The session is the last session (not an
// Interlude) of the GameManager's defaultExperiment (CF_S7 for Complex Features, TUT_S1 for the Tutorial). It is built by Foraging > Session preview and, with
// "Preview on scene open" ticked (the default), also when the Editor or scene opens and after Play, and rebuilt when defaultExperiment changes.
[InitializeOnLoad]
public static class SessionPreview
{
    private const string RootName = "Session preview (not saved)";
    private const string AutoKey = "Foraging.PreviewOnOpen";
    private const string AutoMenu = "Foraging/Preview on scene open";
    private const BindingFlags Private = BindingFlags.Instance | BindingFlags.NonPublic;
    private const HideFlags NotSaved = HideFlags.DontSaveInEditor | HideFlags.DontSaveInBuild;

    private static double _nextCheck;
    private static string _attempted;                                     // what was last built or tried: the check does not retry a failure every second

    static SessionPreview()
    {
        EditorApplication.update += Check;
        AssemblyReloadEvents.beforeAssemblyReload += Clear;
        EditorSceneManager.sceneSaving += (scene, path) => Clear();
        EditorApplication.quitting += Clear;
        EditorSceneManager.sceneOpened += (scene, mode) => _attempted = null;
        EditorApplication.playModeStateChanged += change =>
        {
            if (change == PlayModeStateChange.ExitingEditMode)
            {
                Clear();                                                  // the game builds its own world at Start
            }
        };
    }

    [MenuItem(AutoMenu)]
    private static void ToggleAuto() => EditorPrefs.SetBool(AutoKey, !EditorPrefs.GetBool(AutoKey, true));

    [MenuItem(AutoMenu, true)]
    private static bool ToggleAutoState()
    {
        Menu.SetChecked(AutoMenu, EditorPrefs.GetBool(AutoKey, true));
        return true;
    }

    // Once a second in edit mode: build the preview when it is missing (the Editor or scene just opened, a recompile, the end of Play) or when the
    // GameManager's defaultExperiment is not the one it shows.
    private static void Check()
    {
        if (EditorApplication.timeSinceStartup < _nextCheck)
        {
            return;
        }

        _nextCheck = EditorApplication.timeSinceStartup + 1.0;
        if (EditorApplication.isPlayingOrWillChangePlaymode || EditorApplication.isCompiling || EditorApplication.isUpdating || !EditorPrefs.GetBool(AutoKey, true))
        {
            return;
        }

        SessionConfig session = PreviewSessionOf(Object.FindFirstObjectByType<GameManager>());
        ApplyFog(session);                                                // (cheap: follows an Inspector edit of the fog without rebuilding the bushes)
        string wanted = session != null ? session.name : "none";
        GameObject existing = SceneRoot();
        bool present = existing != null && Healthy(existing);
        if (session != null && (wanted != _attempted || (!present && _attempted == wanted && _builtOnce)))
        {
            Build(false);
        }
    }

    private static bool _builtOnce;

    // The preview's root in the open scene (GameObject.Find could return a scene-less leftover).
    private static GameObject SceneRoot()
    {
        foreach (GameObject root in UnityEngine.SceneManagement.SceneManager.GetActiveScene().GetRootGameObjects())
        {
            if (root.name == RootName)
            {
                return root;
            }
        }

        return null;
    }

    // False when the first bush has lost its materials (see Build): the preview is rebuilt.
    private static bool Healthy(GameObject root)
    {
        Transform bushes = root.transform.Find("Bushes");
        if (bushes == null || bushes.childCount == 0)
        {
            return false;
        }

        Renderer renderer = bushes.GetChild(0).GetComponentInChildren<Renderer>(true);
        return renderer != null && renderer.sharedMaterial != null;
    }

    // The session's fog on the scene's render settings, as GameManager sets it when the session starts, so the preview looks like the session.
    private static void ApplyFog(SessionConfig session)
    {
        if (session == null)
        {
            return;
        }

        float end = Mathf.Max(session.FogEndDistance, session.FogStartDistance + 1f);
        if (RenderSettings.fog != session.FogEnabled || (session.FogEnabled && (RenderSettings.fogMode != FogMode.Linear
            || !Mathf.Approximately(RenderSettings.fogStartDistance, session.FogStartDistance) || !Mathf.Approximately(RenderSettings.fogEndDistance, end))))
        {
            RenderSettings.fog = session.FogEnabled;
            RenderSettings.fogMode = FogMode.Linear;
            RenderSettings.fogStartDistance = session.FogStartDistance;
            RenderSettings.fogEndDistance = end;
        }
    }

    // The session shown for a GameManager: the last one of its defaultExperiment that is not an Interlude.
    // Set by Foraging > Terrain preview: preview this session instead of the last one of the default experiment (null: the default).
    public static SessionConfig Chosen;

    private static SessionConfig PreviewSessionOf(GameManager manager)
    {
        if (manager == null)
        {
            return null;
        }

        if (Chosen != null)
        {
            return Chosen;
        }

        var experiment = new SerializedObject(manager).FindProperty("defaultExperiment").objectReferenceValue as ExperimentConfig;
        SessionConfig found = null;
        if (experiment != null)
        {
            foreach (SessionConfig session in experiment.Sessions)
            {
                if (session != null && !session.IsInterlude)
                {
                    found = session;
                }
            }
        }

        return found;
    }

    [MenuItem("Foraging/Session preview")]
    private static void BuildFromMenu() => Build(true);

    [MenuItem("Foraging/Clear session preview")]
    public static void Clear()
    {
        // FindObjectsByType skips objects that are not saved, so the roots are found among every object in memory. That includes the ones that belong to no
        // scene any more: an object marked not-saved survives a scene reload as a scene-less copy that still renders, with its runtime materials unloaded
        // (magenta bushes) or its bushes drawn over the real ones; earlier versions left one behind at every Play.
        foreach (GameObject candidate in Resources.FindObjectsOfTypeAll<GameObject>())
        {
            if (candidate != null && candidate.name == RootName && candidate.transform.parent == null && !EditorUtility.IsPersistent(candidate))
            {
                Object.DestroyImmediate(candidate);
            }
        }
    }

    public static void Build(bool frame)
    {
        if (Application.isPlaying)
        {
            return;
        }

        var terrainScene = Object.FindFirstObjectByType<TerrainManager>();
        var treeScene = Object.FindFirstObjectByType<TreeGenerator>();
        if (terrainScene == null || treeScene == null)
        {
            return;                                                       // not the game scene
        }

        SessionConfig config = PreviewSessionOf(Object.FindFirstObjectByType<GameManager>());
        if (config == null)
        {
            return;
        }

        _attempted = config.name;
        WorldData world = WorldData.Load(config);
        if (world == null)
        {
            Debug.LogWarning($"Session preview: no world for {config.name}.");
            return;
        }

        Clear();
        var root = new GameObject(RootName);
        Transform ground = BuildGround(root.transform, terrainScene, world, config);
        BuildBushes(root.transform, treeScene, ground.GetComponent<TerrainManager>(), world, config);
        foreach (Transform t in root.GetComponentsInChildren<Transform>(true))
        {
            t.gameObject.hideFlags = NotSaved;
        }

        // The materials and meshes the game's code made at runtime (the bushes, the ground) are not assets and nothing saved refers to them, so Unity unloads
        // them as "unused" at the next Play, save or refresh and the bushes turn magenta. DontSave keeps them.
        foreach (Renderer renderer in root.GetComponentsInChildren<Renderer>(true))
        {
            foreach (Material material in renderer.sharedMaterials)
            {
                if (material != null && string.IsNullOrEmpty(AssetDatabase.GetAssetPath(material)))
                {
                    material.hideFlags |= HideFlags.DontSave;
                }
            }
        }

        foreach (MeshFilter filter in root.GetComponentsInChildren<MeshFilter>(true))
        {
            if (filter.sharedMesh != null && string.IsNullOrEmpty(AssetDatabase.GetAssetPath(filter.sharedMesh)))
            {
                filter.sharedMesh.hideFlags |= HideFlags.DontSave;
            }
        }

        if (frame && SceneView.lastActiveSceneView != null)
        {
            Bounds bounds = ground.GetComponent<MeshRenderer>().bounds;
            SceneView.lastActiveSceneView.LookAt(bounds.center + Vector3.up * 40f, Quaternion.Euler(50f, 30f, 0f), bounds.size.x * 0.45f);
        }

        _builtOnce = true;
        Debug.Log($"Session preview: {config.name}, {world.TreeCount} bushes (not saved with the scene; cleared before Play).");
    }

    private static Transform BuildGround(Transform parent, TerrainManager scene, WorldData world, SessionConfig config)
    {
        var groundObject = new GameObject("Ground");
        groundObject.transform.SetParent(parent, false);
        if (scene.GroundObject != null)
        {
            groundObject.layer = scene.GroundObject.layer;
        }

        var manager = groundObject.AddComponent<TerrainManager>();
        var source = new SerializedObject(scene);
        var target = new SerializedObject(manager);
        target.FindProperty("groundObject").objectReferenceValue = groundObject;
        target.FindProperty("terrainMaterial").objectReferenceValue = source.FindProperty("terrainMaterial").objectReferenceValue;
        target.ApplyModifiedPropertiesWithoutUndo();
        manager.world = world;                                            // (sessionConfig stays unset: the session's mountain colours are applied below on a copy of the material,
                                                                          // since TerrainManager's own code would instantiate a material, which edit mode reports as an error)
        typeof(TerrainManager).GetMethod("Start", Private).Invoke(manager, null);

        var renderer = groundObject.GetComponent<MeshRenderer>();
        var material = new Material(renderer.sharedMaterial) { hideFlags = HideFlags.DontSave };
        material.SetColor("_RockColor", config.MountainRockColor);
        material.SetColor("_SnowColor", config.MountainSnowColor);
        material.SetFloat("_MountainFogStrength", config.MountainFogStrength);
        renderer.sharedMaterial = material;
        return groundObject.transform;
    }

    private static void BuildBushes(Transform parent, TreeGenerator scene, TerrainManager terrain, WorldData world, SessionConfig config)
    {
        var holder = new GameObject("Bushes").transform;
        holder.SetParent(parent, false);
        var source = new SerializedObject(scene);
        var prefab = (GameObject)source.FindProperty("treePrefab").objectReferenceValue;
        var rim = (Material)source.FindProperty("rimMaterial").objectReferenceValue;
        var ring = (Material)source.FindProperty("ringMaterial").objectReferenceValue;
        int treeLayer = LayerMask.NameToLayer("Tree");
        MethodInfo awake = typeof(Tree).GetMethod("Awake", Private);

        for (int s = 0; s < world.TreeCount; s++)
        {
            float px = world.TreePos[2 * s];
            float pz = world.TreePos[2 * s + 1];
            GameObject instance = Object.Instantiate(prefab, new Vector3(px, terrain.SampleElevation(px, pz), pz), Quaternion.identity, holder);
            var tree = instance.GetComponent<Tree>();
            awake?.Invoke(tree, null);                                    // (Awake does not run for an object built in edit mode)
            tree.treeId = s;
            tree.sessionConfig = config;
            tree.rimMaterial = rim;
            tree.ringMaterial = ring;
            tree.fruitCount = world.FruitCount;
            tree.fruitRewards = new int[world.FruitCount];
            System.Array.Copy(world.FruitRewards, s * world.FruitCount, tree.fruitRewards, 0, world.FruitCount);
            tree.fruitRadius = config.FruitRadius;
            tree.fruitSeed = config.WorldSeed + s * 7;
            tree.attributes = new TreeAttributes { shape = world.Shape[s], color = world.Color[s], moisture = world.Moisture[s] };
            tree.SetTerrainManager(terrain);
            tree.ApplyAttributes();
            if (treeLayer >= 0)
            {
                SetLayer(instance, treeLayer);
            }
        }
    }

    private static void SetLayer(GameObject obj, int layer)
    {
        obj.layer = layer;
        foreach (Transform child in obj.transform)
        {
            SetLayer(child.gameObject, layer);
        }
    }
}
