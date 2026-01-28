"""Модуль голосового ввода: запись с микрофона + распознавание через Whisper."""

import tempfile
import wave
import struct
from pathlib import Path

import numpy as np
import sounddevice as sd


# Whisper загружается лениво (модель ~140MB при первом запуске)
_whisper_model = None


def _get_whisper_model(model_name: str = "base"):
    """Загружает модель Whisper (кэшируется)."""
    global _whisper_model
    if _whisper_model is None:
        import whisper
        _whisper_model = whisper.load_model(model_name)
    return _whisper_model


def record_audio(duration: float = 5.0, sample_rate: int = 16000) -> np.ndarray:
    """Записывает аудио с микрофона.

    Args:
        duration: длительность записи в секундах.
        sample_rate: частота дискретизации (16000 оптимально для Whisper).

    Returns:
        numpy array с аудиоданными (float32, mono).
    """
    audio = sd.rec(
        int(duration * sample_rate),
        samplerate=sample_rate,
        channels=1,
        dtype="float32",
    )
    sd.wait()
    return audio.flatten()


def save_wav(audio: np.ndarray, path: str, sample_rate: int = 16000) -> None:
    """Сохраняет numpy-массив как WAV-файл."""
    audio_int16 = (audio * 32767).astype(np.int16)
    with wave.open(path, "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(audio_int16.tobytes())


def recognize(audio: np.ndarray, model_name: str = "base", language: str = "ru") -> str:
    """Распознаёт речь из numpy-массива через Whisper.

    Args:
        audio: аудиоданные (float32, 16kHz, mono).
        model_name: модель Whisper (tiny/base/small/medium/large).
        language: язык распознавания.

    Returns:
        Распознанный текст.
    """
    model = _get_whisper_model(model_name)
    result = model.transcribe(audio, language=language, fp16=False)
    return result["text"].strip()


def voice_input(duration: float = 5.0, model_name: str = "base", language: str = "ru") -> str:
    """Записывает голос и возвращает распознанный текст.

    Args:
        duration: длительность записи в секундах.
        model_name: модель Whisper.
        language: язык.

    Returns:
        Распознанный текст или пустая строка при ошибке.
    """
    audio = record_audio(duration)
    text = recognize(audio, model_name=model_name, language=language)
    return text
