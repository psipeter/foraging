using System.Collections;
using UnityEngine;
using TMPro;

public class HarvestUI : MonoBehaviour
{
    public SessionConfig sessionConfig;

    [SerializeField] private Canvas canvas;
    [SerializeField] private RectTransform floatingTextPrefab;
    [SerializeField] private TextMeshProUGUI totalScoreText;
    [SerializeField] private TextMeshProUGUI hintText;

    [SerializeField] private float fruitTextDuration = 0.8f;
    [SerializeField] private float fruitTextRise = 80f;
    [Tooltip("Where +X popups appear, in canvas pixels from screen center. Fixed so a reward is always readable regardless of where the bush is on screen.")]
    [SerializeField] private Vector2 popupOffset = new Vector2(0f, 90f);
    [SerializeField] private float scorePunchScale = 1.3f;
    [SerializeField] private float scorePunchDuration = 0.2f;

    [Header("Score display")]
    [SerializeField] private float scoreFontSize = 36f;
    [SerializeField] private Vector2 scorePosition = new Vector2(-150f, -44f);
    [SerializeField] private Vector2 scorePlateSize = new Vector2(250f, 60f);
    [SerializeField] private Color plateColor = new Color(0f, 0f, 0f, 0.38f);
    [Tooltip("Seconds for the displayed score to count up to the new total.")]
    [SerializeField] private float scoreCountUpSeconds = 0.2f;
    [SerializeField] private float scoreFlashSeconds = 0.4f;

    private Coroutine _punch;
    private float _scoreTarget;
    private float _scoreShown;
    private float _flash;

    private void OnEnable()
    {
        HarvestManager.OnFruitCollected += HandleFruitCollected;
        HarvestManager.OnScoreChanged += HandleScoreChanged;
        HarvestManager.OnHintChanged += HandleHintChanged;
    }

    private void OnDisable()
    {
        HarvestManager.OnFruitCollected -= HandleFruitCollected;
        HarvestManager.OnScoreChanged -= HandleScoreChanged;
        HarvestManager.OnHintChanged -= HandleHintChanged;
    }

    private void Start()
    {
        if (hintText != null)
        {
            hintText.gameObject.SetActive(false);
        }

        if (totalScoreText != null)
        {
            RectTransform rect = totalScoreText.rectTransform;
            rect.anchoredPosition = scorePosition;
            rect.sizeDelta = scorePlateSize - new Vector2(20f, 10f);
            totalScoreText.fontSize = scoreFontSize;
            totalScoreText.fontStyle = FontStyles.Bold;
            totalScoreText.alignment = TextAlignmentOptions.Center;
            HudWidgets.CreatePlate(rect, scorePlateSize, plateColor, "ScorePlate");
            ShowScore();
        }
    }

    private void Update()
    {
        if (totalScoreText == null)
        {
            return;
        }

        if (!Mathf.Approximately(_scoreShown, _scoreTarget))
        {
            float speed = Mathf.Max(8f, Mathf.Abs(_scoreTarget - _scoreShown) / Mathf.Max(scoreCountUpSeconds, 0.01f));
            _scoreShown = Mathf.MoveTowards(_scoreShown, _scoreTarget, speed * Time.unscaledDeltaTime);
            ShowScore();
        }

        if (_flash > 0f)
        {
            _flash = Mathf.Max(0f, _flash - Time.unscaledDeltaTime / Mathf.Max(scoreFlashSeconds, 0.01f));
            Color flash = sessionConfig != null ? sessionConfig.PopupColor : Color.white;
            totalScoreText.color = Color.Lerp(Color.white, flash, _flash);
        }
    }

    private void ShowScore()
    {
        totalScoreText.text = $"Score: {Mathf.RoundToInt(_scoreShown)}";
    }

