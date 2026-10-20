using System.Collections.Generic;
using UnityEngine;

// Short feedback sounds, synthesized at startup (no audio assets). Add a cue by adding a value to Cue, a
// synthesizer for it in BuildClips, and a call to Play from whatever event should trigger it.
public class FeedbackAudio : MonoBehaviour
{
    public enum Cue
    {
        FruitPick,
        BushExhausted
    }

    public SessionConfig sessionConfig;

    private const int SampleRate = 44100;
    private const int VoiceCount = 4;

    private readonly Dictionary<Cue, AudioClip> _clips = new Dictionary<Cue, AudioClip>();
    private AudioSource[] _voices;
    private int _nextVoice;

    private void Awake()
    {
        _voices = new AudioSource[VoiceCount];
        for (int i = 0; i < VoiceCount; i++)
        {
            AudioSource voice = gameObject.AddComponent<AudioSource>();
            voice.playOnAwake = false;
            voice.spatialBlend = 0f;
            _voices[i] = voice;
        }

        BuildClips();
    }

    private void OnEnable()
    {
        HarvestManager.OnFruitCollected += HandleFruitCollected;
        HarvestManager.OnBushExhausted += HandleBushExhausted;
    }

    private void OnDisable()
    {
        HarvestManager.OnFruitCollected -= HandleFruitCollected;
        HarvestManager.OnBushExhausted -= HandleBushExhausted;
    }

    private void HandleFruitCollected(float amount, Vector3 worldPos)
    {
        float max = sessionConfig != null ? Mathf.Max(sessionConfig.RewardFeedbackMax, 0.0001f) : 6f;
        float semitones = sessionConfig != null ? sessionConfig.PitchSemitoneRange : 0f;
        float t = Mathf.Clamp01(amount / max);
        Play(Cue.FruitPick, Mathf.Pow(2f, semitones * t / 12f));
    }

    private void HandleBushExhausted()
    {
        Play(Cue.BushExhausted, 1f);
    }

    public void Play(Cue cue, float pitch)
    {
        if (!_clips.TryGetValue(cue, out AudioClip clip))
        {
            return;
        }

        AudioSource voice = _voices[_nextVoice];
        _nextVoice = (_nextVoice + 1) % VoiceCount;
        voice.pitch = pitch;
        voice.volume = sessionConfig != null ? sessionConfig.SfxVolume : 0.5f;
        voice.clip = clip;
        voice.Play();
    }

    private void BuildClips()
    {
        // Pick: a short bright blip (fundamental + soft harmonics, fast exponential decay).
        _clips[Cue.FruitPick] = Synthesize("FruitPick", 0.16f, (t) =>
            (Mathf.Sin(2f * Mathf.PI * 660f * t)
             + 0.35f * Mathf.Sin(2f * Mathf.PI * 1320f * t)
             + 0.12f * Mathf.Sin(2f * Mathf.PI * 1980f * t)) * Mathf.Exp(-t * 24f));

        // Exhausted: two soft rising chime notes.
        _clips[Cue.BushExhausted] = Synthesize("BushExhausted", 0.55f, (t) =>
        {
            float a = Mathf.Sin(2f * Mathf.PI * 659.3f * t) * Mathf.Exp(-t * 9f);
            float t2 = t - 0.09f;
            float b = t2 > 0f ? Mathf.Sin(2f * Mathf.PI * 987.8f * t2) * Mathf.Exp(-t2 * 9f) : 0f;
            return a + 0.9f * b;
        });
    }

    // Renders wave(t) for `seconds`, with a 4 ms attack to avoid clicks, normalized to a safe peak.
    private static AudioClip Synthesize(string name, float seconds, System.Func<float, float> wave)
    {
        int count = Mathf.CeilToInt(seconds * SampleRate);
        var data = new float[count];
        float peak = 0.0001f;
        for (int i = 0; i < count; i++)
        {
            float t = i / (float)SampleRate;
            float attack = Mathf.Clamp01(t / 0.004f);
            data[i] = wave(t) * attack;
            peak = Mathf.Max(peak, Mathf.Abs(data[i]));
        }

        for (int i = 0; i < count; i++)
        {
            data[i] *= 0.7f / peak;
        }

        AudioClip clip = AudioClip.Create(name, count, 1, SampleRate, false);
        clip.SetData(data, 0);
        return clip;
    }
}
