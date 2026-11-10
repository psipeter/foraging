using System.Runtime.InteropServices;
using UnityEngine;

// Copies text to the system clipboard: through the page in a browser (Assets/Plugins/WebGL/Clipboard.jslib), through Unity elsewhere.
public static class Clipboard
{
#if UNITY_WEBGL && !UNITY_EDITOR
    [DllImport("__Internal")]
    private static extern void CopyToClipboard(string text);
#endif

    public static void Copy(string text)
    {
#if UNITY_WEBGL && !UNITY_EDITOR
        CopyToClipboard(text);
#else
        GUIUtility.systemCopyBuffer = text;
#endif
    }
}