    private void HandleFruitCollected(float amount, Vector3 worldPos)
    {
        if (canvas == null || floatingTextPrefab == null)
        {
            return;
        }

        float max = sessionConfig != null ? Mathf.Max(sessionConfig.RewardFeedbackMax, 0.0001f) : 6f;
        float scaling = sessionConfig != null ? sessionConfig.RewardSizeScaling : 0f;
        float baseScale = sessionConfig != null ? sessionConfig.PopupScale : 1.7f;
        float extraScale = sessionConfig != null ? sessionConfig.PopupExtraScale : 0f;
        Color popupColor = sessionConfig != null ? sessionConfig.PopupColor : Color.white;

        // Size and brightness follow the reward (scaled by rewardSizeScaling); hue never does.
        float t = Mathf.Clamp01(amount / max);
        float sizeMultiplier = baseScale * (1f + extraScale * scaling * t);
        float brightness = Mathf.Lerp(1f, Mathf.Lerp(0.55f, 1f, t), scaling);
        Color color = popupColor * brightness;
        color.a = 1f;

        RectTransform instance = Instantiate(floatingTextPrefab, canvas.transform);
        instance.anchorMin = instance.anchorMax = new Vector2(0.5f, 0.5f);
        instance.pivot = new Vector2(0.5f, 0.5f);
        instance.localScale = Vector3.one;
        instance.anchoredPosition = popupOffset;

        TextMeshProUGUI tmp = instance.GetComponentInChildren<TextMeshProUGUI>();
        if (tmp != null)
        {
            tmp.text = $"+{amount:F0}";
            tmp.fontStyle = FontStyles.Bold;
            tmp.color = color;
            tmp.outlineWidth = 0.22f;
            tmp.outlineColor = new Color32(0, 0, 0, 215);
        }

        StartCoroutine(AnimatePopup(instance, sizeMultiplier, fruitTextDuration, fruitTextRise));
    }

    private void HandleScoreChanged(float runningTotal)
    {
        _scoreTarget = runningTotal;
        _flash = 1f;

        if (totalScoreText == null)
        {
            return;
        }

        if (_punch != null)
        {
            StopCoroutine(_punch);
        }

        _punch = StartCoroutine(PunchScore());
    }

    private void HandleHintChanged(HarvestHint hint)
    {
        if (hintText == null)
        {
            return;
        }

        switch (hint)
        {
            case HarvestHint.Available:
                hintText.text = "Hold SPACE to harvest";
                hintText.gameObject.SetActive(true);
                break;
            case HarvestHint.Paused:
                hintText.text = "Look toward the bush to keep harvesting";
                hintText.gameObject.SetActive(true);
                break;
            default:
                hintText.gameObject.SetActive(false);
                break;
        }
    }

    private IEnumerator PunchScore()
    {
        RectTransform rect = totalScoreText.rectTransform;
        float elapsed = 0f;
        while (elapsed < scorePunchDuration)
        {
            elapsed += Time.deltaTime;
            float t = Mathf.Clamp01(elapsed / scorePunchDuration);
            rect.localScale = Vector3.one * Mathf.Lerp(scorePunchScale, 1f, t);
            yield return null;
        }

        rect.localScale = Vector3.one;
        _punch = null;
    }

    private static float EaseOutBack(float x)
    {
        const float c1 = 1.70158f;
        const float c3 = c1 + 1f;
        float u = x - 1f;
        return 1f + c3 * u * u * u + c1 * u * u;
    }

    // Pop in with an overshoot and a small wobble while rising, linger, then fade out. The whole popup (text and
    // outline) fades through a CanvasGroup.
    private IEnumerator AnimatePopup(RectTransform rect, float sizeMultiplier, float duration, float risePixels)
    {
        var group = rect.gameObject.AddComponent<CanvasGroup>();
        group.alpha = 0f;
        float elapsed = 0f;
        Vector2 startPos = rect.anchoredPosition;
        Vector2 risePos = startPos + Vector2.up * risePixels;
        duration = Mathf.Max(duration, 0.0001f);

        while (elapsed < duration)
        {
            elapsed += Time.deltaTime;
            float t = Mathf.Clamp01(elapsed / duration);

            float rise = Mathf.Clamp01(t / 0.3f);
            rect.anchoredPosition = Vector2.Lerp(startPos, risePos, 1f - (1f - rise) * (1f - rise));

            float pop = Mathf.Clamp01(t / 0.2f);
            rect.localScale = Vector3.one * sizeMultiplier * Mathf.LerpUnclamped(0.4f, 1f, EaseOutBack(pop));
            float wobble = Mathf.Sin(t * 40f) * 6f * (1f - Mathf.Clamp01(t / 0.45f));
            rect.localRotation = Quaternion.Euler(0f, 0f, wobble);

            group.alpha = t < 0.7f ? Mathf.Clamp01(t / 0.1f) : 1f - (t - 0.7f) / 0.3f;
            yield return null;
        }

        Destroy(rect.gameObject);
    }
}
