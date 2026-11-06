using System;
using UnityEngine;

// A Gaussian bump over (shape, color): height * exp(-((shape - centerShape)^2 / (2 * width^2) + (color - centerColor)^2 / (2 * widthColor^2))).
// `width` is the spread along shape; `widthColor` the spread along color, and 0 (the default) means the same as `width`, a round bump.
// Added to the reward function's per-feature terms; mirrored by bush_value in scripts/world.py.
[Serializable]
public class RewardBump
{
    [SerializeField] private float centerShape = 0.5f;
    [SerializeField] private float centerColor = 0.5f;
    [SerializeField] private float width = 0.2f;
    [Tooltip("Spread along color; 0 = the same as width (a round bump).")]
    [SerializeField] private float widthColor = 0f;
    [SerializeField] private float height = 1f;

    public float CenterShape => centerShape;
    public float CenterColor => centerColor;
    public float Width => width;
    public float WidthColor => widthColor;
    public float Height => height;

    public float Evaluate(float shape, float color)
    {
        float sigmaShape = Mathf.Max(width, 0.0001f);
        float sigmaColor = widthColor > 0f ? Mathf.Max(widthColor, 0.0001f) : sigmaShape;
        float ds = Mathf.Clamp01(shape) - centerShape;
        float dc = Mathf.Clamp01(color) - centerColor;
        return height * Mathf.Exp(-(ds * ds / (2f * sigmaShape * sigmaShape) + dc * dc / (2f * sigmaColor * sigmaColor)));
    }
}
