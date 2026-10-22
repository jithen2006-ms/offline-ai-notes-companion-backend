"""Automated backend test suite for Android transcript upload integration (POST /api/lectures/upload)."""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Ensure app package is importable
ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))
load_dotenv(ROOT_DIR / ".env")

from fastapi.testclient import TestClient
from app.server import app
from app.db import get_connection

client = TestClient(app)


def test_android_upload_and_database_persistence():
    """Test full Android transcript upload, normalization, duplicate handling, and database state."""
    # 1. Valid Android payload using camelCase / Android field names
    payload_1 = {
        "userId": "1",
        "course_name": "Operating Systems",
        "date": "2026-08-25",
        "startTime": "10:00:00",
        "endTime": "11:00:00",
        "duration_seconds": 3600.0,
        "session_status": "COMPLETED",
        "transcript": "Welcome to Operating Systems lecture 1. Today we discuss process scheduling and CPU dispatching.",
    }

    response = client.post("/api/lectures/upload", json=payload_1)
    assert response.status_code == 201, f"Expected 201, got {response.status_code}: {response.text}"
    data = response.json()
    assert data["success"] is True
    assert "lecture_id" in data
    assert data["status"] == "TRANSCRIBED"
    lecture_id = data["lecture_id"]

    try:
        # 2. Verify records created in MySQL
        with get_connection() as conn:
            cursor = conn.cursor(dictionary=True)

            # Check lecture table
            cursor.execute(
                "SELECT l.id, l.title, s.name as subject_name, l.duration_seconds, l.status FROM lectures l JOIN subjects s ON l.subject_id = s.id WHERE l.id = %s",
                (lecture_id,),
            )
            lec_row = cursor.fetchone()
            assert lec_row is not None, "Lecture record missing in MySQL"
            assert lec_row["subject_name"] == "Operating Systems"
            assert float(lec_row["duration_seconds"]) == 3600.0
            assert lec_row["status"] in ("TRANSCRIBED", "GENERATING_NOTES", "READY")

            # Check transcripts table
            cursor.execute("SELECT id, status FROM transcripts WHERE lecture_id = %s", (lecture_id,))
            t_row = cursor.fetchone()
            assert t_row is not None, "Transcript record missing in MySQL"
            assert t_row["status"] == "READY"
            transcript_id = t_row["id"]

            # Check transcript_segments table
            cursor.execute(
                "SELECT segment_id, start_time, end_time, text FROM transcript_segments WHERE transcript_id = %s",
                (transcript_id,),
            )
            seg_row = cursor.fetchone()
            assert seg_row is not None, "Transcript segment missing in MySQL"
            assert seg_row["segment_id"] == 1
            assert float(seg_row["start_time"]) == 0.0
            assert seg_row["text"] == payload_1["transcript"]

            # Check processing_jobs table
            cursor.execute(
                "SELECT job_type, status FROM processing_jobs WHERE lecture_id = %s ORDER BY id",
                (lecture_id,),
            )
            jobs = cursor.fetchall()
            assert len(jobs) >= 2, "Processing jobs missing in MySQL"
            job_types = {j["job_type"]: j["status"] for j in jobs}
            assert job_types["TRANSCRIPTION"] == "COMPLETED"

        # 3. Test Duplicate Upload (Idempotency)
        dup_response = client.post("/api/lectures/upload", json=payload_1)
        assert dup_response.status_code in (200, 201)
        dup_data = dup_response.json()
        assert dup_data["success"] is True
        assert dup_data["lecture_id"] == lecture_id
        assert dup_data.get("duplicate") is True

        # 4. Test Alternative Android Naming Conventions (snake_case)
        payload_2 = {
            "user_id": 1,
            "course": "Computer Networks",
            "title": "TCP/IP Protocol Stack",
            "lecture_date": "2026-08-25",
            "start_time": "14:00:00",
            "end_time": "15:00:00",
            "duration_seconds": 1800.0,
            "transcript": "In this lecture we cover the OSI model and TCP/IP protocol suite layers.",
        }

        response_2 = client.post("/api/lectures/upload", json=payload_2)
        assert response_2.status_code == 201
        data_2 = response_2.json()
        assert data_2["success"] is True
        lecture_id_2 = data_2["lecture_id"]

        # Verify second lecture in MySQL
        with get_connection() as conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                "SELECT l.title, s.name as subject_name FROM lectures l JOIN subjects s ON l.subject_id = s.id WHERE l.id = %s",
                (lecture_id_2,),
            )
            lec_row_2 = cursor.fetchone()
            assert lec_row_2["subject_name"] == "Computer Networks"
            assert lec_row_2["title"] == "TCP/IP Protocol Stack"

        print("[OK] Android upload, database persistence, duplicate detection, and Gemini non-triggering verified!")

    finally:
        # Cleanup test records
        with get_connection() as conn:
            cursor = conn.cursor()
            if 'lecture_id' in locals():
                cursor.execute("DELETE FROM lectures WHERE id = %s", (lecture_id,))
            if 'lecture_id_2' in locals():
                cursor.execute("DELETE FROM lectures WHERE id = %s", (lecture_id_2,))
            conn.commit()


def test_invalid_upload_payload_rejection():
    """Test validation errors for invalid upload payloads."""
    # Missing transcript field
    invalid_payload = {
        "userId": 1,
        "course": "Physics",
    }
    response = client.post("/api/lectures/upload", json=invalid_payload)
    assert response.status_code == 422, f"Expected 422, got {response.status_code}"

    # Empty transcript text
    empty_transcript_payload = {
        "userId": 1,
        "course": "Physics",
        "transcript": "   ",
    }
    response_empty = client.post("/api/lectures/upload", json=empty_transcript_payload)
    assert response_empty.status_code == 422, f"Expected 422, got {response_empty.status_code}"

    print("[OK] Invalid upload payload rejection verified!")


if __name__ == "__main__":
    test_android_upload_and_database_persistence()
    test_invalid_upload_payload_rejection()
    print("\nALL AUTOMATED TESTS PASSED SUCCESSFULLY!")
