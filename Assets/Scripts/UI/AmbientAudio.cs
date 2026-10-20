using UnityEngine;

// Passive ambient audio: footsteps while walking (CC0 grass recordings in Assets/Audio/Ambient/Footsteps; synthesized
// steps are the fallback when none are assigned), a quiet constant background bed of cicadas (a CC0 loop in
// Assets/Audio/Ambient/Cicadas; silent if no clip is assigned), and occasional birdsong (synthesized at startup).
// By design none of it depends on bush attributes, rewards, terrain or time of
// day, so it cannot become an extra cue about reward. It also avoids UnityEngine.Random (which seeds the reward
// noise) and uses System.Random instead.
public class AmbientAudio : MonoBehaviour
{
    public SessionConfig sessionConfig;

    [SerializeField] private PlayerController player;
    [SerializeField] private AudioClip[] footstepClips;
    [SerializeField] private AudioClip bedClip;

    private const int SampleRate = 44100;
    private const int SynthStepVariants = 4;
    private const int BirdPatterns = 3;
    private const int StepVoiceCount = 3;

    private readonly System.Random _rng = new System.Random();
    private AudioClip[] _steps;
    private readonly AudioClip[] _birds = new AudioClip[BirdPatterns];
    private AudioSource[] _stepVoices;
    private AudioSource _bedA;
    private AudioSource _bedB;
    private AudioSource _birdVoice;
    private int _nextStepVoice;
    private int _lastStep = -1;

    private Vector3 _lastPosition;
    private bool _hasLastPosition;
    private float _distanceSinceStep;
    private float _birdTimer;

    private void Awake()
    {
        _stepVoices = new AudioSource[StepVoiceCount];
        for (int i = 0; i < StepVoiceCount; i++)
        {
            _stepVoices[i] = NewVoice(false);
        }

        _bedA = NewVoice(true);
        _bedB = NewVoice(true);
        _birdVoice = NewVoice(false);

        if (footstepClips != null && footstepClips.Length > 0)
        {
            _steps = footstepClips;
        }
        else
        {
            BuildSteps();
        }

        BuildBirds();
        _bedA.clip = bedClip;
        _bedB.clip = bedClip;
    }

    private void Start()
    {
        // Two copies at slightly different pitch and start point, so the short loop does not repeat audibly:
        // the combined pattern only realigns after a very long time.
        if (BedVolume > 0f && bedClip != null)
        {
            _bedA.pitch = 1f;
            _bedB.pitch = 0.965f;
            _bedA.volume = BedVolume * 0.7f;
            _bedB.volume = BedVolume * 0.7f;
            _bedA.Play();
            _bedB.time = bedClip.length * 0.5f;
            _bedB.Play();
        }

        _distanceSinceStep = Stride * 0.5f;
        _birdTimer = Range(2f, 6f);
    }

    private float Stride => sessionConfig != null ? Mathf.Max(0.5f, sessionConfig.FootstepStride) : 3.6f;
    private float StepVolume => sessionConfig != null ? sessionConfig.FootstepVolume : 0.06f;
    private float BedVolume => sessionConfig != null ? sessionConfig.BedVolume : 0.0165f;
    private float BirdVolume => sessionConfig != null ? sessionConfig.BirdVolume : 0.03f;

    private void Update()
    {
        UpdateFootsteps();
        UpdateBirds();
    }

    // A step every `stride` world units actually walked, so steps stop when walking is blocked, locked for
    // harvesting, or the session has ended.
    private void UpdateFootsteps()
    {
        if (player == null || _steps == null || _steps.Length == 0 || StepVolume <= 0f)
        {
            return;
        }

        Vector3 pos = player.transform.position;
        float dt = Time.deltaTime;
        if (!_hasLastPosition)
        {
            _lastPosition = pos;
            _hasLastPosition = true;
            return;
        }

        float moved = new Vector2(pos.x - _lastPosition.x, pos.z - _lastPosition.z).magnitude;
        _lastPosition = pos;
        if (dt <= 0f || player.IsFrozen || moved / dt > player.moveSpeed * 2f)
        {
            return;
        }

        _distanceSinceStep += moved;
        if (_distanceSinceStep < Stride)
        {
            return;
        }

        _distanceSinceStep -= Stride;
        PlayStep();
    }

    private void PlayStep()
    {
        int variant = _rng.Next(_steps.Length);
        if (variant == _lastStep && _steps.Length > 1)
        {
            variant = (variant + 1) % _steps.Length;
        }

        _lastStep = variant;

        AudioSource voice = _stepVoices[_nextStepVoice];
        _nextStepVoice = (_nextStepVoice + 1) % StepVoiceCount;
        voice.clip = _steps[variant];
        voice.pitch = Range(0.92f, 1.08f);
        voice.volume = StepVolume * Range(0.8f, 1f);
        voice.panStereo = (_nextStepVoice == 0 ? 1f : -1f) * 0.08f;
        voice.Play();
    }

