using System;
using UnityEngine;

public enum FactorKind { Sigmoid, Gaussian }
public enum FactorCombine { Product, Mean }

// One feature's factor of a RewardFactors term, a function of x in 0..1. Sigmoid: sigmoid(scale * (x - center)) divided by its value at x = 1, so it is 1 at the paying end
// (`inverted`: x is replaced by 1 - x first, the low end pays); `scale` is the steepness per unit of the feature (about 4 is nearly linear over 0..1, 30 nearly a step).
// Gaussian: exp(-(x - center)^2 / (2 * scale^2)), `scale` the spread. Mirrored by factor_value in scripts/world.py.
[Serializable]
public class RewardFactor
{
    [SerializeField] private FactorKind kind = FactorKind.Sigmoid;
    [SerializeField] private float center = 0.5f;
    [Tooltip("Sigmoid: steepness per unit of the feature. Gaussian: spread.")]
    [SerializeField] private float scale = 10f;
    [Tooltip("Sigmoid only: the low end of the feature pays.")]
    [SerializeField] private bool inverted;

    public FactorKind Kind => kind;
    public float Center => center;
    public float Scale => scale;
    public bool Inverted => inverted;

    public float Evaluate(float x)
    {
        x = Mathf.Clamp01(x);
        if (kind == FactorKind.Gaussian)
        {
            float sigma = Mathf.Max(scale, 0.0001f);
            float d = x - center;
            return Mathf.Exp(-(d * d) / (2f * sigma * sigma));
        }
        if (inverted)
        {
            x = 1f - x;
        }
        return Sigmoid(scale * (x - center)) / Sigmoid(scale * (1f - center));
    }

    private static float Sigmoid(float z) => 1f / (1f + Mathf.Exp(-z));
}

// A term over (shape, color) made of one factor per feature: height * f_shape * f_color (Product: both must be high, a conjunction) or height * (f_shape + f_color) / 2
// (Mean: each feature adds its own part, a separable rule with the same factors). Added to the reward function's other terms; mirrored by bush_value in scripts/world.py.
[Serializable]
public class RewardFactors
{
    [SerializeField] private FactorCombine combine = FactorCombine.Product;
    [SerializeField] private RewardFactor shapeFactor = new RewardFactor();
    [SerializeField] private RewardFactor colorFactor = new RewardFactor();
    [SerializeField] private float height = 1f;

    public FactorCombine Combine => combine;
    public RewardFactor ShapeFactor => shapeFactor;
    public RewardFactor ColorFactor => colorFactor;
    public float Height => height;

    public float Evaluate(float shape, float color)
    {
        float s = shapeFactor.Evaluate(shape);
        float c = colorFactor.Evaluate(color);
        return height * (combine == FactorCombine.Product ? s * c : 0.5f * (s + c));
    }
}
