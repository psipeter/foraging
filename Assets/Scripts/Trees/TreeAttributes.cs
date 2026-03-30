using System;
using UnityEngine;

[Serializable]
public struct TreeAttributes
{
    /// <summary>0 = squat/wide, 1 = tall/narrow.</summary>
    [Range(0f, 1f)] public float shape;
    /// <summary>Abstract 0–1, mapped to visible color on fruits.</summary>
    [Range(0f, 1f)] public float color;
    /// <summary>0 = arid, 1 = swampy (from terrain moisture).</summary>
    [Range(0f, 1f)] public float moisture;
}
