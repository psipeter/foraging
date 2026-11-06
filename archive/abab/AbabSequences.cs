using System.Collections.Generic;
using UnityEngine;

// The two ordered session lists of the ABAB design (start variant A and B: practice, its Interlude, S1, its Interlude, ...). Loaded by GameManager from
// Resources/AbabSequences, and generated with the variant session assets by scripts/build_sessions.py --wire; none of them is committed (the default design is).
// With no such asset the ABAB designs are unavailable and GameManager plays its default list.
[CreateAssetMenu(fileName = "AbabSequences", menuName = "Foraging/ABAB Sequences")]
public class AbabSequences : ScriptableObject
{
    [SerializeField] private List<SessionConfig> sequenceA = new List<SessionConfig>();
    [SerializeField] private List<SessionConfig> sequenceB = new List<SessionConfig>();

    public List<SessionConfig> SequenceA => sequenceA;
    public List<SessionConfig> SequenceB => sequenceB;
}
