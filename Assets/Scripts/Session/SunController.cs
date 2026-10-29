using System;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.Rendering.Universal;

/*
Scene setup instructions (SampleScene):

- Create an empty GameObject named "SunController" at root.
- Add this `SunController` component to it.
- Assign:
  - `sunLight` to the existing Directional Light in the scene.
  - `mainCamera` to the Main Camera.
  - `skyboxMaterial` to SkyboxMaterial.mat (a runtime copy is driven; the asset is never written).
  - `postVolume` to the Global Volume (a runtime copy of its profile is driven).
  (`sessionConfig` is assigned by GameManager.)
- Set the Main Camera clear flags to Skybox (also applied at runtime in Start()).

The sun's direction follows a real solar path (SolveSun). Its colour comes from atmospheric transmittance, and the
procedural sky reddens by itself from its direction; brightness, ambient and exposure follow curves of the sun's elevation
set in SessionConfig (EvaluateLighting). See docs/DECISIONS.md ("Lighting").
*/
public class SunController : MonoBehaviour
{
    public SessionConfig sessionConfig;
    [SerializeField] private Light sunLight;
    [SerializeField] private Camera mainCamera;
    [SerializeField] private Material skyboxMaterial;
    [Tooltip("The scene's global post-processing volume; its Color Adjustments post-exposure is driven by the sun's elevation (a runtime copy of the profile is used, so the asset is never written).")]
    [SerializeField] private Volume postVolume;

    private float sessionTime;
    private bool _sessionEndFired;
    private Material _skyInstance;
    private ColorAdjustments _colorAdjustments;
    private float _lastEnvironmentTime = float.NegativeInfinity;
    private float _lastEnvironmentElevation = float.NaN;
    private float _lastPostExposure = float.NaN;

    private float SessionDuration =>
        sessionConfig != null ? sessionConfig.SessionDuration : 120f;

    public bool SessionComplete => sessionTime >= SessionDuration;

    public static event Action OnSessionEnd;

    public float SessionTimeRemaining => Mathf.Max(0f, SessionDuration - sessionTime);

    // Continuing an interrupted session: the clock (and so the sun) picks up where the data says it stopped.
    public void SetSessionTime(float seconds)
    {
        sessionTime = Mathf.Max(0f, seconds);
    }

    // Ends the session now (the Interlude ends when its trials are done, not at a fixed time).
    public void EndSession()
    {
        sessionTime = SessionDuration;
    }

    private void Start()
    {
        if (mainCamera != null)
        {
            mainCamera.clearFlags = CameraClearFlags.Skybox;
        }

        // The sky is driven on a runtime copy of the material. Writing to the shared SkyboxMaterial asset would be saved
        // into the file by the Editor after every Play (leaving it at whatever the last frame was), so the asset is
        // never touched and stays identical between plays.
        if (skyboxMaterial != null)
        {
            _skyInstance = new Material(skyboxMaterial) { name = skyboxMaterial.name + " (runtime)" };
            RenderSettings.skybox = _skyInstance;
        }

        // Post-exposure goes through a runtime copy of the volume profile (Volume.profile instantiates it), never the asset.
        if (postVolume != null && postVolume.profile != null)
        {
            if (!postVolume.profile.TryGet(out _colorAdjustments))
            {
                _colorAdjustments = postVolume.profile.Add<ColorAdjustments>(true);
            }

            _colorAdjustments.active = true;
            _colorAdjustments.postExposure.overrideState = true;
            _colorAdjustments.postExposure.value = 0f;
        }
    }

