using System;
using System.Collections.Generic;
using System.IO;
using System.IO.Compression;

// One quantized trajectory frame: every column already rounded to its step (see TrajectoryCodec).
public readonly struct FrameQ
{
    public readonly long T, X, Z, Yaw, Pitch, Keys;

    public FrameQ(long t, long x, long z, long yaw, long pitch, long keys)
    {
        T = t; X = x; Z = z; Yaw = yaw; Pitch = pitch; Keys = keys;
    }

    public static FrameQ From(double t, double x, double z, double yaw, double pitch, int keys)
    {
        return new FrameQ(TrajectoryCodec.Quantize(t, TrajectoryCodec.TStep), TrajectoryCodec.Quantize(x, TrajectoryCodec.XzStep),
            TrajectoryCodec.Quantize(z, TrajectoryCodec.XzStep), TrajectoryCodec.Quantize(yaw, TrajectoryCodec.AngleStep),
            TrajectoryCodec.Quantize(pitch, TrajectoryCodec.AngleStep), keys);
    }
}

// Compact encoding of a run of consecutive trajectory frames, the C# side of scripts/trajectory_codec.py (read its
// docstring: the format, and why time is quantized to a microsecond). Per frame t, x, z, yaw, pitch, keys, each a
// multiple of its step, delta-coded against the previous frame (the first against zero), zigzag LEB128 varints,
// raw DEFLATE; the header carries a CRC32 of the uncompressed varint bytes. Different DEFLATE encoders give
// different compressed bytes for the same varints, so what must agree with Python is the varint stream (the CRC), not the compressed body.
public static class TrajectoryCodec
{
    public const double TStep = 1e-6;
    public const double XzStep = 0.01;
    public const double AngleStep = 0.02;

    private const byte Version = 1;
    private const int MaxFrames = 200000;
    private static readonly uint[] CrcTable = BuildCrcTable();

    // Round half to even (Math.Round's default), as numpy's rint does in the Python codec.
    public static long Quantize(double value, double step)
    {
        return (long)Math.Round(value / step);
    }

    public static byte[] Encode(IReadOnlyList<FrameQ> frames, int start, int count, uint firstSeq)
    {
        if (count < 1 || count > MaxFrames)
        {
            throw new ArgumentException($"a chunk holds 1 to {MaxFrames} frames");
        }

        byte[] raw;
        using (var varints = new MemoryStream(count * 8))
        {
            long pt = 0, px = 0, pz = 0, pyaw = 0, ppitch = 0, pkeys = 0;
            for (int i = start; i < start + count; i++)
            {
                FrameQ f = frames[i];
                WriteVarint(varints, f.T - pt);
                WriteVarint(varints, f.X - px);
                WriteVarint(varints, f.Z - pz);
                WriteVarint(varints, f.Yaw - pyaw);
                WriteVarint(varints, f.Pitch - ppitch);
                WriteVarint(varints, f.Keys - pkeys);
                pt = f.T; px = f.X; pz = f.Z; pyaw = f.Yaw; ppitch = f.Pitch; pkeys = f.Keys;
            }

            raw = varints.ToArray();
        }

        using (var output = new MemoryStream())
        {
            var header = new BinaryWriter(output);
            header.Write(new byte[] { (byte)'F', (byte)'T', (byte)'R', (byte)'J' });
            header.Write(Version);
            header.Write((uint)count);
            header.Write(firstSeq);
            header.Write(TStep);
            header.Write(XzStep);
            header.Write(AngleStep);
            header.Write(Crc32(raw));
            header.Flush();
            using (var deflate = new DeflateStream(output, CompressionLevel.Optimal, true))
            {
                deflate.Write(raw, 0, raw.Length);
            }

            return output.ToArray();
        }
    }

    private static void WriteVarint(Stream stream, long value)
    {
        ulong v = (ulong)((value << 1) ^ (value >> 63));       // zigzag
        while (v >= 0x80)
        {
            stream.WriteByte((byte)(v | 0x80));
            v >>= 7;
        }

        stream.WriteByte((byte)v);
    }

    private static uint[] BuildCrcTable()
    {
        var table = new uint[256];
        for (uint n = 0; n < 256; n++)
        {
            uint c = n;
            for (int k = 0; k < 8; k++)
            {
                c = (c & 1) != 0 ? 0xEDB88320u ^ (c >> 1) : c >> 1;
            }

            table[n] = c;
        }

        return table;
    }

    private static uint Crc32(byte[] bytes)
    {
        uint c = 0xFFFFFFFFu;
        foreach (byte b in bytes)
        {
            c = CrcTable[(c ^ b) & 0xFF] ^ (c >> 8);
        }

        return c ^ 0xFFFFFFFFu;
    }
}
