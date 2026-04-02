using System;
using UnityEngine;

public class HarvestManager : MonoBehaviour
{
    public SessionConfig sessionConfig;
    [SerializeField] private PlayerController playerController;
    [SerializeField] private SunController sunController;

    private bool _isHarvesting;
    private float _harvestTimer;
    private Tree _currentTree;
    private float _runningTotal;
    private int _fruitsCollected;
    private float _totalHarvestReward;

    public static event Action<float> OnHarvestComplete;
    public static event Action<float, Vector3> OnFruitCollected;
    public static event Action<float, Vector3> OnHarvestSummary;

    public bool IsHarvesting => _isHarvesting;

    private void OnEnable()
    {
        SunController.OnSessionEnd += HandleSessionEnd;
    }

    private void OnDisable()
    {
        SunController.OnSessionEnd -= HandleSessionEnd;
    }

    public void StartHarvest(Tree tree)
    {
        if (sunController != null && sunController.SessionComplete)
        {
            return;
        }

        if (_isHarvesting || tree == null || tree.isHarvested)
        {
            return;
        }

        _currentTree = tree;
        _isHarvesting = true;
        _harvestTimer = 0f;
        _fruitsCollected = 0;
        _totalHarvestReward = 0f;

        if (playerController != null)
        {
            playerController.SetFrozen(true);
            playerController.SetHarvestAnimationSpeed(sessionConfig.FruitHarvestDuration * tree.FruitCount);
        }
    }

    private void Update()
    {
        if (!_isHarvesting || _currentTree == null || sessionConfig == null)
        {
            return;
        }

        _harvestTimer += Time.deltaTime;

        int fruitCount = Mathf.Max(1, _currentTree.FruitCount);
        float duration = Mathf.Max(sessionConfig.FruitHarvestDuration * fruitCount, 0.0001f);
        float normalized = Mathf.Clamp01(_harvestTimer / duration);

        int targetFruits = Mathf.FloorToInt(normalized * _currentTree.FruitCount);
        targetFruits = Mathf.Min(targetFruits, _currentTree.FruitCount);

        for (int i = _fruitsCollected; i < targetFruits; i++)
        {
            float bushReward = _currentTree.Evaluate(sessionConfig.RewardFunction);
            float noise = GaussianNoise() * sessionConfig.RewardStd;
            float fruitReward = Mathf.Max(0f,
                Mathf.RoundToInt(bushReward + noise));

            _currentTree.HideFruit(i);

            Vector3 worldPos = _currentTree.GetFruitWorldPosition(i);
            OnFruitCollected?.Invoke(fruitReward, worldPos);

            _totalHarvestReward += fruitReward;
            _fruitsCollected++;
        }

        if (_harvestTimer >= duration)
        {
            CompleteHarvest();
        }
    }

    private void CompleteHarvest()
    {
        if (_currentTree != null)
        {
            _currentTree.isHarvested = true;
            _currentTree.SetHarvested(true);

            _runningTotal += _totalHarvestReward;

            Vector3 worldPos = _currentTree.GetWorldCenter();
            OnHarvestSummary?.Invoke(_totalHarvestReward, worldPos);
            OnHarvestComplete?.Invoke(_runningTotal);
        }

        if (playerController != null)
        {
            playerController.SetFrozen(false);
            playerController.ResetAnimationSpeed();
            playerController.ClearTarget();
        }

        _isHarvesting = false;
        _currentTree = null;
    }

    private void HandleSessionEnd()
    {
        if (_isHarvesting)
        {
            CompleteHarvest();
        }

        _isHarvesting = false;
        _currentTree = null;
    }

    private float GaussianNoise()
    {
        float u1 = 1f - UnityEngine.Random.value;
        float u2 = 1f - UnityEngine.Random.value;
        return Mathf.Sqrt(-2f * Mathf.Log(u1)) * Mathf.Sin(2f * Mathf.PI * u2);
    }
}

