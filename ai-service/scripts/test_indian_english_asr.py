import json
import time
from pathlib import Path

import soundfile as sf
import torch
from transformers import AutoModelForSpeechSeq2Seq, AutoProcessor, pipeline

MODEL_ID = "theshivam7/whisper-tiny-indian-english"
TEST_DIR = Path(r"C:\Users\ashok\OneDrive\Desktop\offline-ai-notes-companion\tests")
OUTPUT_DIR = Path(r"C:\Users\ashok\OneDrive\Desktop\offline-ai-notes-companion\ai-service\data\output")
TXT_PATH = OUTPUT_DIR / "sample_indian_english.txt"
JSON_PATH = OUTPUT_DIR / "sample_indian_english.json"


def resolve_audio_path():
    candidates = list(TEST_DIR.glob("*.mp3")) + list(TEST_DIR.glob("*.wav")) + list(TEST_DIR.glob("*.m4a"))
    if not candidates:
        raise FileNotFoundError(f"No audio file found in {TEST_DIR}")

    preferred = [
        p for p in candidates
        if "Speak English on Any Topic" in p.name and "Sunita Rawat" in p.name
    ]
    if preferred:
        return preferred[0]

    return candidates[0]


def normalize_segments(result):
    chunks = result.get("chunks") if isinstance(result, dict) else None
    if chunks:
        segments = []
        for idx, chunk in enumerate(chunks):
            start, end = chunk.get("timestamp", (None, None))
            text = chunk.get("text", "")
            segments.append({
                "id": idx,
                "start": float(start) if start is not None else 0.0,
                "end": float(end) if end is not None else 0.0,
                "text": text,
            })
        return segments

    if isinstance(result, dict) and "segments" in result:
        return result["segments"]

    text = result.get("text", "") if isinstance(result, dict) else str(result)
    return [{"id": 0, "start": 0.0, "end": 0.0, "text": text}]


def main():
    AUDIO_PATH = resolve_audio_path()
    if not AUDIO_PATH.exists():
        raise FileNotFoundError(f"Audio file not found: {AUDIO_PATH}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    with sf.SoundFile(str(AUDIO_PATH)) as audio_file:
        audio_duration = len(audio_file) / audio_file.samplerate

    start_loading = time.perf_counter()
    processor = AutoProcessor.from_pretrained(MODEL_ID)
    model = AutoModelForSpeechSeq2Seq.from_pretrained(
        MODEL_ID,
        torch_dtype=torch.float32,
    )
    load_time = time.perf_counter() - start_loading

    pipe = pipeline(
        "automatic-speech-recognition",
        model=model,
        tokenizer=processor.tokenizer,
        feature_extractor=processor.feature_extractor,
        device="cpu",
        torch_dtype=torch.float32,
        chunk_length_s=30,
        stride_length_s=5,
        return_timestamps=True,
    )

    start_transcription = time.perf_counter()
    result = pipe(str(AUDIO_PATH), batch_size=1)
    transcription_time = time.perf_counter() - start_transcription

    total_time = load_time + transcription_time
    ratio = total_time / audio_duration if audio_duration > 0 else 0.0
    segments = normalize_segments(result)

    text = result.get("text", "") if isinstance(result, dict) else str(result)
    TXT_PATH.write_text(text, encoding="utf-8")

    payload = {
        "model": MODEL_ID,
        "audio_duration": round(audio_duration, 4),
        "model_loading_time": round(load_time, 4),
        "transcription_time": round(transcription_time, 4),
        "total_processing_time": round(total_time, 4),
        "processing_audio_ratio": round(ratio, 4),
        "segments": segments,
        "device": "cpu",
        "dtype": "float32",
    }
    JSON_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"audio_duration={audio_duration}")
    print(f"model_loading_time={load_time}")
    print(f"transcription_time={transcription_time}")
    print(f"total_processing_time={total_time}")
    print(f"processing_audio_ratio={ratio}")
    print(f"segment_count={len(segments)}")
    print(f"txt_output={TXT_PATH}")
    print(f"json_output={JSON_PATH}")
    print("transcript:")
    print(text)


if __name__ == "__main__":
    main()
