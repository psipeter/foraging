import numpy as np
import pytest

import trajectory_codec as codec

# The wire format pinned byte for byte; the C# encoder has to produce this too (see the module docstring).
GOLDEN_FRAMES = [[0.0, 183.1345, 165.1293, 21.6543, 0.0, 0],
                 [0.002292, 183.1345, 165.1293, 21.6543, 0.0, 1],
                 [0.004, -1.234, 5.0, -3.0, -12.5, 5]]
GOLDEN = bytes.fromhex(
    "4654524a0103000000030000008dedb5a0f7c6b03e7b14ae47e17a843f7b14ae47e17a943f"
    "df76eefa6398348fa9a989e99b0003c30b65062060ba21d5be8069e62fc685c20f393900")


def walk(n, seed=0):
    rng = np.random.default_rng(seed)
    return np.c_[np.cumsum(rng.uniform(0.001, 0.01, n)), np.cumsum(rng.normal(0, 0.05, n)) + 183,
                 np.cumsum(rng.normal(0, 0.05, n)) + 165, np.cumsum(rng.normal(0, 0.3, n)),
                 rng.normal(0, 2, n), rng.integers(0, 8, n)]


def test_round_trip_returns_the_quantized_frames_within_half_a_step():
    f = walk(2000)
    first, steps, got = codec.decode(codec.encode(f, first_seq=7))
    assert first == 7 and steps == codec.DEFAULT_STEPS
    assert np.array_equal(got, codec.quantize(f))
    assert np.all(np.abs(got - f) <= codec.DEFAULT_STEPS.vector() / 2 + 1e-9)


def test_golden_bytes():
    assert codec.encode(GOLDEN_FRAMES, first_seq=3) == GOLDEN
    first, _, got = codec.decode(GOLDEN)
    assert first == 3 and np.allclose(got, codec.quantize(GOLDEN_FRAMES))


def test_rounding_is_half_to_even_like_math_round():
    steps = codec.Steps(t=1.0, xz=1.0, angle=1.0)
    got = codec.quantize([[0.5, 1.5, 2.5, -0.5, -1.5, 0]], steps)
    assert got.tolist() == [[0.0, 2.0, 2.0, -0.0, -2.0, 0.0]]


def test_empty_chunk_and_single_frame():
    assert codec.decode(codec.encode(np.empty((0, 6))))[2].shape == (0, 6)
    assert np.array_equal(codec.decode(codec.encode([[1.0, 2.0, 3.0, 4.0, 5.0, 6]]))[2],
                          codec.quantize([[1.0, 2.0, 3.0, 4.0, 5.0, 6]]))


def test_large_jumps_and_negative_values():
    f = np.array([[0.0, 0, 0, 0, 0, 0], [1e5, -1e6, 1e6, -359.98, 89.98, 7], [2e5, 0, 0, 359.98, -89.98, 0]])
    assert np.array_equal(codec.decode(codec.encode(f))[2], codec.quantize(f))


def test_custom_steps_travel_in_the_header():
    steps = codec.Steps(t=0.01, xz=0.5, angle=0.022)
    _, got_steps, got = codec.decode(codec.encode(walk(50), steps=steps))
    assert got_steps == steps and np.array_equal(got, codec.quantize(walk(50), steps))


def test_a_stationary_participant_costs_almost_nothing():
    still = np.tile([10.0, 183.0, 165.0, 21.0, 0.0, 0], (5000, 1)) + np.c_[np.arange(5000) * 0.002, np.zeros((5000, 5))]
    assert len(codec.encode(still)) < 200


@pytest.mark.parametrize("bad", [
    lambda b: b[:10],                                    # shorter than the header
    lambda b: b"XXXX" + b[4:],                           # wrong magic
    lambda b: b[:4] + b"\x09" + b[5:],                   # unknown version
    lambda b: b[:-1],                                    # truncated body
    lambda b: b + b"\x00",                               # trailing byte
    lambda b: b[:45] + bytes([b[45] ^ 0x01]) + b[46:],   # a flipped bit in the body (DEFLATE alone would not notice)
    lambda b: b[:38] + bytes([b[38] ^ 0x01]) + b[39:],   # a flipped bit in the checksum
])
def test_malformed_chunks_are_refused(bad):
    with pytest.raises(ValueError):
        codec.decode(bad(codec.encode(walk(300))))


def test_the_header_cannot_claim_more_frames_than_the_body_holds_or_the_limit_allows():
    good = bytearray(codec.encode(walk(100)))
    good[5:9] = (101).to_bytes(4, "little")
    with pytest.raises(ValueError):
        codec.decode(bytes(good))
    good[5:9] = (codec.MAX_FRAMES + 1).to_bytes(4, "little")
    with pytest.raises(ValueError):
        codec.decode(bytes(good))


def test_a_decompression_bomb_is_refused():
    import zlib
    body = zlib.compressobj(9, zlib.DEFLATED, -15)
    payload = body.compress(b"\x00" * 5_000_000) + body.flush()
    head = codec.HEADER.pack(codec.MAGIC, codec.VERSION, 10, 0, 0.001, 0.01, 0.02, 0)
    with pytest.raises(ValueError):
        codec.decode(head + payload)


def test_non_finite_and_misshapen_input_is_refused():
    with pytest.raises(ValueError):
        codec.encode([[0, 0, 0, 0, float("nan"), 0]])
    with pytest.raises(ValueError):
        codec.encode([[0, 0, 0]])


def test_size_on_a_realistic_walk_is_a_small_fraction_of_csv():
    f = walk(5000)
    csv = "\n".join(",".join(f"{v:.6f}" for v in row) for row in f).encode()
    assert len(codec.encode(f)) < len(csv) / 5


def test_every_bit_flip_in_the_body_is_detected_or_harmless():
    good = codec.encode(walk(200))
    want = codec.decode(good)[2]
    for i in range(codec.HEADER.size, len(good)):
        for bit in range(8):
            damaged = bytearray(good)
            damaged[i] ^= 1 << bit
            try:
                got = codec.decode(bytes(damaged))[2]
            except ValueError:
                continue
            assert np.array_equal(got, want)         # only unused bits of the last byte can change nothing
