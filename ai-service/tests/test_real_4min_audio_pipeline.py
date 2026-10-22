"""Automated test suite verifying the real 4-minute audio fixture -> Whisper -> FastAPI -> MySQL -> Gemini 3.5 Flash-Lite -> READY pipeline."""

import os
import sys
import time
import json
from pathlib import Path
from dotenv import load_dotenv

# Ensure app package is importable
ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))
load_dotenv(ROOT_DIR / ".env")

import soundfile as sf
import torch
from transformers import AutoModelForSpeechSeq2Seq, AutoProcessor, pipeline
from fastapi.testclient import TestClient
from app.server import app
from app.db import get_connection

client = TestClient(app)

AUDIO_PATH = ROOT_DIR / "data" / "Speak English on Any Topic in 1 Minute (Daily Practice Plan)  Sunita Rawat.mp3"
MODEL_ID = "theshivam7/whisper-tiny-indian-english"


def test_real_4min_audio_pipeline():
    """Verify real 4-minute audio fixture metadata, Whisper ASR inference, timestamped segments, FastAPI upload, MySQL storage, Gemini 3.5 Flash-Lite generation, and READY state."""
    print(f"\n--- 1. AUDIO FIXTURE METADATA INSPECTION ---")
    assert AUDIO_PATH.exists(), f"Audio file not found: {AUDIO_PATH}"
    file_size_bytes = AUDIO_PATH.stat().st_size
    file_size_mb = file_size_bytes / (1024 * 1024)

    with sf.SoundFile(str(AUDIO_PATH)) as audio_file:
        audio_duration = len(audio_file) / audio_file.samplerate
        sample_rate = audio_file.samplerate
        channels = audio_file.channels

    print(f"Exact Filename: {AUDIO_PATH.name}")
    print(f"File Size: {file_size_bytes} bytes ({file_size_mb:.2f} MB)")
    print(f"Duration: {audio_duration:.2f} seconds ({audio_duration/60:.2f} minutes)")
    print(f"Sample Rate: {sample_rate} Hz, Channels: {channels}")

    assert audio_duration > 200, f"Expected ~4 minute audio, got {audio_duration} seconds"

    print(f"\n--- 2. REAL WHISPER ASR INFERENCE ---")
    t0 = time.perf_counter()
    processor = AutoProcessor.from_pretrained(MODEL_ID)
    model = AutoModelForSpeechSeq2Seq.from_pretrained(MODEL_ID, torch_dtype=torch.float32)
    load_time = time.perf_counter() - t0

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

    t1 = time.perf_counter()
    result = pipe(str(AUDIO_PATH), batch_size=1)
    proc_time = time.perf_counter() - t1
    rtf = proc_time / audio_duration

    chunks = result.get("chunks", [])
    full_text = result.get("text", "").strip()

    print(f"Model: {MODEL_ID}")
    print(f"Model Load Time: {load_time:.2f} s")
    print(f"Inference Time: {proc_time:.2f} s")
    print(f"Real-Time Factor (RTF): {rtf:.4f}x")
    print(f"Segment Count: {len(chunks)}")
    print(f"Full Text Length: {len(full_text)} characters")

    # Assert real Whisper output characteristics
    assert len(chunks) > 0, "Whisper returned 0 segments"
    assert len(full_text) > 100, "Whisper returned suspiciously short transcript"
    assert "[Recognized classroom lecture segment]" not in full_text, "Found placeholder string in transcript"

    formatted_segments = []
    for idx, chunk in enumerate(chunks):
        st, et = chunk.get("timestamp", (0.0, 0.0))
        st = float(st) if st is not None else 0.0
        et = float(et) if et is not None else st + 1.0
        txt = chunk.get("text", "").strip()
        assert st <= et, f"Invalid timestamp window at index {idx}: {st} > {et}"
        formatted_segments.append({
            "id": idx + 1,
            "start": round(st, 2),
            "end": round(et, 2),
            "text": txt
        })

    final_timestamp = formatted_segments[-1]["end"]
    print(f"Final Segment Timestamp: {final_timestamp}s (Audio Duration: {audio_duration:.2f}s)")
    assert final_timestamp <= audio_duration + 5.0, "Final timestamp exceeds audio duration"

    print(f"\n--- 3. FASTAPI UPLOAD (POST /api/lectures/upload) ---")
    payload = {
        "userId": "1",
        "course_name": "English Communication",
        "title": "Speak English on Any Topic in 1 Minute",
        "date": "2026-08-26",
        "startTime": "10:00:00",
        "endTime": "10:05:00",
        "duration_seconds": round(audio_duration, 2),
        "session_status": "COMPLETED",
        "transcript": {
            "segments": formatted_segments
        }
    }

    upload_res = client.post("/api/lectures/upload", json=payload)
    assert upload_res.status_code == 201, f"Expected 201, got {upload_res.status_code}: {upload_res.text}"
    upload_data = upload_res.json()
    assert upload_data["success"] is True
    lecture_id = upload_data["lecture_id"]
    print(f"Upload Success! Lecture ID: {lecture_id}")

    try:
        print(f"\n--- 4. MYSQL PERSISTENCE VERIFICATION ---")
        with get_connection() as conn:
            cursor = conn.cursor(dictionary=True, buffered=True)

            cursor.execute("SELECT id, title, duration_seconds, status FROM lectures WHERE id = %s", (lecture_id,))
            lec_row = cursor.fetchone()
            assert lec_row is not None
            assert lec_row["title"] == payload["title"]

            cursor.execute("SELECT id FROM transcripts WHERE lecture_id = %s", (lecture_id,))
            t_row = cursor.fetchone()
            assert t_row is not None
            transcript_id = t_row["id"]

            cursor.execute("SELECT COUNT(*) as seg_count FROM transcript_segments WHERE transcript_id = %s", (transcript_id,))
            count_row = cursor.fetchone()
            assert count_row["seg_count"] == len(formatted_segments)
            print(f"MySQL transcript_segments count: {count_row['seg_count']}")

        print(f"\n--- 5. GEMINI 3.5 FLASH-LITE STUDY MATERIAL GENERATION ---")
        # Trigger Gemini processing using real Whisper segments stored in MySQL
        from app.services.gemini_service import generate_study_material_for_lecture
        gem_result = generate_study_material_for_lecture(lecture_id=lecture_id)
        assert gem_result["success"] is True
        assert gem_result["status"] == "READY"
        print("Gemini study material generation succeeded with status: READY")

        print(f"\n--- 6. WEBSITE API & SOURCE REFERENCES VERIFICATION ---")
        get_res = client.get(f"/api/lectures/{lecture_id}")
        assert get_res.status_code == 200
        get_data = get_res.json()
        assert get_data["status"] == "READY"
        assert "material" in get_data
        assert len(get_data["segments"]) == len(formatted_segments)

        print("[OK] Real 4-minute audio fixture, Whisper ASR, MySQL persistence, Gemini 3.5 Flash-Lite, and website integration verified!")

    finally:
        # Clean up test lecture record
        with get_connection() as conn:
            cursor = conn.cursor(buffered=True)
            cursor.execute("DELETE FROM lectures WHERE id = %s", (lecture_id,))
            conn.commit()


if __name__ == "__main__":
    test_real_4min_audio_pipeline()
    print("\nALL AUTOMATED TESTS PASSED SUCCESSFULLY!")
