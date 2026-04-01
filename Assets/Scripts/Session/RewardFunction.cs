using System;
using UnityEngine;

[Serializable]
public class RewardFunction
{
    [SerializeField] private RewardComponent shapeComponent = new RewardComponent();
    [SerializeField] private RewardComponent colorComponent = new RewardComponent();
    [SerializeField] private RewardComponent moistureComponent = new RewardComponent();

    public RewardComponent ShapeComponent => shapeComponent;
    public RewardComponent ColorComponent => colorComponent;
    public RewardComponent MoistureComponent => moistureComponent;

    public float Evaluate(TreeAttributes attributes)
    {
        float reward =
            shapeComponent.Evaluate(attributes.shape) +
            colorComponent.Evaluate(attributes.color) +
            moistureComponent.Evaluate(attributes.moisture);

        return reward;
    }
}
