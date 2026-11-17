using System;
using UnityEngine;

// The reward function is a value map over (shape, color): the sum of its Gaussian bumps (one placeable, stretchable, rotatable primitive; scripts/value_maps.py is the
// specification, scripts/world.py the generator that pre-draws every fruit's pay from it). Moisture never pays.
[Serializable]
public class RewardFunction
{
    [Tooltip("Gaussian bumps over (shape, color), summed.")]
    [SerializeField] private RewardBump[] bumps = new RewardBump[0];

    public RewardBump[] Bumps => bumps;

    public float Evaluate(TreeAttributes attributes)
    {
        float reward = 0f;
        foreach (RewardBump bump in bumps)
        {
            reward += bump.Evaluate(attributes.shape, attributes.color);
        }

        return reward;
    }
}
