using System;
using UnityEngine;

/*
Scene setup instructions (SampleScene):

- Create an empty GameObject named "SunController" at root.
- Add this `SunController` component to it.
- Assign:
  - `sessionConfig` to your SessionConfig asset (e.g., DefaultSession).
  - `sunLight` to the existing Directional Light in the scene.
  - `mainCamera` to the Main Camera.
- Set the Main Camera clear flags to SolidColor so `backgroundColor`
  drives the sky color over the session.
*/
public class SunController : MonoBehaviour
{
    [SerializeField] private SessionConfig sessionConfig;
    [SerializeField] private Light sunLight;
    [SerializeField] private Camera mainCamera;
    [SerializeField] private float minSunElevation = 30f;
    [SerializeField] private TerrainManager terrainManager;
    [SerializeField] private TreeGenerator treeGenerator;

    private float sessionTime;
    private bool _sessionEndFired;

    private float SessionDuration =>
        sessionConfig != null ? sessionConfig.SessionDuration : 120f;

    public float SessionProgress => Mathf.Clamp01(sessionTime / Mathf.Max(SessionDuration, 0.0001f));
    public bool SessionComplete => sessionTime >= SessionDuration;
    public Color CurrentAmbientColor => RenderSettings.ambientLight;

    public static event Action OnSessionEnd;

    public float SessionTimeRemaining => Mathf.Max(0f, SessionDuration - sessionTime);

    private void Start()
    {
        if (mainCamera != null)
        {
            mainCamera.clearFlags = CameraClearFlags.SolidColor;
        }
    }

    private void Update()
    {
        if (SessionComplete)
        {
            if (!_sessionEndFired)
            {
                _sessionEndFired = true;
                OnSessionEnd?.Invoke();
            }
            return;
        }

        sessionTime += Time.deltaTime;
        float t = Mathf.Clamp01(sessionTime / Mathf.Max(SessionDuration, 0.0001f));

        UpdateSunTransform(t);
        UpdateSunColorAndIntensity(t);
        UpdateSkyAndAmbient(t);

        if (terrainManager != null)
        {
            terrainManager.UpdateTerrainLighting();
        }

        Color ambient = CurrentAmbientColor;
        // For now, use a simple global query; this keeps TreeGenerator free of extra tracking.
        Tree[] trees = FindObjectsByType<Tree>(FindObjectsSortMode.None);
        for (int i = 0; i < trees.Length; i++)
        {
            trees[i].UpdateLighting(ambient);
        }
    }

    private void UpdateSunTransform(float t)
    {
        if (sunLight == null)
        {
            return;
        }

        float sunArcHeight = sessionConfig != null ? sessionConfig.SunArcHeight : 60f;

        float elevation = Mathf.Sin(t * Mathf.PI) * sunArcHeight;
        elevation = Mathf.Max(elevation, minSunElevation);
        float azimuth = Mathf.Lerp(-90f, 90f, t) + 180f;

        sunLight.transform.rotation = Quaternion.Euler(elevation, azimuth, 0f);
    }

    private void UpdateSunColorAndIntensity(float t)
    {
        if (sunLight == null)
        {
            return;
        }

        Color dawn = sessionConfig != null ? sessionConfig.SunColorDawn : new Color(1.0f, 0.4f, 0.1f);
        Color noon = sessionConfig != null ? sessionConfig.SunColorNoon : new Color(1.0f, 0.95f, 0.8f);

        float noonFactor = Mathf.Sin(t * Mathf.PI);
        noonFactor = Mathf.Clamp01(noonFactor);

        sunLight.color = Color.Lerp(dawn, noon, noonFactor);

        float intensity = Mathf.Lerp(0.1f, 1.2f, noonFactor);
        sunLight.intensity = intensity;
    }

    private void UpdateSkyAndAmbient(float t)
    {
        Color skyDawn = sessionConfig != null ? sessionConfig.SkyColorDawn : new Color(0.8f, 0.4f, 0.2f);
        Color skyNoon = sessionConfig != null ? sessionConfig.SkyColorNoon : new Color(0.3f, 0.6f, 1.0f);
        Color skyDusk = sessionConfig != null ? sessionConfig.SkyColorDusk : new Color(0.6f, 0.2f, 0.1f);

        Color ambientDawn = sessionConfig != null ? sessionConfig.AmbientDawn : new Color(0.15f, 0.1f, 0.08f);
        Color ambientNoon = sessionConfig != null ? sessionConfig.AmbientNoon : new Color(0.2f, 0.2f, 0.25f);
        Color ambientDusk = sessionConfig != null ? sessionConfig.AmbientDusk : new Color(0.12f, 0.08f, 0.06f);

        Color skyColor;
        Color ambientColor;

        if (t < 0.5f)
        {
            float nt = t * 2f;
            skyColor = Color.Lerp(skyDawn, skyNoon, nt);
            ambientColor = Color.Lerp(ambientDawn, ambientNoon, nt);
        }
        else
        {
            float nt = (t - 0.5f) * 2f;
            skyColor = Color.Lerp(skyNoon, skyDusk, nt);
            ambientColor = Color.Lerp(ambientNoon, ambientDusk, nt);
        }

        if (mainCamera != null)
        {
            mainCamera.backgroundColor = skyColor;
        }

        RenderSettings.ambientLight = ambientColor;
    }
}

