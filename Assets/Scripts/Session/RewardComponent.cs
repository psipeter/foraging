using System;
using UnityEngine;

[Serializable]
public class RewardComponent
{
    [SerializeField] private BasisFunctionType basisFunctionType = BasisFunctionType.Linear;
    [SerializeField] private float weight = 1f;
    [SerializeField] private float peak = 0.5f;
    [SerializeField] private float width = 0.25f;

    public string TypeName => basisFunctionType.ToString();
    public float Weight => weight;
    public float Peak => peak;
    public float Width => width;

    public float Evaluate(float attributeValue)
    {
        float normalizedValue = Mathf.Clamp01(attributeValue);
        float basisValue;

        switch (basisFunctionType)
        {
            case BasisFunctionType.Linear:
                basisValue = normalizedValue;
                break;
            case BasisFunctionType.InvertedLinear:
                basisValue = 1f - normalizedValue;
                break;
            case BasisFunctionType.GaussianPeak:
                basisValue = EvaluateGaussian(normalizedValue);
                break;
            case BasisFunctionType.InvertedGaussian:
                basisValue = 1f - EvaluateGaussian(normalizedValue);
                break;
            case BasisFunctionType.Constant:
                basisValue = 1f;
                break;
            default:
                basisValue = normalizedValue;
                break;
        }

        return basisValue * weight;
    }

    private float EvaluateGaussian(float value)
    {
        float sigma = Mathf.Max(width, 0.0001f);
        float distance = value - peak;
        float exponent = -(distance * distance) / (2f * sigma * sigma);
        return Mathf.Exp(exponent);
    }
}
