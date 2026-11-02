using System;
using UnityEngine;

// A round Gaussian bump over (shape, color): height * exp(-((shape - centerShape)^2 + (color - centerColor)^2) / (2 * width^2)).
// Added to the reward function's per-feature terms; mirrored by bush_value in scripts/world.py.
[Serializable]
public class RewardBump
{
    [SerializeField] private float centerShape = 0.5f;
    [SerializeField] private float centerColor = 0.5f;
    [SerializeField] private float width = 0.2f;
    [SerializeField] private float height = 1f;

    public float CenterShape => centerShape;
    public float CenterColor => centerColor;
    public float Width => width;
    public float Height => height;

    public float Evaluate(float shape, float color)
    {
        float sigma = Mathf.Max(width, 0.0001f);
        float ds = Mathf.Clamp01(shape) - centerShape;
        float dc = Mathf.Clamp01(color) - centerColor;
        return height * Mathf.Exp(-(ds * ds + dc * dc) / (2f * sigma * sigma));
    }
}
