using System;
using System.Collections.Generic;
using System.IO;
using UnityEditor;
using UnityEngine;

// Creates or updates an experiment's assets (its sessions, the ExperimentConfig and its entry in the catalog) from a spec that
// scripts/build_experiment.py writes from the experiment's design module (scripts/design/<code>.py). It is the one place SessionConfig assets are
// made in bulk: a session is a copy of a template asset with the spec's fields set, so a design change is a rebuild, not a hand edit.
// Run it through the Unity CLI: unity command eval 'return ExperimentBuilder.Build("<spec.json>");'
public static class ExperimentBuilder
{
    private const string Root = "Assets/ScriptableObjects/Experiments";

    [Serializable] public class FieldSpec { public string p; public string v; }

    [Serializable]
    public class SessionSpec
    {
        public string name;
        public string template;         // asset path of the asset copied when the session asset does not exist yet
        public FieldSpec[] fields;      // SerializedProperty path and value as text
    }

    [Serializable]
    public class ExperimentSpec
    {
        public string code;
        public string title;
        public string[] requires;
        public bool countsTowardTotal;
        public bool removeStale;        // delete the experiment's <code>_S*/<code>_I* assets that the spec does not list
        public SessionSpec[] sessions;  // in play order
    }

    public static string Build(string specPath)
    {
        ExperimentSpec spec = JsonUtility.FromJson<ExperimentSpec>(File.ReadAllText(specPath));
        if (spec == null || string.IsNullOrEmpty(spec.code) || spec.sessions == null)
        {
            throw new ArgumentException("ExperimentBuilder: the spec has no code or sessions.");
        }

        string folder = $"{Root}/{spec.code}";
        if (!AssetDatabase.IsValidFolder(folder))
        {
            AssetDatabase.CreateFolder(Root, spec.code);
        }

        int created = 0;
        var listed = new HashSet<string>();
        var assets = new List<SessionConfig>();
        foreach (SessionSpec session in spec.sessions)
        {
            if (!session.name.StartsWith(spec.code + "_"))
            {
                throw new ArgumentException($"ExperimentBuilder: '{session.name}' does not start with '{spec.code}_'.");
            }

            string path = $"{folder}/{session.name}.asset";
            listed.Add(path);
            if (AssetDatabase.LoadAssetAtPath<SessionConfig>(path) == null)
            {
                if (!AssetDatabase.CopyAsset(session.template, path))
                {
                    throw new InvalidOperationException($"ExperimentBuilder: could not copy {session.template} to {path}.");
                }

                created++;
            }

            SessionConfig asset = AssetDatabase.LoadAssetAtPath<SessionConfig>(path);
            var serialized = new SerializedObject(asset);
            foreach (FieldSpec field in session.fields)
            {
                SetField(serialized, field.p, field.v, session.name);
            }

            serialized.ApplyModifiedPropertiesWithoutUndo();
            EditorUtility.SetDirty(asset);
            assets.Add(asset);
        }

        int removed = 0;
        if (spec.removeStale)
        {
            foreach (string guid in AssetDatabase.FindAssets("t:SessionConfig", new[] { folder }))
            {
                string path = AssetDatabase.GUIDToAssetPath(guid);
                if (!listed.Contains(path) && AssetDatabase.DeleteAsset(path))
                {
                    removed++;
                }
            }
        }

        string experimentPath = $"{folder}/{spec.code}.asset";
        ExperimentConfig experiment = AssetDatabase.LoadAssetAtPath<ExperimentConfig>(experimentPath);
        if (experiment == null)
        {
            experiment = ScriptableObject.CreateInstance<ExperimentConfig>();
            AssetDatabase.CreateAsset(experiment, experimentPath);
        }

        var experimentObject = new SerializedObject(experiment);
        experimentObject.FindProperty("code").stringValue = spec.code;
        experimentObject.FindProperty("title").stringValue = spec.title;
        experimentObject.FindProperty("countsTowardTotal").boolValue = spec.countsTowardTotal;
        SetObjectList(experimentObject.FindProperty("requires"), spec.requires ?? new string[0]);
        SerializedProperty list = experimentObject.FindProperty("sessions");
        list.arraySize = assets.Count;
        for (int i = 0; i < assets.Count; i++)
        {
            list.GetArrayElementAtIndex(i).objectReferenceValue = assets[i];
        }

        experimentObject.ApplyModifiedPropertiesWithoutUndo();
        EditorUtility.SetDirty(experiment);

        bool registered = Register(experiment);
        AssetDatabase.SaveAssets();
        AssetDatabase.Refresh();
        return $"{spec.code}: {assets.Count} session assets ({created} created, {removed} removed), experiment asset {(registered ? "added to" : "already in")} the catalog";
    }

    private static void SetObjectList(SerializedProperty array, string[] values)
    {
        array.arraySize = values.Length;
        for (int i = 0; i < values.Length; i++)
        {
            array.GetArrayElementAtIndex(i).stringValue = values[i];
        }
    }

    private static bool Register(ExperimentConfig experiment)
    {
        ExperimentCatalog catalog = Resources.Load<ExperimentCatalog>("ExperimentCatalog");
        if (catalog == null)
        {
            throw new InvalidOperationException("ExperimentBuilder: Resources/ExperimentCatalog.asset not found.");
        }

        var serialized = new SerializedObject(catalog);
        SerializedProperty list = serialized.FindProperty("experiments");
        for (int i = 0; i < list.arraySize; i++)
        {
            if (list.GetArrayElementAtIndex(i).objectReferenceValue == experiment)
            {
                return false;
            }
        }

        list.arraySize++;
        list.GetArrayElementAtIndex(list.arraySize - 1).objectReferenceValue = experiment;
        serialized.ApplyModifiedPropertiesWithoutUndo();
        EditorUtility.SetDirty(catalog);
        return true;
    }

    // Sets one serialized field from text. A path ending in ".Array.size" resizes the array above it.
    private static void SetField(SerializedObject target, string path, string value, string owner)
    {
        const string sizeSuffix = ".Array.size";
        if (path.EndsWith(sizeSuffix))
        {
            SerializedProperty array = target.FindProperty(path.Substring(0, path.Length - sizeSuffix.Length));
            if (array == null || !array.isArray)
            {
                throw new ArgumentException($"{owner}: no array '{path}'.");
            }

            array.arraySize = int.Parse(value, System.Globalization.CultureInfo.InvariantCulture);
            return;
        }

        SerializedProperty property = target.FindProperty(path);
        if (property == null)
        {
            throw new ArgumentException($"{owner}: no serialized field '{path}'.");
        }

        var invariant = System.Globalization.CultureInfo.InvariantCulture;
        switch (property.propertyType)
        {
            case SerializedPropertyType.Integer: property.intValue = int.Parse(value, invariant); break;
            case SerializedPropertyType.Boolean: property.boolValue = value == "true"; break;
            case SerializedPropertyType.Float: property.floatValue = float.Parse(value, invariant); break;
            case SerializedPropertyType.String: property.stringValue = value; break;
            case SerializedPropertyType.Enum: property.enumValueIndex = int.Parse(value, invariant); break;
            case SerializedPropertyType.Vector2:
                string[] xy = value.Split(',');
                property.vector2Value = new Vector2(float.Parse(xy[0], invariant), float.Parse(xy[1], invariant));
                break;
            default:
                throw new ArgumentException($"{owner}: field '{path}' has type {property.propertyType}, which the builder does not set.");
        }
    }
}
