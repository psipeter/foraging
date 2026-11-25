using UnityEngine;

// The floating disc of a ranking stage: a small bumpy oval of terrain, a little bigger than the arc of bushes, with a short underside. Its top uses the
// terrain's own shader and textures with a fixed moisture (0 arid, 0.5 grassland, 1 swamp: the three key textures), so it looks like the real ground. It is built in code for each set
// in the set's own frame (x to the player's right, z ahead, the player at the origin), and `HeightAt` gives the surface height the bushes stand on.
public class RankingDisc
{
    private const int Segments = 72;
    private const int Rings = 6;
    private const int MaskSegments = 32;
    private const float MaskDepth = 0.6f;           // the plane lies this far under the surface: the disc keeps an edge this thick, and below it nothing shows
    private const float MaskScale = 1.7f;           // the mask plane reaches this many times the disc's larger half size
    private const float Dome = 0.3f;            // the centre stands this far above the edge
    private const float UnderRim = 0.6f, UnderMiddle = 1.9f, UnderPoint = 3.3f;

    public GameObject Object { get; private set; }
    public int TextureIndex { get; private set; }            // 0 arid, 1 grassland, 2 swamp

    private float _rx, _rz, _phase1, _phase2, _phase3;
    private float _tilt;                                  // radians: the far side rises (0 = flat); `_rz` is then the half size along the slope
    private Vector2 _centre;                              // in the set's frame

    // `terrain` is the terrain's material instance (its shader, textures and tiling); `centre` and `turn` place the disc in the world (the set's frame is the player's position turned
    // by the view's yaw); `radiusX` and `radiusZ` are the outline's mean half sizes along the player's right and ahead; `halfExtent` is the world's, for the texture's scale.
    public static RankingDisc Create(Material terrain, Vector3 position, Quaternion turn, Vector2 centre, float radiusX, float radiusZ, float halfExtent, int seed, int layer, float tiltDegrees = 0f)
    {
        float tilt = tiltDegrees * Mathf.Deg2Rad;
        var disc = new RankingDisc { _rx = radiusX, _rz = radiusZ / Mathf.Cos(tilt), _centre = centre, _tilt = tilt };      // `radiusZ` is the horizontal half size
        var rng = new System.Random(seed);
        disc.TextureIndex = rng.Next(3);
        disc._phase1 = (float)(rng.NextDouble() * Mathf.PI * 2f);
        disc._phase2 = (float)(rng.NextDouble() * Mathf.PI * 2f);
        disc._phase3 = (float)(rng.NextDouble() * Mathf.PI * 2f);

        disc.Object = new GameObject("RankingDisc");
        disc.Object.layer = layer;
        Quaternion frame = turn * Quaternion.Euler(-tiltDegrees, 0f, 0f);            // tipped about the player's right: the far side up, a hillside
        disc.Object.transform.SetPositionAndRotation(position, frame);
        disc.Object.AddComponent<MeshFilter>().sharedMesh = disc.BuildMesh(position, frame, halfExtent);
        MeshRenderer renderer = disc.Object.AddComponent<MeshRenderer>();
        var top = new Material(terrain);
        top.SetFloat("_GrayAmount", 0f);
        var under = new Material(Shader.Find("Universal Render Pipeline/Lit"));
        under.SetColor("_BaseColor", new Color(0.2f, 0.17f, 0.13f));
        under.SetFloat("_Smoothness", 0f);
        renderer.sharedMaterials = new[] { top, under };
        renderer.shadowCastingMode = UnityEngine.Rendering.ShadowCastingMode.Off;
        renderer.receiveShadows = true;
        Material mask = Resources.Load<Material>("StageMask");
        if (mask != null)
        {
            disc.AddMask(mask, Mathf.Max(disc._rx, disc._rz) * MaskScale, layer);
        }

        return disc;
    }

    // A flat plane a little under the surface (MaskDepth), wider than the disc, that writes depth and no colour (Shaders/StageMask.shader): the half of a bush that is buried in the disc, which no terrain
    // hides here, fails the depth test instead of sticking out through the disc's thin underside. Under it the disc's underside is hidden too: seen from above the disc is a plate with an edge MaskDepth thick.
    private void AddMask(Material material, float radius, int layer)
    {
        var go = new GameObject("StageMask");
        go.layer = layer;
        go.transform.SetParent(Object.transform, false);
        go.transform.localPosition = new Vector3(0f, -MaskDepth, 0f);
        var vertices = new Vector3[MaskSegments + 1];
        var triangles = new int[MaskSegments * 3];
        for (int s = 0; s < MaskSegments; s++)
        {
            float angle = 2f * Mathf.PI * s / MaskSegments;
            vertices[s + 1] = new Vector3(radius * Mathf.Cos(angle), 0f, radius * Mathf.Sin(angle));
            triangles[3 * s] = 0;
            triangles[3 * s + 1] = 1 + (s + 1) % MaskSegments;
            triangles[3 * s + 2] = 1 + s;
        }

        var mesh = new Mesh { name = "StageMask", vertices = vertices, triangles = triangles };
        mesh.RecalculateBounds();
        go.AddComponent<MeshFilter>().sharedMesh = mesh;
        MeshRenderer renderer = go.AddComponent<MeshRenderer>();
        renderer.sharedMaterial = material;
        renderer.shadowCastingMode = UnityEngine.Rendering.ShadowCastingMode.Off;
        renderer.receiveShadows = false;
    }

