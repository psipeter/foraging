using System;
using UnityEngine;

[Serializable]
public class RewardFunction
{
    [SerializeField] private RewardComponent shapeComponent = new RewardComponent();
    [SerializeField] private RewardComponent colorComponent = new RewardComponent();
    [SerializeField] private RewardComponent moistureComponent = new RewardComponent();
    [Tooltip("Gaussian bumps over (shape, color), added to the per-feature terms (an interaction no sum of one-feature terms can make).")]
    [SerializeField] private RewardBump[] bumps = new RewardBump[0];
    [Tooltip("Product terms over (shape, color): one feature linear times a Gaussian of the other, added to the other terms.")]
    [SerializeField] private RewardProduct[] products = new RewardProduct[0];

    public RewardComponent ShapeComponent => shapeComponent;
    public RewardComponent ColorComponent => colorComponent;
    public RewardComponent MoistureComponent => moistureComponent;
    public RewardBump[] Bumps => bumps;
    public RewardProduct[] Products => products;

    public float Evaluate(TreeAttributes attributes)
    {
        float reward =
            shapeComponent.Evaluate(attributes.shape) +
            colorComponent.Evaluate(attributes.color) +
            moistureComponent.Evaluate(attributes.moisture);

        foreach (RewardBump bump in bumps)
        {
            reward += bump.Evaluate(attributes.shape, attributes.color);
        }

        foreach (RewardProduct product in products)
        {
            reward += product.Evaluate(attributes.shape, attributes.color);
        }

        return reward;
    }
}
