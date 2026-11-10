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
    private float _short = 1f;
    private int _repeats = RunModes.AllRepeats;

    [MenuItem("Foraging/Experiments")]
    private static void Open() => GetWindow<ExperimentPlayer>("Experiments");

    private void OnEnable()
    {
        _short = EditorPrefs.GetFloat(RunModes.ShortKey, 1f);
        _repeats = EditorPrefs.GetInt(RunModes.RepeatsKey, RunModes.AllRepeats);
    }

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
        EditorGUI.BeginChangeCheck();
        _short = EditorGUILayout.Slider(new GUIContent("Short", "0 to 1: every session lasts this fraction of its length (at least 10 s) and every Interlude plays this fraction of its trials (at least 3). 1 = as designed. Kept between runs; applies to Play and to Play with the menu."), _short, 0f, 1f);
        _repeats = Mathf.Max(1, EditorGUILayout.IntField(new GUIContent("Repeats", "1 or more: a cell's sessions are played up to this iteration (1 = one of each, with their Interludes); more than any iteration that exists = all. Kept between runs; applies to Play and to Play with the menu."), _repeats));
        if (EditorGUI.EndChangeCheck())
        {
            EditorPrefs.SetFloat(RunModes.ShortKey, _short);
            EditorPrefs.SetInt(RunModes.RepeatsKey, _repeats);
        }

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

        EditorGUILayout.HelpBox("Play starts at the Boot scene and skips the menu, at the part chosen above (a part past the end starts at the last); afterwards the Editor is as it was (the play button starts the open scene with the GameManager's default experiment). Short and Repeats make a reduced run (RunModes): the parts counted above are those of the full experiment.", MessageType.None);
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
