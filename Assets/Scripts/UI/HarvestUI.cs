using System.Collections;
using UnityEngine;
using TMPro;

public class HarvestUI : MonoBehaviour
{
    [SerializeField] private Camera mainCamera;
    [SerializeField] private Canvas canvas;
    [SerializeField] private RectTransform floatingTextPrefab;
    [SerializeField] private TextMeshProUGUI totalScoreText;

    [SerializeField] private float fruitTextDuration = 0.7f;
    [SerializeField] private float fruitTextRise = 60f;
    [SerializeField] private float fruitTextSpread = 40f;

    private void OnEnable()
    {
        HarvestManager.OnFruitCollected += HandleFruitCollected;
        HarvestManager.OnHarvestSummary += HandleHarvestSummary;
        HarvestManager.OnHarvestComplete += HandleHarvestComplete;
    }

    private void OnDisable()
    {
        HarvestManager.OnFruitCollected -= HandleFruitCollected;
        HarvestManager.OnHarvestSummary -= HandleHarvestSummary;
        HarvestManager.OnHarvestComplete -= HandleHarvestComplete;
    }

    private void HandleFruitCollected(float amount, Vector3 worldPos)
    {
        SpawnFloatingText($"+{amount:F0}", worldPos, fruitTextDuration, fruitTextRise, 1f, true);
    }

    private void HandleHarvestSummary(float totalAmount, Vector3 worldPos)
    {
        SpawnFloatingText($"Total: {totalAmount:F0}", worldPos + Vector3.up * 1.5f, 2.5f, 100f, 1.2f, false);
    }

    private void HandleHarvestComplete(float runningTotal)
    {
        if (totalScoreText != null)
        {
            totalScoreText.text = $"Score: {runningTotal:F0}";
        }
    }

    private void SpawnFloatingText(string text, Vector3 worldPos, float duration, float risePixels, float scale, bool applySpread)
    {
        if (mainCamera == null || canvas == null || floatingTextPrefab == null)
        {
            return;
        }

        Vector3 screenPos = mainCamera.WorldToScreenPoint(worldPos);
        if (screenPos.z < 0f)
        {
            return;
        }

        if (applySpread)
        {
            screenPos.x += Random.Range(-fruitTextSpread, fruitTextSpread);
        }

        RectTransform instance = Instantiate(floatingTextPrefab, canvas.transform);
        instance.localScale = Vector3.one * scale;

        if (RectTransformUtility.ScreenPointToLocalPointInRectangle(
                canvas.transform as RectTransform,
                screenPos,
                canvas.renderMode == RenderMode.ScreenSpaceOverlay ? null : mainCamera,
                out Vector2 localPos))
        {
            instance.anchoredPosition = localPos;
        }

        TextMeshProUGUI tmp = instance.GetComponentInChildren<TextMeshProUGUI>();
        if (tmp != null)
        {
            tmp.text = text;
        }

        StartCoroutine(FadeAndRise(instance, duration, risePixels));
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