    // The outline's radius factor at an angle (1 = the oval's mean): the bumps that make it irregular.
    private float Bump(float angle)
    {
        return 1f + 0.06f * Mathf.Sin(5f * angle + _phase1) + 0.035f * Mathf.Sin(8f * angle + _phase2) + 0.03f * Mathf.Sin(3f * angle + _phase3);
    }

    // The surface height at a point of the set's frame (the player at the origin): the slope (0 when flat) plus a gentle dome over the oval, 0 at its edge.
    public float HeightAt(float x, float z)
    {
        float dz = z - _centre.y;
        float u = (x - _centre.x) / _rx, v = dz / Mathf.Cos(_tilt) / _rz;
        float rho = Mathf.Sqrt(u * u + v * v) / Bump(Mathf.Atan2(v, u));
        return dz * Mathf.Tan(_tilt) + Dome * Mathf.Clamp01(1f - rho * rho);
    }

    private Mesh BuildMesh(Vector3 position, Quaternion turn, float halfExtent)
    {
        int topCount = 1 + Rings * Segments;
        int ringStart = topCount;                                        // the underside: three rings and a point
        var vertices = new Vector3[topCount + 3 * Segments + 1];
        var uv = new Vector2[vertices.Length];
        var uv2 = new Vector2[vertices.Length];
        float moisture = TextureIndex * 0.5f;
        for (int i = 0; i < vertices.Length; i++)
        {
            uv2[i] = new Vector2(moisture, 0f);
        }

        vertices[0] = new Vector3(0f, Dome, 0f);
        for (int r = 1; r <= Rings; r++)
        {
            float rho = r / (float)Rings;
            for (int s = 0; s < Segments; s++)
            {
                vertices[1 + (r - 1) * Segments + s] = Point(s, rho, Dome * (1f - rho * rho));
            }
        }

        float[] underRho = { 0.985f, 0.8f, 0.42f };
        float[] underY = { -UnderRim, -UnderMiddle, -UnderPoint * 0.8f };
        for (int k = 0; k < 3; k++)
        {
            for (int s = 0; s < Segments; s++)
            {
                vertices[ringStart + k * Segments + s] = Point(s, underRho[k], underY[k]);
            }
        }

        vertices[vertices.Length - 1] = new Vector3(0f, -UnderPoint, 0f);
        for (int i = 0; i < topCount; i++)
        {
            Vector3 world = position + turn * vertices[i];
            uv[i] = new Vector2(world.x, world.z) / (2f * halfExtent);
        }

        var top = new System.Collections.Generic.List<int>();
        for (int s = 0; s < Segments; s++)
        {
            int n = (s + 1) % Segments;
            top.AddRange(new[] { 0, 1 + n, 1 + s });
        }

        for (int r = 1; r < Rings; r++)
        {
            for (int s = 0; s < Segments; s++)
            {
                int n = (s + 1) % Segments;
                int a = 1 + (r - 1) * Segments + s, b = 1 + (r - 1) * Segments + n, c = 1 + r * Segments + s, d = 1 + r * Segments + n;
                top.AddRange(new[] { a, b, c, b, d, c });
            }
        }

        var under = new System.Collections.Generic.List<int>();
        for (int s = 0; s < Segments; s++)
        {
            int n = (s + 1) % Segments;
            int outer = 1 + (Rings - 1) * Segments;                              // the top's last ring
            under.AddRange(new[] { outer + s, outer + n, ringStart + s, outer + n, ringStart + n, ringStart + s });
            for (int k = 0; k < 2; k++)
            {
                int a = ringStart + k * Segments + s, b = ringStart + k * Segments + n, c = ringStart + (k + 1) * Segments + s, d = ringStart + (k + 1) * Segments + n;
                under.AddRange(new[] { a, b, c, b, d, c });
            }

            under.AddRange(new[] { ringStart + 2 * Segments + s, ringStart + 2 * Segments + n, vertices.Length - 1 });
        }

        var mesh = new Mesh { name = "RankingDisc" };
        mesh.vertices = vertices;
        mesh.uv = uv;
        mesh.uv2 = uv2;
        mesh.uv3 = new Vector2[vertices.Length];          // the terrain shader reads the mountain weights (rock, snow) from here: none on the disc
        mesh.subMeshCount = 2;
        mesh.SetTriangles(top, 0);
        mesh.SetTriangles(under, 1);
        mesh.RecalculateNormals();
        mesh.RecalculateTangents();
        mesh.RecalculateBounds();
        return mesh;
    }

    // A point of the outline scaled by rho, at segment s, at height y (in the disc's own frame: the set's frame shifted so the oval's middle is the origin).
    private Vector3 Point(int s, float rho, float y)
    {
        float angle = 2f * Mathf.PI * s / Segments;
        float f = Bump(angle) * rho;
        return new Vector3(_rx * f * Mathf.Cos(angle), y, _rz * f * Mathf.Sin(angle));
    }
}
