import hashlib
import os
import shutil
import tempfile
from pathlib import Path

import numpy as np
import requests
import soundfile as sf

try:
    import librosa
    librosa.load  # trigger lazy submodule — will raise if numba is missing
    _LIBROSA_AVAILABLE = True
except Exception:
    librosa = None  # type: ignore
    _LIBROSA_AVAILABLE = False
    print("[normalizer] librosa not available — using pydub/soundfile fallback")

try:
    from pydub import AudioSegment
    _PYDUB_AVAILABLE = True
except ImportError:
    AudioSegment = None  # type: ignore
    _PYDUB_AVAILABLE = False


def _load_audio_as_numpy(path: str, target_sr: int, mono: bool):
    """Load any audio file to numpy array, using librosa > pydub > soundfile."""
    if _LIBROSA_AVAILABLE:
        audio, sr = librosa.load(path, sr=target_sr, mono=mono)
        return audio, sr

    # Try soundfile first (handles WAV/FLAC/OGG natively)
    ext = Path(path).suffix.lower()
    if ext not in (".mp3", ".m4a", ".aac"):
        try:
            audio, sr = sf.read(path, always_2d=False)
            if mono and audio.ndim == 2:
                audio = audio.mean(axis=1)
            if sr != target_sr:
                ratio = target_sr / sr
                new_len = int(len(audio) * ratio)
                audio = np.interp(
                    np.linspace(0, len(audio) - 1, new_len),
                    np.arange(len(audio)),
                    audio if audio.ndim == 1 else audio[:, 0],
                )
            return audio, target_sr
        except Exception:
            pass  # fall through to pydub

    # Use pydub (requires ffmpeg) for compressed formats
    if _PYDUB_AVAILABLE:
        seg = AudioSegment.from_file(path)
        seg = seg.set_frame_rate(target_sr)
        if mono:
            seg = seg.set_channels(1)
        samples = np.array(seg.get_array_of_samples(), dtype=np.float32)
        samples /= 2 ** (seg.sample_width * 8 - 1)
        if seg.channels == 2 and not mono:
            samples = samples.reshape(-1, 2)
        return samples, target_sr

    raise RuntimeError(
        "Cannot decode audio: install pydub+ffmpeg (`brew install ffmpeg && pip install pydub`)"
    )


def download_file(url: str, dest_path: str, api_key: str = "") -> bool:
    headers = {
        "User-Agent": "BecomingSoundEngine/1.0 (https://github.com/absybvc-cloud/Becoming; sound art project)",
    }
    # Freesound preview URLs are public — sending an auth header can cause 401.
    # Only add the token header for non-preview download URLs.
    if api_key and "previews" not in url:
        headers["Authorization"] = f"Token {api_key}"
    try:
        with requests.get(url, headers=headers, stream=True, timeout=30) as r:
            r.raise_for_status()
            Path(dest_path).parent.mkdir(parents=True, exist_ok=True)
            with open(dest_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=65536):
                    f.write(chunk)
        return True
    except Exception as e:
        print(f"[normalizer] download failed: {e}")
        return False


def compute_checksum(file_path: str) -> str:
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def normalize_audio(
    raw_path: str,
    out_path: str,
    target_sr: int = 44100,
    target_channels: int = 2,
) -> dict:
    """
    Load raw audio, resample, set channels, write normalized WAV.
    Returns basic properties dict.
    """
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)

    try:
        audio, sr = _load_audio_as_numpy(raw_path, target_sr, mono=(target_channels == 1))
    except Exception as e:
        raise RuntimeError(f"Failed to load audio: {e}")

    # ensure correct shape: (samples,) for mono, (samples, 2) for stereo
    if target_channels == 2:
        if audio.ndim == 1:
            audio = np.stack([audio, audio], axis=-1)
        elif _LIBROSA_AVAILABLE:
            audio = audio.T  # librosa returns (channels, samples) for stereo

    duration = len(audio) / target_sr if audio.ndim == 1 else audio.shape[0] / target_sr
    sf.write(out_path, audio, target_sr, subtype="PCM_16")

    return {
        "sample_rate": target_sr,
        "channels": target_channels,
        "duration_seconds": round(duration, 3),
    }


def compute_loudness_features(file_path: str) -> dict:
    """Compute RMS, peak, silence ratio, clipping ratio."""
    try:
        audio, sr = _load_audio_as_numpy(file_path, target_sr=44100, mono=True)
    except Exception:
        return {}

    rms = float(np.sqrt(np.mean(audio ** 2)))
    peak = float(np.max(np.abs(audio)))
    silence_ratio = float(np.mean(np.abs(audio) < 0.01))
    clipping_ratio = float(np.mean(np.abs(audio) > 0.99))

    # approximate LUFS (simplified, not ITU-R BS.1770 compliant)
    loudness_lufs = float(20 * np.log10(rms + 1e-9))

    return {
        "rms": round(rms, 6),
        "peak_db": round(float(20 * np.log10(peak + 1e-9)), 3),
        "silence_ratio": round(silence_ratio, 4),
        "clipping_ratio": round(clipping_ratio, 6),
        "loudness_lufs": round(loudness_lufs, 3),
    }
