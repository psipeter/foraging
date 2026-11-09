using System.Text;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.Rendering.Universal;

// Development builds only (a release build does nothing, so a link cannot change what a participant sees). Two address options to find out why a browser build
// does not look like the Editor:
//   ?quality=<n>   switches to quality level n at start (0 Mobile, 1 PC): the WebGL build defaults to level 0, whose pipeline asset has a shadow distance of 50, one
//                  cascade, no soft shadows and a render scale of 0.8, against 300, four cascades, soft shadows and 1 for the PC level.
//   ?lightinfo=1   a readout in the corner: the quality level and pipeline asset, the shadow settings in force, the sun (intensity, colour, shadow type, elevation), the
//                  ambient (mode, intensity, the probe's brightness upward, sideways and downward) and the fog.
public class LightingDebug : MonoBehaviour
{
    private string _text = "";
    private float _next;
    private GUIStyle _style;

    [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.BeforeSceneLoad)]
    private static void Begin()
    {
        if (!Debug.isDebugBuild)
        {
            return;
        }

        string quality = OnlineSettings.UrlParameter("quality");
        if (quality != null && int.TryParse(quality, out int level) && level >= 0 && level < QualitySettings.names.Length)
        {
            QualitySettings.SetQualityLevel(level, true);
        }

        if (OnlineSettings.UrlParameter("lightinfo") != null)
        {
            var host = new GameObject("LightingDebug");
            DontDestroyOnLoad(host);
            host.AddComponent<LightingDebug>();
        }
    }

    private void OnGUI()
    {
        if (_style == null)
        {
            _style = new GUIStyle(GUI.skin.box) { alignment = TextAnchor.UpperLeft, fontSize = 15, richText = false };
            _style.normal.textColor = Color.white;
        }

        if (Time.unscaledTime >= _next)
        {
            _text = Describe();
            _next = Time.unscaledTime + 1f;
        }

        GUI.Box(new Rect(8f, 8f, 620f, 24f * (1 + _text.Split('\n').Length)), _text, _style);
    }

    private static string Describe()
    {
        var text = new StringBuilder();
        RenderPipelineAsset pipeline = GraphicsSettings.currentRenderPipeline;
        text.AppendLine($"quality {QualitySettings.GetQualityLevel()} {QualitySettings.names[QualitySettings.GetQualityLevel()]}   pipeline {(pipeline != null ? pipeline.name : "none")}   {Screen.width}x{Screen.height}");
        if (pipeline is UniversalRenderPipelineAsset urp)
        {
            text.AppendLine($"shadows: distance {urp.shadowDistance:0}, cascades {urp.shadowCascadeCount}, map {urp.mainLightShadowmapResolution}, soft {urp.supportsSoftShadows}, main light shadows {urp.supportsMainLightShadows}, render scale {urp.renderScale:0.00}");
        }

        Light sun = RenderSettings.sun;
        if (sun == null)
        {
            foreach (Light candidate in FindObjectsByType<Light>(FindObjectsSortMode.None))
            {
                if (candidate.type == LightType.Directional)
                {
                    sun = candidate;
                    break;
                }
            }
        }

        if (sun != null)
        {
            text.AppendLine($"sun: intensity {sun.intensity:0.00}, colour {sun.color.r:0.00} {sun.color.g:0.00} {sun.color.b:0.00}, shadows {sun.shadows} (strength {sun.shadowStrength:0.00}), elevation {-sun.transform.eulerAngles.x:0}");
        }

        SphericalHarmonicsL2 probe = RenderSettings.ambientProbe;
        var directions = new[] { Vector3.up, Vector3.forward, Vector3.down };
        var colours = new Color[3];
        probe.Evaluate(directions, colours);
        text.AppendLine($"ambient: mode {RenderSettings.ambientMode}, intensity {RenderSettings.ambientIntensity:0.00}, probe brightness up {colours[0].grayscale:0.000} side {colours[1].grayscale:0.000} down {colours[2].grayscale:0.000}");
        text.Append($"fog: {RenderSettings.fog} {RenderSettings.fogStartDistance:0} to {RenderSettings.fogEndDistance:0}, skybox {(RenderSettings.skybox != null ? RenderSettings.skybox.name : "none")}, {1f / Mathf.Max(Time.unscaledDeltaTime, 1e-4f):0} fps");
        return text.ToString();
    }
}
