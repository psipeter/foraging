using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Text;
using UnityEngine;
using UnityEngine.Networking;

// Reads the files in Assets/StreamingAssets (worlds, Interlude files, instruction text, online.json, build_info.json).
// On desktop they are plain files. In a browser there is no file system: the Bootstrap scene fetches the common files listed in
// streaming_files.txt (written by Assets/Editor/BuildInfoWriter before each build: everything outside Experiments/) into memory at the start,
// then the files of the experiment the participant chooses (all of them, or one session's at a time: ExperimentConfig.DownloadPerSession) before
// its game scene starts, and the game reads them from there. Paths are relative to StreamingAssets, with '/' ("Experiments/CF/CF_S1_seed201.world").
public static class StreamingData
{
    private const string Manifest = "streaming_files.txt";
    private static readonly Dictionary<string, byte[]> Cache = new Dictionary<string, byte[]>();

    // True where the files must be fetched over HTTP before use.
    public static bool NeedsPreload => Application.platform == RuntimePlatform.WebGLPlayer;

    public static bool Exists(string relativePath)
    {
        return Cache.ContainsKey(relativePath) || (!NeedsPreload && File.Exists(FullPath(relativePath)));
    }

    // Null when the file does not exist.
    public static byte[] ReadBytes(string relativePath)
    {
        if (Cache.TryGetValue(relativePath, out byte[] bytes))
        {
            return bytes;
        }

        return !NeedsPreload && File.Exists(FullPath(relativePath)) ? File.ReadAllBytes(FullPath(relativePath)) : null;
    }

    public static string ReadText(string relativePath)
    {
        byte[] bytes = ReadBytes(relativePath);
        return bytes == null ? null : Encoding.UTF8.GetString(bytes).TrimStart('﻿');
    }

    private static string FullPath(string relativePath)
    {
        return Path.Combine(Application.streamingAssetsPath, relativePath);
    }

    // True once Preload has fetched the common files (the Boot scene runs again between experiments and need not fetch twice).
    public static bool Loaded { get; private set; }

    // True when every file is available to read (always on desktop, where they are plain files).
    public static bool AllLoaded(IEnumerable<string> relativePaths)
    {
        if (!NeedsPreload)
        {
            return true;
        }

        foreach (string path in relativePaths)
        {
            if (!Cache.ContainsKey(path))
            {
                return false;
            }
        }

        return true;
    }

    // Fetches the common files named in the manifest.
    public static IEnumerator Preload(Action<float> progress, Action<string> failed)
    {
        string[] names = null;
        using (UnityWebRequest request = UnityWebRequest.Get(Application.streamingAssetsPath + "/" + Manifest))
        {
            yield return HttpSink.Send(request, 60f);
            if (request.result != UnityWebRequest.Result.Success)
            {
                failed($"Could not load the file list ({request.error}).");
                yield break;
            }

            names = request.downloadHandler.text.Split(new[] { '\n', '\r' }, StringSplitOptions.RemoveEmptyEntries);
        }

        bool ok = true;
        yield return Fetch(names, progress, reason => { ok = false; failed(reason); });
        Loaded = ok;
    }

    // Fetches the listed files into memory unless they are there already. `progress` gets 0 to 1 (may be null); `failed` the reason, after which
    // nothing more is fetched. A browser only: on desktop the files are read where they are.
    public static IEnumerator Fetch(IEnumerable<string> relativePaths, Action<float> progress, Action<string> failed)
    {
        if (!NeedsPreload)
        {
            progress?.Invoke(1f);
            yield break;
        }

        var wanted = new List<string>();
        foreach (string path in relativePaths)
        {
            if (!Cache.ContainsKey(path) && !wanted.Contains(path))
            {
                wanted.Add(path);
            }
        }

        for (int i = 0; i < wanted.Count; i++)
        {
            progress?.Invoke(i / (float)wanted.Count);
            using (UnityWebRequest request = UnityWebRequest.Get(Application.streamingAssetsPath + "/" + wanted[i]))
            {
                yield return HttpSink.Send(request, 120f);
                if (request.result != UnityWebRequest.Result.Success)
                {
                    failed($"Could not load {wanted[i]} ({request.error}).");
                    yield break;
                }

                Cache[wanted[i]] = request.downloadHandler.data;
            }
        }

        progress?.Invoke(1f);
    }
}
