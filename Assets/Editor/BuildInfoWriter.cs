using System;
using System.Diagnostics;
using System.IO;
using UnityEditor;
using UnityEditor.Build;
using UnityEditor.Build.Reporting;

// Writes Assets/StreamingAssets/build_info.json (gitignored) with the git commit the code was built from, so each
// session's manifest.json can say which code produced it. "dirty" is true when files that shape the game (scripts,
// shaders, session configs, worlds, instruction text) differ from that commit; Inspector churn elsewhere is ignored.
// Refreshed on Editor load, on entering Play mode and before every build.
[InitializeOnLoad]
public class BuildInfoWriter : IPreprocessBuildWithReport
{
    private static readonly string[] TrackedPaths =
    {
        "Assets/Scripts", "Assets/Shaders", "Assets/ScriptableObjects", "Assets/StreamingAssets", "Assets/Scenes"
    };

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
        AssetDatabase.ImportAsset("Assets/StreamingAssets/build_info.json");
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
                // Ignore the generated file itself and .meta churn.
                if (line.Trim().Length > 0 && !line.Contains("build_info.json") && !line.EndsWith(".meta"))
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
