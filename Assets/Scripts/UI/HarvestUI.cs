using System.Collections;
using UnityEngine;
using TMPro;

public class HarvestUI : MonoBehaviour
{
    [SerializeField] private Canvas canvas;
    [SerializeField] private RectTransform floatingTextPrefab;
    [SerializeField] private TextMeshProUGUI totalScoreText;
    [SerializeField] private TextMeshProUGUI hintText;

    [SerializeField] private float fruitTextDuration = 0.7f;
    [SerializeField] private float fruitTextRise = 60f;
    [Tooltip("Where +X popups appear, in canvas pixels from screen center. Fixed so a reward is always readable regardless of where the bush is on screen.")]
    [SerializeField] private Vector2 popupOffset = new Vector2(0f, 90f);
    [SerializeField] private float scorePunchScale = 1.25f;
    [SerializeField] private float scorePunchDuration = 0.2f;

    private Coroutine _punch;

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
    }

    private void HandleFruitCollected(float amount, Vector3 worldPos)
    {
        if (canvas == null || floatingTextPrefab == null)
        {
            return;
        }

        RectTransform instance = Instantiate(floatingTextPrefab, canvas.transform);
        instance.anchorMin = instance.anchorMax = new Vector2(0.5f, 0.5f);
        instance.pivot = new Vector2(0.5f, 0.5f);
        instance.localScale = Vector3.one;
        instance.anchoredPosition = popupOffset;

        TextMeshProUGUI tmp = instance.GetComponentInChildren<TextMeshProUGUI>();
        if (tmp != null)
        {
            tmp.text = $"+{amount:F0}";
        }

        StartCoroutine(FadeAndRise(instance, fruitTextDuration, fruitTextRise));
    }

    private void HandleScoreChanged(float runningTotal)
    {
        if (totalScoreText == null)
        {
            return;
        }

        totalScoreText.text = $"Score: {runningTotal:F0}";
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

    private IEnumerator FadeAndRise(RectTransform rect, float duration, float risePixels)
    {
        TextMeshProUGUI tmp = rect.GetComponentInChildren<TextMeshProUGUI>();
        float elapsed = 0f;
        Vector2 startPos = rect.anchoredPosition;
        Vector2 risePos = startPos + Vector2.up * risePixels;

        while (elapsed < duration)
        {
            elapsed += Time.deltaTime;
            float t = Mathf.Clamp01(elapsed / duration);

            float phase = t;
            if (phase < 0.3f)
            {
                // Phase 1: rise in (0 → 0.3)
                float localT = phase / 0.3f;
                rect.anchoredPosition = Vector2.Lerp(startPos, risePos, localT);
                if (tmp != null)
                {
                    Color c = tmp.color;
                    c.a = Mathf.Lerp(0f, 1f, localT);
                    tmp.color = c;
                }
            }
            else if (phase < 0.7f)
            {
                // Phase 2: linger (0.3 → 0.7)
                rect.anchoredPosition = risePos;
                if (tmp != null)
                {
                    Color c = tmp.color;
                    c.a = 1f;
                    tmp.color = c;
                }
            }
            else
            {
                // Phase 3: fade out (0.7 → 1.0)
                float localT = (phase - 0.7f) / 0.3f;
                rect.anchoredPosition = risePos;
                if (tmp != null)
                {
                    Color c = tmp.color;
                    c.a = Mathf.Lerp(1f, 0f, localT);
                    tmp.color = c;
                }
            }

            yield return null;
        }

        Destroy(rect.gameObject);
    }
}
