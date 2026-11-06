using System;
using System.Text;
using UnityEngine;

// Which session design is played (the default list or the ABAB lists) and, for ABAB, the start variant for this run: 0 = A, 1 = B. The practice session uses that set and the sets alternate every session
// (scripts/feature_sets.py); the variant decides which of GameManager's two session lists is played. Chosen once per process, from, in order:
// the command line (-variant A|B), the page address (?variant=A|B, development builds only), the design (Abab: A, Baba: B), then, for the
// Counterbalanced design, GameManager's Editor override and the participant ID (so a participant who returns to an unfinished run gets the same
// sequence), and A when there is no ID.
public static class DesignVariant
{
    // The design: the command line (-design default|abab|baba|counterbalanced), the page address (?design=, development builds only), online.json
    // "design", then the Editor setting on GameManager. An unrecognised text selects the default design.
    public static DesignMode ChooseDesign(DesignMode editor)
    {
        string design = OnlineSettings.Load().design;
        if (string.IsNullOrEmpty(design))
        {
            return editor;
        }

        switch (design.Trim().ToLowerInvariant())
        {
            case "abab": return DesignMode.Abab;
            case "baba": return DesignMode.Baba;
            case "counterbalanced": return DesignMode.Counterbalanced;
            default: return DesignMode.Default;
        }
    }

    public static int Choose(DesignMode mode, int editorOverride)
    {
        string flag = null;
        if (Application.platform != RuntimePlatform.WebGLPlayer)
        {
            string[] args = Environment.GetCommandLineArgs();
            int i = Array.IndexOf(args, "-variant");
            flag = i >= 0 && i + 1 < args.Length ? args[i + 1] : null;
        }

        if (flag == null && Debug.isDebugBuild)
        {
            flag = OnlineSettings.UrlParameter("variant");
        }

        if (flag != null && (flag.ToUpperInvariant() == "A" || flag.ToUpperInvariant() == "B"))
        {
            return flag.ToUpperInvariant() == "A" ? 0 : 1;
        }

        if (mode == DesignMode.Abab)
        {
            return 0;
        }

        if (mode == DesignMode.Baba)
        {
            return 1;
        }

        if (editorOverride == 0 || editorOverride == 1)
        {
            return editorOverride;
        }

        string pid = OnlineSettings.Load().prolificPid;
        return string.IsNullOrEmpty(pid) ? 0 : ForPid(pid);
    }

    // FNV-1a (32 bit) of the trimmed, lower-cased UTF-8 text, bit 16: mirrors feature_sets.variant_for_pid (test_feature_sets.py pins values).
    public static int ForPid(string pid)
    {
        uint h = 2166136261u;
        foreach (byte b in Encoding.UTF8.GetBytes(pid.Trim().ToLowerInvariant()))
        {
            h = unchecked((h ^ b) * 16777619u);
        }

        return (int)((h >> 16) & 1u);
    }
}
