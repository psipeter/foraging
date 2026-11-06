using UnityEditor;

// Foraging > Quick test: a local switch for playing short sessions (practice 15 s, other sessions 30 s, at most 5 Interlude trials; the numbers are
// GameManager's quick* fields). An EditorPref, so it is per machine, is not saved in the scene and never reaches a build; GameManager applies it to a copy of
// each session asset, so no asset changes.
public static class QuickTestMenu
{
    private const string Key = "Foraging.QuickTest";
    private const string Path = "Foraging/Quick test (short sessions)";

    [MenuItem(Path)]
    private static void Toggle()
    {
        EditorPrefs.SetBool(Key, !EditorPrefs.GetBool(Key, false));
    }

    [MenuItem(Path, true)]
    private static bool Validate()
    {
        Menu.SetChecked(Path, EditorPrefs.GetBool(Key, false));
        return true;
    }
}
