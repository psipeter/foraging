using System.Collections.Generic;
using UnityEngine;

// Every experiment this build can play, in menu order when there is no server to order them (Resources/ExperimentCatalog.asset). The menu shows the
// experiments the server offers, with the participant's standing in each; the catalog maps their codes to the assets that hold the sessions.
[CreateAssetMenu(fileName = "ExperimentCatalog", menuName = "Foraging/Experiment catalog", order = 1)]
public class ExperimentCatalog : ScriptableObject
{
    private const string ResourceName = "ExperimentCatalog";

    [SerializeField] private List<ExperimentConfig> experiments = new List<ExperimentConfig>();

    public IReadOnlyList<ExperimentConfig> Experiments => experiments;

    public ExperimentConfig Find(string code)
    {
        foreach (ExperimentConfig experiment in experiments)
        {
            if (experiment != null && experiment.Code == code)
            {
                return experiment;
            }
        }

        return null;
    }

    public static ExperimentCatalog Load() => Resources.Load<ExperimentCatalog>(ResourceName);
}
