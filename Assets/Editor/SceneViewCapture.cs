using System;
using System.IO;
using UnityEditor;
using UnityEngine;

// Foraging > Capture Scene view: saves what the Scene view camera is looking at (the session preview or anything else in the open scene) as a PNG, so a view
// chosen in the Editor can be kept without building or playing. Pose, field of view, the scene's lights, the fog and the pipeline in force are the Scene view's own;
// the picture is 16:9 at the Scene view camera's vertical field of view (a Scene view window with another shape shows less or more at the sides). It is rendered in edit
// mode, so the sun is the scene's directional light as it stands, not the game's moving sun. Files go to <project>/Captures/ (git-ignored).
// "... as menu backdrop" also writes the picture over Resources/Backdrops/menu.jpg.
public static class SceneViewCapture
{
    private const int Width = 1920;
    private const int Height = 1080;

    [MenuItem("Foraging/Capture Scene view")]
    private static void CaptureToFolder() => Capture(false);

    [MenuItem("Foraging/Capture Scene view as menu backdrop")]
    private static void CaptureAsBackdrop() => Capture(true);

    public static string Capture(bool asBackdrop)
    {
        SceneView view = SceneView.lastActiveSceneView;
        if (view == null)
        {
            Debug.LogWarning("Capture Scene view: there is no Scene view open.");
            return null;
        }

        Camera camera = view.camera;
        RenderTexture previousTarget = camera.targetTexture;
        float previousAspect = camera.aspect;
        var target = new RenderTexture(Width, Height, 24, RenderTextureFormat.ARGB32, RenderTextureReadWrite.sRGB);
        var texture = new Texture2D(Width, Height, TextureFormat.RGB24, false);
        try
        {
            camera.targetTexture = target;
            camera.aspect = Width / (float)Height;
            camera.Render();
            RenderTexture.active = target;
            texture.ReadPixels(new Rect(0, 0, Width, Height), 0, 0);
            texture.Apply();
        }
        finally
        {
            RenderTexture.active = null;
            camera.targetTexture = previousTarget;
            camera.aspect = previousAspect;
            target.Release();
            UnityEngine.Object.DestroyImmediate(target);
        }

        string root = Path.GetDirectoryName(Application.dataPath);
        string folder = Path.Combine(root, "Captures");
        Directory.CreateDirectory(folder);
        string path = Path.Combine(folder, $"scene_{DateTime.Now:yyyyMMdd_HHmmss}.png");
        File.WriteAllBytes(path, texture.EncodeToPNG());
        if (asBackdrop)
        {
            File.WriteAllBytes(Path.Combine(root, "Assets", "Resources", "Backdrops", "menu.jpg"), texture.EncodeToJPG(92));
            AssetDatabase.ImportAsset("Assets/Resources/Backdrops/menu.jpg");
        }

        UnityEngine.Object.DestroyImmediate(texture);
        Debug.Log($"Capture Scene view: saved {path}{(asBackdrop ? " and the menu backdrop" : "")}.");
        return path;
    }
}
