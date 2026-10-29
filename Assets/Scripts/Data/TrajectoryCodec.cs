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

    private const int HeaderSize = 41;
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

    // Decodes a chunk (used to check the codec against Python's chunks; the client never reads one back).
    public static FrameQ[] Decode(byte[] data, out uint firstSeq)
    {
        if (data.Length < HeaderSize || data[0] != 'F' || data[1] != 'T' || data[2] != 'R' || data[3] != 'J' || data[4] != Version)
        {
            throw new InvalidDataException("not a trajectory chunk of a known version");
        }

        var header = new BinaryReader(new MemoryStream(data, 5, HeaderSize - 5));
        uint n = header.ReadUInt32();
        firstSeq = header.ReadUInt32();
        double tStep = header.ReadDouble(), xzStep = header.ReadDouble(), angleStep = header.ReadDouble();
        uint crc = header.ReadUInt32();
        if (n == 0 || n > MaxFrames || tStep != TStep || xzStep != XzStep || angleStep != AngleStep)
        {
            throw new InvalidDataException("chunk header is outside what this client reads");
        }

        byte[] raw;
        using (var body = new MemoryStream(data, HeaderSize, data.Length - HeaderSize))
        using (var inflate = new DeflateStream(body, CompressionMode.Decompress))
        using (var output = new MemoryStream())
        {
            inflate.CopyTo(output);
            raw = output.ToArray();
        }

        if (Crc32(raw) != crc)
        {
            throw new InvalidDataException("chunk checksum mismatch");
        }

        var frames = new FrameQ[n];
        int pos = 0;
        long t = 0, x = 0, z = 0, yaw = 0, pitch = 0, keys = 0;
        for (int i = 0; i < n; i++)
        {
            t += ReadVarint(raw, ref pos);
            x += ReadVarint(raw, ref pos);
            z += ReadVarint(raw, ref pos);
            yaw += ReadVarint(raw, ref pos);
            pitch += ReadVarint(raw, ref pos);
            keys += ReadVarint(raw, ref pos);
            frames[i] = new FrameQ(t, x, z, yaw, pitch, keys);
        }

        if (pos != raw.Length)
        {
            throw new InvalidDataException("chunk body has extra bytes");
        }

        return frames;
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

    private static long ReadVarint(byte[] data, ref int pos)
    {
        ulong v = 0;
        for (int shift = 0; ; shift += 7)
        {
            if (pos >= data.Length || shift > 63)
            {
                throw new InvalidDataException("truncated or oversized varint");
            }

            byte b = data[pos++];
            v |= (ulong)(b & 0x7F) << shift;
            if ((b & 0x80) == 0)
            {
                break;
            }
        }

        return (long)(v >> 1) ^ -(long)(v & 1);
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
