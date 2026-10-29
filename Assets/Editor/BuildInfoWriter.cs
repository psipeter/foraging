using System;
using System.Diagnostics;
using System.IO;
using UnityEditor;
using UnityEditor.Build;
using UnityEditor.Build.Reporting;

// Writes Assets/StreamingAssets/build_info.json (gitignored) with the git commit the code was built from, so each
// session's manifest.json can say which code produced it. "dirty" is true when files that shape the game (scripts and
// their execution order, shaders, materials, prefabs, render and input settings, the time/quality/physics project
// settings, session configs, worlds, instruction text) differ from that commit; other Inspector churn is ignored.
// Refreshed on Editor load, on entering Play mode and before every build.
[InitializeOnLoad]
public class BuildInfoWriter : IPreprocessBuildWithReport
{
    private static readonly string[] TrackedPaths =
    {
        "Assets/Scripts", "Assets/Shaders", "Assets/ScriptableObjects", "Assets/StreamingAssets", "Assets/Scenes",
        "Assets/Prefabs", "Assets/Materials", "Assets/Resources", "Assets/Settings", "Assets/PlayerInputActions.inputactions",
        "ProjectSettings/TimeManager.asset", "ProjectSettings/QualitySettings.asset", "ProjectSettings/GraphicsSettings.asset",
        "ProjectSettings/DynamicsManager.asset", "ProjectSettings/InputManager.asset", "ProjectSettings/URPProjectSettings.asset",
        "ProjectSettings/ProjectSettings.asset"
    };

    // A script's .meta holds its execution order, which decides what each frame's logic reads; other .meta files are
    // Unity's own churn.
    private static bool IsIgnored(string line)
    {
        string trimmed = line.Trim();
        if (trimmed.Length == 0 || trimmed.Contains("build_info.json"))
        {
            return true;
        }

        return trimmed.EndsWith(".meta") && !trimmed.Contains("Assets/Scripts/");
    }

    public int callbackOrder => 0;

    static BuildInfoWriter()
    {
        EditorApplication.playModeStateChanged += state =>
        {
            if (state == PlayModeStateChange.ExitingEditMode)
            {
                Write();
            }
        };
        EditorApplication.delayCall += Write;
    }

    public void OnPreprocessBuild(BuildReport report)
    {
        Write();
        WriteStreamingFileList();
        AssetDatabase.ImportAsset("Assets/StreamingAssets/build_info.json");
        AssetDatabase.ImportAsset("Assets/StreamingAssets/streaming_files.txt");
    }

    // A browser cannot list a directory: the Bootstrap scene fetches the files named here (StreamingData.Preload).
    private static void WriteStreamingFileList()
    {
        string folder = Path.Combine(Path.GetFullPath(Path.Combine(UnityEngine.Application.dataPath, "..")), "Assets", "StreamingAssets");
        var names = new System.Collections.Generic.List<string>();
        foreach (string file in Directory.GetFiles(folder, "*", SearchOption.AllDirectories))
        {
            string relative = Path.GetRelativePath(folder, file).Replace('\\', '/');
            if (!relative.EndsWith(".meta") && relative != "streaming_files.txt")
            {
                names.Add(relative);
            }
        }

        names.Sort(StringComparer.Ordinal);
        string text = string.Join("\n", names) + "\n";
        string path = Path.Combine(folder, "streaming_files.txt");
        if (!File.Exists(path) || File.ReadAllText(path) != text)
        {
            File.WriteAllText(path, text);
        }
    }

    private static void Write()
    {
        try
        {
            string root = Path.GetFullPath(Path.Combine(UnityEngine.Application.dataPath, ".."));
            string commit = Git(root, "rev-parse HEAD").Trim();
            if (commit.Length == 0)
            {
                return;
            }

            string status = Git(root, "status --porcelain -- " + string.Join(" ", TrackedPaths));
            bool dirty = false;
            foreach (string line in status.Split('\n'))
            {
                if (!IsIgnored(line))
                {
                    dirty = true;
                    break;
                }
            }

            string json = "{\n  \"commit\": \"" + commit + "\",\n  \"dirty\": " + (dirty ? "true" : "false") +
                          ",\n  \"unityVersion\": \"" + UnityEngine.Application.unityVersion + "\"\n}\n";
            string path = Path.Combine(root, "Assets", "StreamingAssets", "build_info.json");
            if (!File.Exists(path) || File.ReadAllText(path) != json)
            {
                File.WriteAllText(path, json);
            }
        }
        catch (Exception)
        {
            // Not a git checkout, or git is not installed: the manifest records the commit as null.
        }
    }

    private static string Git(string workingDirectory, string arguments)
    {
        var info = new ProcessStartInfo("git", arguments)
        {
            WorkingDirectory = workingDirectory,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            UseShellExecute = false,
            CreateNoWindow = true
        };
        using (Process process = Process.Start(info))
        {
            string output = process.StandardOutput.ReadToEnd();
            process.WaitForExit();
            return output;
        }
    }
}