    private void UpdateBirds()
    {
        if (BirdVolume <= 0f)
        {
            return;
        }

        _birdTimer -= Time.unscaledDeltaTime;
        if (_birdTimer > 0f)
        {
            return;
        }

        float lo = sessionConfig != null ? sessionConfig.BirdIntervalMin : 5f;
        float hi = sessionConfig != null ? sessionConfig.BirdIntervalMax : 14f;
        _birdTimer = Range(Mathf.Min(lo, hi), Mathf.Max(lo, hi));

        _birdVoice.clip = _birds[_rng.Next(BirdPatterns)];
        _birdVoice.pitch = Range(0.85f, 1.2f);
        _birdVoice.volume = BirdVolume * Range(0.6f, 1f);
        _birdVoice.panStereo = Range(-0.8f, 0.8f);
        _birdVoice.Play();
    }

    private AudioSource NewVoice(bool loop)
    {
        AudioSource voice = gameObject.AddComponent<AudioSource>();
        voice.playOnAwake = false;
        voice.loop = loop;
        voice.spatialBlend = 0f;
        return voice;
    }

    private float Range(float lo, float hi)
    {
        return lo + (float)_rng.NextDouble() * (hi - lo);
    }

    private float Noise()
    {
        return (float)(_rng.NextDouble() * 2.0 - 1.0);
    }

    // Footstep: lowpassed noise (a soft crunch) plus a short low thump, fast exponential decay. Each variant uses
    // a different brightness and noise.
    private void BuildSteps()
    {
        _steps = new AudioClip[SynthStepVariants];
        for (int v = 0; v < SynthStepVariants; v++)
        {
            float seconds = 0.2f;
            int count = Mathf.CeilToInt(seconds * SampleRate);
            var data = new float[count];
            float a = 0.10f + 0.05f * v;           // one-pole lowpass coefficient: brightness
            float thumpHz = 70f + 12f * v;
            float y = 0f;
            for (int i = 0; i < count; i++)
            {
                float t = i / (float)SampleRate;
                y += a * (Noise() - y);
                float crunch = y * Mathf.Exp(-t * 38f);
                float thump = Mathf.Sin(2f * Mathf.PI * thumpHz * t) * Mathf.Exp(-t * 30f);
                data[i] = (1.6f * crunch + 0.55f * thump) * Mathf.Clamp01(t / 0.004f);
            }

            _steps[v] = MakeClip("Step" + v, data, false);
        }
    }

    // Birds: three short whistle patterns built from frequency-swept notes with a smooth envelope.
    private void BuildBirds()
    {
        // Pattern 0: three rising whistles.
        _birds[0] = MakeBird("BirdRise", 0.65f, new[]
        {
            new Note(0.00f, 0.10f, 2600f, 3500f), new Note(0.16f, 0.10f, 2700f, 3600f), new Note(0.32f, 0.14f, 2800f, 3900f)
        });
        // Pattern 1: a fast trill.
        var trill = new Note[9];
        for (int i = 0; i < trill.Length; i++)
        {
            trill[i] = new Note(i * 0.055f, 0.035f, 3300f + 60f * (i % 3), 3800f + 60f * (i % 3));
        }

        _birds[1] = MakeBird("BirdTrill", 0.6f, trill);
        // Pattern 2: two falling notes.
        _birds[2] = MakeBird("BirdFall", 0.5f, new[]
        {
            new Note(0.00f, 0.14f, 4200f, 2900f), new Note(0.22f, 0.16f, 3800f, 2600f)
        });
    }

    private readonly struct Note
    {
        public readonly float Start, Duration, FreqStart, FreqEnd;

        public Note(float start, float duration, float freqStart, float freqEnd)
        {
            Start = start;
            Duration = duration;
            FreqStart = freqStart;
            FreqEnd = freqEnd;
        }
    }

    private static AudioClip MakeBird(string name, float seconds, Note[] notes)
    {
        int count = Mathf.CeilToInt(seconds * SampleRate);
        var data = new float[count];
        foreach (Note note in notes)
        {
            int first = Mathf.FloorToInt(note.Start * SampleRate);
            int len = Mathf.CeilToInt(note.Duration * SampleRate);
            float phase = 0f;
            for (int i = 0; i < len && first + i < count; i++)
            {
                float u = i / (float)len;
                float freq = Mathf.Lerp(note.FreqStart, note.FreqEnd, u);
                phase += 2f * Mathf.PI * freq / SampleRate;
                float env = Mathf.Sin(Mathf.PI * u);
                env *= env;
                data[first + i] += (Mathf.Sin(phase) + 0.25f * Mathf.Sin(2f * phase)) * env;
            }
        }

        return MakeClip(name, data, false);
    }

    // Normalizes to a safe peak and wraps the samples in a mono clip.
    private static AudioClip MakeClip(string name, float[] data, bool loop)
    {
        float peak = 0.0001f;
        for (int i = 0; i < data.Length; i++)
        {
            peak = Mathf.Max(peak, Mathf.Abs(data[i]));
        }

        for (int i = 0; i < data.Length; i++)
        {
            data[i] *= 0.7f / peak;
        }

        AudioClip clip = AudioClip.Create(name, data.Length, 1, SampleRate, false);
        clip.SetData(data, 0);
        return clip;
    }
}
