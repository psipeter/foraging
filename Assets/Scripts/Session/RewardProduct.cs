using System;
using UnityEngine;

// A product term over (shape, color): one feature enters linearly and the other through a Gaussian, so the reward of the one depends on the value of the
// other (an interaction no sum of one-feature terms can make): height * f(linear feature) * exp(-(g - center)^2 / (2 * width^2)), with f(x) = x, or
// 1 - x when linearInverted. Added to the reward function's other terms; mirrored by bush_value in scripts/world.py.
[Serializable]
public class RewardProduct
{
    [Tooltip("True: linear in shape and Gaussian in color. False: linear in color and Gaussian in shape.")]
    [SerializeField] private bool linearInShape = true;
    [Tooltip("The linear factor is 1 - x instead of x.")]
    [SerializeField] private bool linearInverted;
    [Tooltip("Center and spread of the Gaussian factor, on the other feature (0..1).")]
    [SerializeField] private float center = 0.5f;
    [SerializeField] private float width = 0.25f;
    [SerializeField] private float height = 1f;

    public bool LinearInShape => linearInShape;
    public bool LinearInverted => linearInverted;
    public float Center => center;
    public float Width => width;
    public float Height => height;

    public float Evaluate(float shape, float color)
    {
        float linear = Mathf.Clamp01(linearInShape ? shape : color);
        if (linearInverted)
        {
            linear = 1f - linear;
        }

        float sigma = Mathf.Max(width, 0.0001f);
        float d = Mathf.Clamp01(linearInShape ? color : shape) - center;
        return height * linear * Mathf.Exp(-(d * d) / (2f * sigma * sigma));
    }
}
