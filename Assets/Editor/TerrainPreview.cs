using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using UnityEditor;
using UnityEngine;

// Foraging > Terrain preview: tweak terrain and balancing fields and see the result in 3D without touching any real session. Pick a source session and "Start from it": the window makes
// a throwaway copy (<code>_PREVIEW.asset, git-ignored) and edits only that. Change its terrain fields here (they are the copy's own fields), press "Regenerate world and
// preview": the window saves the copy, runs scripts/world.py for it (the world is generated in Python, not in Unity) and rebuilds the session preview in the open scene
// (Foraging > Session preview) for it, so you can fly around the Scene view or press Play. When you have chosen values, they go into the experiment's design table
// (scripts/design/<code>.py) and "Delete the preview files" removes the copy and its world. The Interlude file is not regenerated (it matters only for the real game).
// The window runs ./venv/bin/python in the project folder.
public class TerrainPreview : EditorWindow
{
    private static readonly string[] Fields =
    {
        "terrainNoiseFrequency", "terrainNoiseOctaves", "terrainMaxElevation", "moistureTerraceMode",
        "moistureTerraceLevels", "moistureTerraceUnevenness",
        "moistureTerraceSharpness", "moistureTerraceResidual",
        "terraceMeanWidth", "terraceWidthSpread", "terraceMaxBand", "terraceMinStep", "terracePhaseShift", "terracePhaseFrequency", "terraceStrength",
        "terraceDiffusionIterations", "terraceDiffusionEdge",
        "spatialBalance", "featureBalance", "featureBalanceTarget", "featureBalanceScales",
    };

    private readonly List<SessionConfig> _sessions = new List<SessionConfig>();
    private int _choice;
    private SessionConfig _preview;
    private Process _process;
    private string _status = "";
    private Vector2 _scroll;

    [MenuItem("Foraging/Terrain preview")]
    private static void Open() => GetWindow<TerrainPreview>("Terrain preview");

    private void OnEnable() => FindSessions();

    private void FindSessions()
    {
        _sessions.Clear();
        ExperimentCatalog catalog = ExperimentCatalog.Load();
        if (catalog == null)
        {
            return;
        }

        foreach (ExperimentConfig experiment in catalog.Experiments)
        {
            if (experiment == null)
            {
                continue;
            }

            foreach (SessionConfig session in experiment.Sessions)
            {
                if (session != null && !session.IsInterlude)
                {
                    _sessions.Add(session);
                }
            }
        }

        _choice = Mathf.Clamp(_choice, 0, Mathf.Max(0, _sessions.Count - 1));
    }

    private void OnGUI()
    {
        if (_sessions.Count == 0)
        {
            EditorGUILayout.HelpBox("No sessions in the experiment catalog.", MessageType.Warning);
            if (GUILayout.Button("Look again"))
            {
                FindSessions();
            }

            return;
        }

        var names = new string[_sessions.Count];
        for (int i = 0; i < names.Length; i++)
        {
            names[i] = _sessions[i].name;
        }

        _choice = EditorGUILayout.Popup("Source session", _choice, names);
        SessionConfig source = _sessions[_choice];
        string previewPath = PreviewPath(source);
        _preview = AssetDatabase.LoadAssetAtPath<SessionConfig>(previewPath);
        using (new EditorGUILayout.HorizontalScope())
        {
            if (GUILayout.Button(_preview == null ? $"Start from {source.name}" : $"Reset the preview to {source.name}"))
            {
                _preview = CreatePreview(source);
                _status = $"The preview copy {_preview.name} starts from {source.name}.";
            }

            using (new EditorGUI.DisabledScope(_preview == null))
            {
                if (GUILayout.Button("Delete the preview files"))
                {
                    DeletePreview(source);
                    _preview = null;
                    _status = "The preview copy and its world are deleted.";
                }
            }
        }

        if (_preview == null)
        {
            EditorGUILayout.HelpBox("Start from a session to get a throwaway copy whose terrain fields you can change.", MessageType.Info);
            return;
        }

        SessionConfig session = _preview;
        var serialized = new SerializedObject(session);
        serialized.Update();
        _scroll = EditorGUILayout.BeginScrollView(_scroll);
        foreach (string field in Fields)
        {
            SerializedProperty property = serialized.FindProperty(field);
            if (property != null)
            {
                EditorGUILayout.PropertyField(property, true);
            }
        }

        EditorGUILayout.EndScrollView();
        serialized.ApplyModifiedProperties();

        using (new EditorGUI.DisabledScope(_process != null))
        {
            if (GUILayout.Button("Regenerate world and preview"))
            {
                Regenerate(session);
            }
        }

        EditorGUILayout.HelpBox(_status.Length > 0 ? _status : "Change the fields, then regenerate. The world is made by scripts/world.py (about 10 to 60 seconds).", MessageType.Info);
    }

    private static string PreviewPath(SessionConfig source) => $"Assets/ScriptableObjects/Experiments/{source.ExperimentCode}/{source.ExperimentCode}_PREVIEW.asset";

    // A fresh copy of `source` named <code>_PREVIEW (replacing an earlier one), the session the preview then shows.
    public static SessionConfig CreatePreview(SessionConfig source)
    {
        string path = PreviewPath(source);
        AssetDatabase.DeleteAsset(path);
        AssetDatabase.CopyAsset(AssetDatabase.GetAssetPath(source), path);
        AssetDatabase.SaveAssets();
        SessionConfig copy = AssetDatabase.LoadAssetAtPath<SessionConfig>(path);
        SessionPreview.Chosen = copy;
        return copy;
    }

    private static void DeletePreview(SessionConfig source)
    {
        SessionPreview.Chosen = null;
        SessionPreview.Clear();
        AssetDatabase.DeleteAsset(PreviewPath(source));
        foreach (string file in Directory.GetFiles(Path.Combine(Application.streamingAssetsPath, "Experiments", source.ExperimentCode), $"{source.ExperimentCode}_PREVIEW_seed*"))
        {
            File.Delete(file);
        }

        AssetDatabase.Refresh();
    }

    private void Regenerate(SessionConfig session)
    {
        EditorUtility.SetDirty(session);
        AssetDatabase.SaveAssets();
        string root = Path.GetDirectoryName(Application.dataPath);
        string python = Path.Combine(root, "venv", "bin", "python");
        var info = new ProcessStartInfo(python, $"scripts/world.py {session.name} --unity")
        {
            WorkingDirectory = root,
            UseShellExecute = false,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            CreateNoWindow = true,
        };
        try
        {
            _process = Process.Start(info);
        }
        catch (System.Exception exception)
        {
            _status = $"Could not start {python}: {exception.Message}";
            return;
        }

        _status = $"Generating the world of {session.name} ...";
        SessionPreview.Chosen = session;
        EditorApplication.update -= Poll;
        EditorApplication.update += Poll;
    }

    private void Poll()
    {
        if (_process == null || !_process.HasExited)
        {
            return;
        }

        EditorApplication.update -= Poll;
        string output = _process.StandardOutput.ReadToEnd().Trim();
        string error = _process.StandardError.ReadToEnd().Trim();
        int code = _process.ExitCode;
        _process = null;
        if (code != 0)
        {
            _status = $"world.py failed ({code}): {error}";
            Repaint();
            return;
        }

        AssetDatabase.Refresh();
        SessionPreview.Build(false);
        _status = $"Preview rebuilt. {output}";
        Repaint();
    }
}
