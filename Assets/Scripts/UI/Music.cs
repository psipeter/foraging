using UnityEngine;

// The study's music (Resources/Audio: synthesized, no licence): a slow pad loop under the menus and, at the start of each score screen (a session's or an
// Interlude's, and the experiment's completion screen), a short soft arpeggio followed by a quieter pad loop. It never plays during a session (the
// ambient sound is the only sound there) and never depends on anything the participant does. Fades in and out; created on first use and kept across scene loads.
public class Music : MonoBehaviour
{
    private enum Mode { None, Menu, Score }

    // The loudness of the music, 0 to 1 (SessionConfig.musicVolume sets it at each session; the menus use the last value, 0.3 at first).
    public static float Volume = 0.3f;

    private const float FadeSeconds = 1.5f;
    private static Music _instance;
    private AudioSource _loop;
    private AudioSource _cue;
    private AudioClip _menu, _scoreLoop, _scoreCue;
    private Mode _mode = Mode.None;
    private float _level;          // the loop's volume as a share of Volume, moving toward `_target`
    private float _target;

    [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.SubsystemRegistration)]
    private static void Reset()
    {
        _instance = null;
        Volume = 0.3f;
    }

    private static Music Instance
    {
        get
        {
            if (_instance == null)
            {
                var go = new GameObject("Music");
                DontDestroyOnLoad(go);
                _instance = go.AddComponent<Music>();
                _instance.Load();
            }

            return _instance;
        }
    }

    public static void PlayMenu() => Instance.Set(Mode.Menu);

    // The cue (an arpeggio) and then the score loop; a second call during the same screen does nothing.
    public static void PlayScore() => Instance.Set(Mode.Score);

    public static void Stop() => Instance.Set(Mode.None);

    private void Load()
    {
        _loop = gameObject.AddComponent<AudioSource>();
        _loop.loop = true;
        _loop.playOnAwake = false;
        _loop.volume = 0f;
        _cue = gameObject.AddComponent<AudioSource>();
        _cue.playOnAwake = false;
        _menu = Resources.Load<AudioClip>("Audio/menu_loop");
        _scoreLoop = Resources.Load<AudioClip>("Audio/score_loop");
        _scoreCue = Resources.Load<AudioClip>("Audio/score_cue");
    }

    private void Set(Mode mode)
    {
        if (mode == _mode)
        {
            return;
        }

        _mode = mode;
        _target = mode == Mode.None ? 0f : 1f;
        if (mode == Mode.None)
        {
            return;                                                       // the loop fades out and stops in Update
        }

        _loop.clip = mode == Mode.Menu ? _menu : _scoreLoop;
        _level = 0f;
        _loop.volume = 0f;
        if (_loop.clip != null)
        {
            _loop.Play();
        }

        if (mode == Mode.Score && _scoreCue != null)
        {
            _cue.volume = Volume;
            _cue.PlayOneShot(_scoreCue);
        }
    }

    private void Update()
    {
        _level = Mathf.MoveTowards(_level, _target, Time.unscaledDeltaTime / FadeSeconds);
        _loop.volume = _level * Volume * (_mode == Mode.Score ? 0.7f : 1f);
        if (_mode == Mode.None && _level <= 0f && _loop.isPlaying)
        {
            _loop.Stop();
        }
    }
}
