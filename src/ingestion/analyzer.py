import numpy as np
import soundfile as sf

try:
    import librosa
    librosa.load  # trigger lazy submodule — will raise if numba is missing
    _LIBROSA_AVAILABLE = True
except Exception:
    librosa = None  # type: ignore
    _LIBROSA_AVAILABLE = False

try:
    from pydub import AudioSegment
    _PYDUB_AVAILABLE = True
except ImportError:
    AudioSegment = None  # type: ignore
    _PYDUB_AVAILABLE = False


def _load_mono(file_path: str):
    """Load any audio file as mono numpy float32 array."""
    if _LIBROSA_AVAILABLE:
        return librosa.load(file_path, sr=None, mono=True)
    if _PYDUB_AVAILABLE:
        seg = AudioSegment.from_file(file_path).set_channels(1)
        samples = np.array(seg.get_array_of_samples(), dtype=np.float32)
        samples /= 2 ** (seg.sample_width * 8 - 1)
        return samples, seg.frame_rate
    # soundfile fallback (WAV/FLAC only)
    audio, sr = sf.read(file_path, always_2d=False)
    if audio.ndim == 2:
        audio = audio.mean(axis=1)
    return audio.astype(np.float32), sr


def extract_features(file_path: str) -> dict:
    """Extract spectral and rhythmic features from a normalized audio file."""
    if not _LIBROSA_AVAILABLE:
        # minimal fallback: load with pydub/soundfile, compute basic features only
        try:
            audio, sr = _load_mono(file_path)
        except Exception as e:
            print(f"[analyzer] failed to load {file_path}: {e}")
            return {}
        zcr_mean = float(np.mean(np.abs(np.diff(np.sign(audio))) > 0))
        return {
            "spectral_centroid_mean": None,
            "spectral_bandwidth_mean": None,
            "zero_crossing_rate_mean": round(zcr_mean, 6),
            "tempo_estimate": None,
            "tonal_confidence": 0.5,   # assume atmospheric/tonal when unknown
            "noise_probability": 0.2,
            "music_probability": 0.6,  # bias toward musical — let curator decide
            "speech_probability": 0.2,
        }

    try:
        audio, sr = librosa.load(file_path, sr=None, mono=True)
    except Exception as e:
        print(f"[analyzer] failed to load {file_path}: {e}")
        return {}

    features = {}

    # spectral centroid
    sc = librosa.feature.spectral_centroid(y=audio, sr=sr)
    features["spectral_centroid_mean"] = float(np.mean(sc))

    # spectral bandwidth
    sb = librosa.feature.spectral_bandwidth(y=audio, sr=sr)
    features["spectral_bandwidth_mean"] = float(np.mean(sb))

    # zero crossing rate
    zcr = librosa.feature.zero_crossing_rate(audio)
    features["zero_crossing_rate_mean"] = float(np.mean(zcr))

    # tempo
    try:
        tempo, _ = librosa.beat.beat_track(y=audio, sr=sr)
        features["tempo_estimate"] = float(tempo)
    except Exception:
        features["tempo_estimate"] = None

    # tonal confidence via chroma energy
    try:
        chroma = librosa.feature.chroma_stft(y=audio, sr=sr)
        features["tonal_confidence"] = float(np.mean(np.max(chroma, axis=0)))
    except Exception:
        features["tonal_confidence"] = None

    # simple content probabilities based on heuristics
    rms = float(np.sqrt(np.mean(audio ** 2)))
    zcr_mean = features["zero_crossing_rate_mean"]
    sc_mean = features["spectral_centroid_mean"]

    # noise: high ZCR + high spectral centroid
    noise_prob = float(np.clip((zcr_mean * 10) * (sc_mean / 8000), 0, 1))

    # music: moderate ZCR + strong tonal confidence
    tonal = features.get("tonal_confidence") or 0.0
    music_prob = float(np.clip(tonal * 1.2, 0, 1))

    # speech: high ZCR, low tonal confidence, moderate centroid
    speech_prob = float(np.clip(zcr_mean * 5 * (1 - tonal), 0, 1))

    # normalize so they sum to ~1
    total = noise_prob + music_prob + speech_prob + 1e-9
    features["noise_probability"] = round(noise_prob / total, 4)
    features["music_probability"] = round(music_prob / total, 4)
    features["speech_probability"] = round(speech_prob / total, 4)

    return features


def score_quality(loudness_features: dict, duration: float, config: dict) -> float:
    """
    Compute a quality score 0.0–1.0.
    Penalizes silence, clipping, very short/long files.
    """
    score = 1.0

    silence_ratio = loudness_features.get("silence_ratio", 0)
    clipping_ratio = loudness_features.get("clipping_ratio", 0)
    rms = loudness_features.get("rms", 0)

    max_silence = config.get("max_silence_ratio", 0.6)
    min_rms = config.get("min_rms", 0.01)
    clip_thresh = config.get("clipping_threshold", 0.99)
    min_dur = config.get("min_duration_sec", 3.0)
    max_dur = config.get("max_duration_sec", 300.0)

    if silence_ratio > max_silence:
        score -= 0.3
    if clipping_ratio > 0.01:
        score -= 0.2
    if rms < min_rms:
        score -= 0.3
    if duration < min_dur or duration > max_dur:
        score -= 0.2

    return round(max(0.0, min(1.0, score)), 4)


def score_world_fit(features: dict, loudness: dict) -> float:
    """
    Score how well a sound fits the Becoming sonic world (0.0–1.0).
    Favors atmospheric, non-speech, non-clipped audio.
    """
    score = 0.5

    music_prob = features.get("music_probability", 0)
    noise_prob = features.get("noise_probability", 0)
    speech_prob = features.get("speech_probability", 0)
    tonal = features.get("tonal_confidence", 0) or 0
    silence_ratio = loudness.get("silence_ratio", 0)
    clipping_ratio = loudness.get("clipping_ratio", 0)

    # atmospheric / musical content preferred
    score += music_prob * 0.3
    score += tonal * 0.2

    # penalize speech and clipping
    score -= speech_prob * 0.4
    score -= clipping_ratio * 0.3

    # penalize excessive silence
    if silence_ratio > 0.5:
        score -= 0.2

    return round(max(0.0, min(1.0, score)), 4)


def score_pulse_fit(features: dict) -> float:
    """Score fit for pulse (rhythmic) state."""
    tempo = features.get("tempo_estimate") or 0
    music_prob = features.get("music_probability", 0)

    score = 0.0
    if 60 < tempo < 180:
        score += 0.5
    score += music_prob * 0.5
    return round(max(0.0, min(1.0, score)), 4)


def score_drift_fit(features: dict, loudness: dict) -> float:
    """Score fit for drift (atmospheric/drone) state."""
    tonal = features.get("tonal_confidence", 0) or 0
    zcr = features.get("zero_crossing_rate_mean", 0)
    silence_ratio = loudness.get("silence_ratio", 0)

    score = tonal * 0.5
    score += (1 - min(zcr * 10, 1)) * 0.3  # low ZCR = slower, more ambient
    score -= silence_ratio * 0.2

    return round(max(0.0, min(1.0, score)), 4)
