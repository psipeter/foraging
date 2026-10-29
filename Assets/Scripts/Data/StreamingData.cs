using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Text;
using UnityEngine;
using UnityEngine.Networking;

// Reads the files in Assets/StreamingAssets (worlds, Interlude files, instruction text, online.json, build_info.json).
// On desktop they are plain files. In a browser there is no file system: the Bootstrap scene fetches every file listed in
// streaming_files.txt (written by Assets/Editor/BuildInfoWriter before each build) into memory before the game scene starts,
// and the game reads them from there. Paths are relative to StreamingAssets, with '/' ("Worlds/S1_seed1.world").
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

    // Fetches every listed file into memory. `progress` gets 0 to 1; `failed` the reason, after which nothing more is fetched.
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

        for (int i = 0; i < names.Length; i++)
        {
            progress(i / (float)names.Length);
            using (UnityWebRequest request = UnityWebRequest.Get(Application.streamingAssetsPath + "/" + names[i]))
            {
                yield return HttpSink.Send(request, 120f);
                if (request.result != UnityWebRequest.Result.Success)
                {
                    failed($"Could not load {names[i]} ({request.error}).");
                    yield break;
                }

                Cache[names[i]] = request.downloadHandler.data;
            }
        }

        progress(1f);
    }
}
