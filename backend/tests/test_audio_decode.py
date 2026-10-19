"""Regression: real audio decoding must remain compatible with faster-whisper."""
import wave
from faster_whisper.audio import decode_audio


def test_whisper_decodes_pcm_wav(tmp_path):
    audio = tmp_path / 'silence.wav'
    with wave.open(str(audio), 'wb') as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(16000)
        stream.writeframes(b'\x00\x00' * 1600)
    samples = decode_audio(str(audio), sampling_rate=16000)
    assert samples.shape == (1600,)
    assert not samples.any()
