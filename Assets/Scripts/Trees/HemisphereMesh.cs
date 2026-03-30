using System.Collections.Generic;
using UnityEngine;

public static class HemisphereMesh
{
    private static readonly Dictionary<int, Mesh> Cache = new Dictionary<int, Mesh>();

    /// <summary>
    /// Generates a hemisphere mesh with dome-up orientation:
    /// - Flat face at Y=0
    /// - Dome apex at Y=1
    /// </summary>
    public static Mesh Create(int segments)
    {
        int seg = Mathf.Max(3, segments);

        if (Cache.TryGetValue(seg, out Mesh cached) && cached != null)
        {
            return cached;
        }

        var vertices = new List<Vector3>();
        var normals = new List<Vector3>();
        var uvs = new List<Vector2>();
        var triangles = new List<int>();

        int lonSegments = seg;   // longitude slices
        int latSegments = seg;   // latitude rings

        // Hemisphere surface (unit sphere, centered at origin; hemisphere is Y in [0..1]).
        for (int lat = 0; lat <= latSegments; lat++)
        {
            float t = lat / (float)latSegments; // 0..1
            float theta = t * (Mathf.PI * 0.5f); // 0..pi/2

            float y = Mathf.Sin(theta);
            float r = Mathf.Cos(theta);

            for (int lon = 0; lon <= lonSegments; lon++)
            {
                float u = lon / (float)lonSegments; // 0..1
                float phi = u * Mathf.PI * 2f;      // 0..2pi

                float x = r * Mathf.Cos(phi);
                float z = r * Mathf.Sin(phi);

                vertices.Add(new Vector3(x, y, z));
                normals.Add(new Vector3(x, y, z).normalized);
                uvs.Add(new Vector2(u, t));
            }
        }

        // Hemisphere triangles
        int rowVertexCount = lonSegments + 1;
        for (int lat = 0; lat < latSegments; lat++)
        {
            for (int lon = 0; lon < lonSegments; lon++)
            {
                int a = lat * rowVertexCount + lon;
                int b = a + rowVertexCount;
                int c = a + 1;
                int d = b + 1;

                // Ensure triangles face outward (consistent with outward normals).
                triangles.Add(a);
                triangles.Add(b);
                triangles.Add(c);

                triangles.Add(c);
                triangles.Add(b);
                triangles.Add(d);
            }
        }

        // Close the flat bottom with a disc of triangles at y=0.
        // We use separate vertices so we can give the disc downward normals.
        int hemisphereVertexCount = vertices.Count;
        int centerIndex = vertices.Count;
        vertices.Add(Vector3.zero);
        normals.Add(Vector3.down);
        uvs.Add(new Vector2(0.5f, 0f));

        int ringStart = vertices.Count;
        for (int lon = 0; lon <= lonSegments; lon++)
        {
            float u = lon / (float)lonSegments;
            float phi = u * Mathf.PI * 2f;

            float x = Mathf.Cos(phi);
            float z = Mathf.Sin(phi);

            vertices.Add(new Vector3(x, 0f, z));
            normals.Add(Vector3.down);
            uvs.Add(new Vector2(u, 0f));
        }

        for (int lon = 0; lon < lonSegments; lon++)
        {
            int current = ringStart + lon;
            int next = ringStart + lon + 1;

            // Winding chosen so the disc front face points downward (-Y).
            triangles.Add(centerIndex);
            triangles.Add(next);
            triangles.Add(current);
        }

        var mesh = new Mesh
        {
            name = $"Hemisphere_{seg}_Segments"
        };

        mesh.SetVertices(vertices);
        mesh.SetNormals(normals);
        mesh.SetUVs(0, uvs);
        mesh.SetTriangles(triangles, 0, true);
        mesh.RecalculateBounds();

        Cache[seg] = mesh;
        return mesh;
    }
}

