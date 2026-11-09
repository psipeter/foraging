using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;

// Foraging > Experiments: play one experiment straight from the Editor without the login and the menu, or start from the Boot scene to try the menu.
// "Play" sets an EditorPref that Bootstrap and GameManager read (it never reaches a build); "Play with the menu" clears it and starts at the Boot scene,
// where the menu offers every experiment of the catalog (there is no data server in the Editor unless uploadInEditor is set).
public class ExperimentPlayer : EditorWindow
{
    private const string ExperimentKey = "Foraging.Experiment";
    private const string StartPartKey = "Foraging.StartPart";
    private const string BootScene = "Assets/Scenes/Boot.unity";

    private int _startPart = 1;

    [MenuItem("Foraging/Experiments")]
    private static void Open() => GetWindow<ExperimentPlayer>("Experiments");

    private void OnGUI()
    {
        var catalog = ExperimentCatalog.Load();
        if (catalog == null)
        {
            EditorGUILayout.HelpBox("No Resources/ExperimentCatalog asset.", MessageType.Warning);
            return;
        }

        EditorGUILayout.LabelField("Play an experiment", EditorStyles.boldLabel);
        _startPart = Mathf.Max(1, EditorGUILayout.IntField(new GUIContent("Start at part", "1 = the first part. A part is a session or an Interlude, in play order (\"Part 3 of 18\" on the screens). Applies to Play below, not to Play with the menu."), _startPart));
        foreach (ExperimentConfig experiment in catalog.Experiments)
        {
            if (experiment == null)
            {
                continue;
            }

            using (new EditorGUILayout.HorizontalScope())
            {
                EditorGUILayout.LabelField($"{experiment.Title} ({experiment.Code}, {experiment.Sessions.Count} parts)");
                if (GUILayout.Button("Play", GUILayout.Width(120)))
                {
                    Play(experiment.Code, _startPart);
                }
            }
        }

        EditorGUILayout.Space();
        if (GUILayout.Button("Play with the menu (Boot scene)"))
        {
            Play("", 1);
        }

        EditorGUILayout.HelpBox("Play starts at the Boot scene and skips the menu, at the part chosen above (a part past the end starts at the last); afterwards the Editor is as it was (the play button starts the open scene with the GameManager's default experiment). The quick-test toggle (Foraging > Quick test) still applies.", MessageType.None);
    }

    private static void Play(string code, int startPart)
    {
        EditorPrefs.SetString(ExperimentKey, code);
        EditorPrefs.SetInt(StartPartKey, startPart);
        EditorSceneManager.playModeStartScene = AssetDatabase.LoadAssetAtPath<SceneAsset>(BootScene);
        EditorApplication.playModeStateChanged -= Restore;
        EditorApplication.playModeStateChanged += Restore;
        EditorApplication.isPlaying = true;
    }

    // After the run the Editor is as it was: the play button starts the open scene again, with the GameManager's default experiment.
    private static void Restore(PlayModeStateChange change)
    {
        if (change == PlayModeStateChange.EnteredEditMode)
        {
            EditorPrefs.DeleteKey(ExperimentKey);
            EditorPrefs.DeleteKey(StartPartKey);
            EditorSceneManager.playModeStartScene = null;
            EditorApplication.playModeStateChanged -= Restore;
        }
    }
}
