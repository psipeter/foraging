using System;
using UnityEngine;

// A Gaussian bump over (shape, color): height * exp(-((shape - centerShape)^2 / (2 * width^2) + (color - centerColor)^2 / (2 * widthColor^2))).
// `width` is the spread along shape; `widthColor` the spread along color, and 0 (the default) means the same as `width`, a round bump.
// `angle` (degrees, 0 = the axes of the plane) turns the bump about its center, so the spreads lie along the turned axes: `width` along the axis that
// is `angle` from the shape axis, `widthColor` along the one at right angles (an elongated, tilted bump no one-feature term can make).
// Added to the reward function's per-feature terms; mirrored by bush_value in scripts/world.py.
[Serializable]
public class RewardBump
{
    [SerializeField] private float centerShape = 0.5f;
    [SerializeField] private float centerColor = 0.5f;
    [SerializeField] private float width = 0.2f;
    [Tooltip("Spread along color; 0 = the same as width (a round bump).")]
    [SerializeField] private float widthColor = 0f;
    [Tooltip("Degrees the bump is turned about its center; 0 = spreads along the shape and color axes.")]
    [SerializeField] private float angle = 0f;
    [SerializeField] private float height = 1f;

    public float CenterShape => centerShape;
    public float CenterColor => centerColor;
    public float Width => width;
    public float WidthColor => widthColor;
    public float Angle => angle;
    public float Height => height;

    public float Evaluate(float shape, float color)
    {
        float sigmaShape = Mathf.Max(width, 0.0001f);
        float sigmaColor = widthColor > 0f ? Mathf.Max(widthColor, 0.0001f) : sigmaShape;
        float ds = Mathf.Clamp01(shape) - centerShape;
        float dc = Mathf.Clamp01(color) - centerColor;
        if (angle != 0f)
        {
            float cos = Mathf.Cos(angle * Mathf.Deg2Rad);
            float sin = Mathf.Sin(angle * Mathf.Deg2Rad);
            float along = ds * cos + dc * sin;
            dc = -ds * sin + dc * cos;
            ds = along;
        }
        return height * Mathf.Exp(-(ds * ds / (2f * sigmaShape * sigmaShape) + dc * dc / (2f * sigmaColor * sigmaColor)));
    }
}
