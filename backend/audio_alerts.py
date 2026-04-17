"""
SIEWS+ 5.0 — Audio Alert Generator
Generates audio alert tones (WAV files) for browser-side playback.
Pre-generates alert sounds so no external audio files are needed.
"""
import os
import struct
import math

AUDIO_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "audio")
os.makedirs(AUDIO_DIR, exist_ok=True)


def _generate_wav(filename: str, frequency: float, duration: float, sample_rate: int = 44100,
                  volume: float = 0.6, fade_ms: int = 50, repeat: int = 1, gap_ms: int = 200):
    """
    Generate a WAV file with a sine wave tone.

    Args:
        filename:    Output filename (in AUDIO_DIR)
        frequency:   Tone frequency in Hz
        duration:    Duration per tone in seconds
        sample_rate: Audio sample rate
        volume:      Volume (0.0 - 1.0)
        fade_ms:     Fade in/out duration in milliseconds
        repeat:      Number of beep repetitions
        gap_ms:      Gap between repetitions in milliseconds
    """
    filepath = os.path.join(AUDIO_DIR, filename)
    if os.path.exists(filepath):
        return filepath

    all_samples = []
    fade_samples = int(sample_rate * fade_ms / 1000)
    gap_samples = int(sample_rate * gap_ms / 1000)

    for r in range(repeat):
        num_samples = int(sample_rate * duration)
        for i in range(num_samples):
            t = i / sample_rate
            sample = volume * math.sin(2 * math.pi * frequency * t)

            # Fade in
            if i < fade_samples:
                sample *= i / fade_samples
            # Fade out
            if i > num_samples - fade_samples:
                sample *= (num_samples - i) / fade_samples

            all_samples.append(sample)

        # Add gap (silence) between repeats
        if r < repeat - 1:
            all_samples.extend([0.0] * gap_samples)

    # Encode as 16-bit PCM WAV
    num_channels = 1
    bits_per_sample = 16
    data_size = len(all_samples) * 2  # 2 bytes per sample
    file_size = 36 + data_size

    with open(filepath, "wb") as f:
        # RIFF header
        f.write(b"RIFF")
        f.write(struct.pack("<I", file_size))
        f.write(b"WAVE")

        # fmt chunk
        f.write(b"fmt ")
        f.write(struct.pack("<I", 16))  # chunk size
        f.write(struct.pack("<H", 1))   # PCM format
        f.write(struct.pack("<H", num_channels))
        f.write(struct.pack("<I", sample_rate))
        f.write(struct.pack("<I", sample_rate * num_channels * bits_per_sample // 8))
        f.write(struct.pack("<H", num_channels * bits_per_sample // 8))
        f.write(struct.pack("<H", bits_per_sample))

        # data chunk
        f.write(b"data")
        f.write(struct.pack("<I", data_size))

        for sample in all_samples:
            clamped = max(-1.0, min(1.0, sample))
            int_sample = int(clamped * 32767)
            f.write(struct.pack("<h", int_sample))

    print(f"[AUDIO] Generated: {filepath}")
    return filepath


def generate_all_alert_sounds():
    """Pre-generate all alert sound files."""
    sounds = {
        "zone_entry.wav":     {"frequency": 880,  "duration": 0.15, "repeat": 2, "gap_ms": 100, "volume": 0.4},
        "zone_warning.wav":   {"frequency": 1200, "duration": 0.2,  "repeat": 3, "gap_ms": 150, "volume": 0.6},
        "zone_critical.wav":  {"frequency": 1600, "duration": 0.3,  "repeat": 5, "gap_ms": 100, "volume": 0.8},
        "shutdown.wav":       {"frequency": 440,  "duration": 1.0,  "repeat": 1, "gap_ms": 0,   "volume": 0.9},
        "ocr_detected.wav":   {"frequency": 660,  "duration": 0.1,  "repeat": 1, "gap_ms": 0,   "volume": 0.3},
        "face_recognized.wav": {"frequency": 523, "duration": 0.15, "repeat": 2, "gap_ms": 80,  "volume": 0.3},
    }

    for filename, params in sounds.items():
        _generate_wav(filename, **params)

    print(f"[AUDIO] All {len(sounds)} alert sounds ready")
    return list(sounds.keys())


# Generate on import
generate_all_alert_sounds()
