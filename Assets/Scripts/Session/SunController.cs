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
    public SessionConfig sessionConfig;
    [SerializeField] private Light sunLight;
    [SerializeField] private Camera mainCamera;
    [SerializeField] private TerrainManager terrainManager;

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
    }

    private void UpdateSunTransform(float t)
    {
        if (sunLight == null)
        {
            return;
        }

        float sunArcHeight = sessionConfig != null ? sessionConfig.SunArcHeight : 60f;
        float minEl = sessionConfig != null ? sessionConfig.MinSunElevation : 5f;

        float elevation = Mathf.Sin(t * Mathf.PI) * sunArcHeight;
        elevation = Mathf.Max(elevation, minEl);
        float azimuth = Mathf.Lerp(-90f, 90f, t) + 180f;

        sunLight.transform.rotation = Quaternion.Euler(elevation, azimuth, 0f);
    }

    private void UpdateSunColorAndIntensity(float t)
    {
        if (sunLight == null)
        {
            return;
        }

        sunLight.color = new Color(1.0f, 0.95f, 0.85f);

        float blend = Mathf.Sin(t * Mathf.PI);
        float dawnIntensity = sessionConfig != null ? sessionConfig.SunIntensityDawn : 0.4f;
        float noonIntensity = sessionConfig != null ? sessionConfig.SunIntensityNoon : 1.2f;
        sunLight.intensity = Mathf.Lerp(dawnIntensity, noonIntensity, blend);
    }

    private void UpdateSkyAndAmbient(float t)
    {
        Color skyDawn = sessionConfig != null ? sessionConfig.SkyColorDawn : new Color(0.8f, 0.4f, 0.2f);
        Color skyNoon = sessionConfig != null ? sessionConfig.SkyColorNoon : new Color(0.3f, 0.6f, 1.0f);

        float blend = Mathf.Sin(t * Mathf.PI);
        Color skyColor = Color.Lerp(skyDawn, skyNoon, blend);
        Color ambientColor = skyColor * 0.7f;

        if (mainCamera != null)
        {
            mainCamera.backgroundColor = skyColor;
        }

        RenderSettings.ambientLight = ambientColor;
    }
}

