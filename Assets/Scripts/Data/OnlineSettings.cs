using System;
using System.IO;
using UnityEngine;

// Which build commit the game was built from (written by Assets/Editor/BuildInfoWriter into StreamingAssets/build_info.json).
[Serializable]
public class BuildInfo
{
    public string commit;
    public bool dirty;
    public string unityVersion;

    public static BuildInfo Read()
    {
        try
        {
            if (StreamingData.Exists("build_info.json"))
            {
                return JsonUtility.FromJson<BuildInfo>(StreamingData.ReadText("build_info.json"));
            }
        }
        catch { }

        return null;
    }
}

// Whether and where the game uploads its data: StreamingAssets/online.json, overridden by the command line
// (-onlineUrl <functions url> -onlineKey <publishable key> turn uploading on, -pid <id> sets the participant's Prolific ID).
// The key is the project's publishable key, which is meant to ship in clients. Uploading is off in the Editor unless
// "uploadInEditor" is true, so developing never writes to the study database.
[Serializable]
public class OnlineSettings
{
    public bool enabled;
    public string url;
    public string apikey;
    public bool uploadInEditor;

    [NonSerialized] public string prolificPid;

    public bool Active =>
        enabled && !string.IsNullOrEmpty(url) && !string.IsNullOrEmpty(apikey) && (!Application.isEditor || uploadInEditor);

    public static OnlineSettings Load()
    {
        var settings = new OnlineSettings();
        try
        {
            if (StreamingData.Exists("online.json"))
            {
                settings = JsonUtility.FromJson<OnlineSettings>(StreamingData.ReadText("online.json")) ?? settings;
            }
        }
        catch (Exception e)
        {
            Debug.LogWarning($"online.json could not be read: {e.Message}");
        }

        if (Application.platform != RuntimePlatform.WebGLPlayer)
        {
            string[] args = Environment.GetCommandLineArgs();
            for (int i = 0; i + 1 < args.Length; i++)
            {
                switch (args[i])
                {
                    case "-onlineUrl": settings.url = args[i + 1]; settings.enabled = settings.uploadInEditor = true; break;
                    case "-onlineKey": settings.apikey = args[i + 1]; break;
                    case "-pid": settings.prolificPid = args[i + 1]; break;
                }
            }
        }

        // In a browser the same come from the page's address: ?PROLIFIC_PID=<id> (or ?pid=), and, in a development build only (a link
        // must not be able to redirect a participant's data), ?onlineUrl=...&onlineKey=...
        string pid = UrlParameter("PROLIFIC_PID") ?? UrlParameter("pid");
        if (pid != null)
        {
            settings.prolificPid = pid;
        }

        if (Debug.isDebugBuild && UrlParameter("onlineUrl") != null)
        {
            settings.url = UrlParameter("onlineUrl");
            settings.apikey = UrlParameter("onlineKey") ?? settings.apikey;
            settings.enabled = settings.uploadInEditor = true;
        }

        return settings;
    }

    // A query parameter of the page's address (empty or absent outside a browser), or null.
    public static string UrlParameter(string name)
    {
        string url = Application.absoluteURL;
        int q = string.IsNullOrEmpty(url) ? -1 : url.IndexOf('?');
        if (q < 0)
        {
            return null;
        }

        string query = url.Substring(q + 1);
        int hash = query.IndexOf('#');
        foreach (string pair in (hash >= 0 ? query.Substring(0, hash) : query).Split('&'))
        {
            int eq = pair.IndexOf('=');
            if (eq > 0 && Uri.UnescapeDataString(pair.Substring(0, eq)) == name)
            {
                return Uri.UnescapeDataString(pair.Substring(eq + 1));
            }
        }

        return null;
    }
}