    private void OnDestroy()
    {
        if (_skyInstance != null)
        {
            if (RenderSettings.skybox == _skyInstance)
            {
                RenderSettings.skybox = skyboxMaterial;
            }

            Destroy(_skyInstance);
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
        // The sun follows a real solar path from sunStartElevation in the morning to
        // sunEndElevation in the afternoon, mapped onto the session's length (a shorter session plays the same path faster).
        // Interludes hold the sun still at solar noon.
        bool frozen = sessionConfig != null && sessionConfig.FreezeSun;
        float progress = frozen ? 0f : Mathf.Clamp01(sessionTime / Mathf.Max(SessionDuration, 0.0001f));
        SolveSun(progress, frozen, out float elevation, out float azimuth);

        UpdateSunTransform(elevation, azimuth);

        UnityEngine.Profiling.Profiler.BeginSample("SunController.ApplyLighting");
        ApplyLighting(elevation);
        UnityEngine.Profiling.Profiler.EndSample();
    }

    // Solar position from latitude and declination. The session runs from the morning hour angle at which the sun is at
    // sunStartElevation to the afternoon hour angle at which it is at sunEndElevation (both from the same relation
    // sin(el) = sin(lat) sin(dec) + cos(lat) cos(dec) cos(hour)); hour angle 0 is solar noon. Elevation and azimuth (degrees;
    // azimuth from world +Z toward +X, the direction to the sun) follow the standard formulas, so the path rises in the east,
    // peaks toward the south and sets in the west (moving faster near the horizon).
    private void SolveSun(float progress, bool solarNoon, out float elevationDeg, out float azimuthDeg)
    {
        float latitude = (sessionConfig != null ? sessionConfig.SunLatitude : 40f) * Mathf.Deg2Rad;
        float declination = (sessionConfig != null ? sessionConfig.SunDeclination : 12f) * Mathf.Deg2Rad;
        float endElevation = (sessionConfig != null ? sessionConfig.SunEndElevation : 10f) * Mathf.Deg2Rad;
        float startElevation = (sessionConfig != null ? sessionConfig.SunStartElevation : 30f) * Mathf.Deg2Rad;

        float sinLat = Mathf.Sin(latitude), cosLat = Mathf.Cos(latitude);
        float sinDec = Mathf.Sin(declination), cosDec = Mathf.Cos(declination);
        float hourStart = -HourAngleAt(startElevation, sinLat, cosLat, sinDec, cosDec);
        float hourEnd = Mathf.Max(HourAngleAt(endElevation, sinLat, cosLat, sinDec, cosDec), hourStart);
        float hour = solarNoon ? 0f : Mathf.Lerp(hourStart, hourEnd, progress);

        float sinEl = sinLat * sinDec + cosLat * cosDec * Mathf.Cos(hour);
        float el = Mathf.Asin(Mathf.Clamp(sinEl, -1f, 1f));
        float cosAz = (sinDec - Mathf.Sin(el) * sinLat) / Mathf.Max(Mathf.Cos(el) * cosLat, 1e-4f);
        float az = Mathf.Acos(Mathf.Clamp(cosAz, -1f, 1f));
        if (hour > 0f)
        {
            az = 2f * Mathf.PI - az;     // afternoon: the west side
        }

        elevationDeg = el * Mathf.Rad2Deg;
        azimuthDeg = az * Mathf.Rad2Deg;
    }

    // Absolute hour angle (radians, 0 at noon) at which the sun is at the given elevation.
    private static float HourAngleAt(float elevation, float sinLat, float cosLat, float sinDec, float cosDec)
    {
        float cosH = (Mathf.Sin(elevation) - sinLat * sinDec) / Mathf.Max(cosLat * cosDec, 1e-4f);
        return Mathf.Acos(Mathf.Clamp(cosH, -1f, 1f));
    }

    private void UpdateSunTransform(float elevationDeg, float azimuthDeg)
    {
        if (sunLight == null)
        {
            return;
        }

        float minEl = sessionConfig != null ? sessionConfig.MinSunElevation : 0f;
        float offset = sessionConfig != null ? sessionConfig.SunAzimuthOffset : 0f;
        float elevation = Mathf.Max(elevationDeg, minEl);

        // The light travels from the sun toward the scene: its yaw is the sun's azimuth + 180 degrees.
        sunLight.transform.rotation = Quaternion.Euler(elevation, azimuthDeg + 180f + offset, 0f);
    }

    // Everything computed from the sun's elevation, as plain values.
    public struct LightingState
    {
        public Color sunColor;
        public float sunIntensity;
        public float ambientIntensity;
        public float skyExposure;
        public float postExposureEv;
    }

    // Hue comes from physics: the sun's colour is its transmittance through the atmosphere, exp(-tau * air mass) per channel
    // (Kasten-Young air mass), normalised so only the chroma changes (warm white at noon, orange near the horizon), and the
    // procedural sky already reddens from the sun's direction. Brightness comes from the configured curves of elevation.
    public LightingState EvaluateLighting(float elevationDeg)
    {
        SessionConfig c = sessionConfig;
        float el = Mathf.Clamp(elevationDeg, 0.5f, 90f);
        float airMass = 1f / (Mathf.Sin(el * Mathf.Deg2Rad) + 0.50572f * Mathf.Pow(el + 6.07995f, -1.6364f));
        Vector3 tau = c != null ? c.SunExtinction : new Vector3(0.10f, 0.16f, 0.30f);
        float strength = c != null ? c.SunHueStrength : 0.8f;

        var physical = new Color(Mathf.Exp(-tau.x * airMass), Mathf.Exp(-tau.y * airMass), Mathf.Exp(-tau.z * airMass), 1f);
        float peak = Mathf.Max(physical.r, Mathf.Max(physical.g, physical.b));
        physical = new Color(physical.r / peak, physical.g / peak, physical.b / peak, 1f);
        Color neutral = new Color(1.0f, 0.95f, 0.85f);

        LightingState light;
        light.sunColor = Color.Lerp(neutral, physical, strength);
        light.sunIntensity = c != null ? c.SunIntensityByElevation.Evaluate(elevationDeg) : 1.2f;
        light.ambientIntensity = c != null ? c.AmbientIntensityByElevation.Evaluate(elevationDeg) : 1f;
        light.skyExposure = c != null ? c.SkyExposureByElevation.Evaluate(elevationDeg) : 1.3f;
        light.postExposureEv = c != null ? c.PostExposureByElevation.Evaluate(elevationDeg) : 0f;
        return light;
    }

    private void ApplyLighting(float elevationDeg)
    {
        LightingState h = EvaluateLighting(elevationDeg);

        if (sunLight != null)
        {
            sunLight.color = h.sunColor;
            sunLight.intensity = h.sunIntensity;
        }

        if (_skyInstance != null)
        {
            _skyInstance.SetColor("_SkyTint", sessionConfig != null ? sessionConfig.SkyTintNeutral : new Color(0.5f, 0.5f, 0.5f));
            _skyInstance.SetFloat("_AtmosphereThickness", sessionConfig != null ? sessionConfig.SkyAtmosphereThickness : 1f);
            _skyInstance.SetFloat("_Exposure", h.skyExposure);
        }

        // The ambient comes from the sky (the scene's Environment source is Skybox). Changing the ambient settings and rebuilding
        // the probe (DynamicGI.UpdateEnvironment re-renders the environment cubemap) are the expensive parts, so they happen in
        // steps (every ambientUpdateInterval seconds once the sun has moved ambientUpdateMinDegrees), not every frame.
        float interval = sessionConfig != null ? sessionConfig.AmbientUpdateInterval : 1.5f;
        float minDegrees = sessionConfig != null ? sessionConfig.AmbientUpdateMinDegrees : 2f;
        bool first = float.IsNaN(_lastEnvironmentElevation);
        bool due = first || (interval > 0f && Time.unscaledTime - _lastEnvironmentTime >= interval
                             && Mathf.Abs(elevationDeg - _lastEnvironmentElevation) >= minDegrees);
        if (due)
        {
            if (RenderSettings.ambientMode != UnityEngine.Rendering.AmbientMode.Skybox)
            {
                RenderSettings.ambientMode = UnityEngine.Rendering.AmbientMode.Skybox;
            }

            RenderSettings.ambientIntensity = h.ambientIntensity;
            DynamicGI.UpdateEnvironment();
            _lastEnvironmentTime = Time.unscaledTime;
            _lastEnvironmentElevation = elevationDeg;
        }

        SetPostExposure(h.postExposureEv);
    }

    private void SetPostExposure(float ev)
    {
        if (_colorAdjustments != null && !Mathf.Approximately(ev, _lastPostExposure))
        {
            _lastPostExposure = ev;
            _colorAdjustments.postExposure.value = ev;
        }
    }
}
