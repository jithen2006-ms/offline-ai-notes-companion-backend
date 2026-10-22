"""Automated backend test suite for Android timestamped transcript -> Gemini 3.5 Flash-Lite -> MySQL pipeline."""

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
from app.services.gemini_service import (
    StudyMaterial,
    StudyItem,
    Definition,
    Question,
    SourceRef,
    generate_study_material_for_lecture,
)

client = TestClient(app)


def test_android_timestamped_segments_and_gemini_pipeline():
    """Test full end-to-end flow: Android timestamped segments upload -> MySQL -> Gemini -> Study Material -> MySQL READY."""
    # 1. Android payload containing genuine timestamped segments
    payload = {
        "userId": "1",
        "course_name": "Database Systems",
        "date": "2026-08-25",
        "startTime": "09:00:00",
        "endTime": "10:00:00",
        "duration_seconds": 3600.0,
        "session_status": "COMPLETED",
        "transcript": {
            "segments": [
                {
                    "id": 1,
                    "start": 0.0,
                    "end": 12.5,
                    "text": "Welcome to Database Systems. Today we cover relational database management system fundamentals."
                },
                {
                    "id": 2,
                    "start": 13.0,
                    "end": 28.0,
                    "text": "A DBMS is software designed to store, retrieve, and manage structured data efficiently."
                },
                {
                    "id": 3,
                    "start": 29.0,
                    "end": 45.0,
                    "text": "Primary keys uniquely identify each row in a database table. Foreign keys establish relational links between tables."
                }
            ]
        }
    }

    # Upload via POST /api/lectures/upload
    response = client.post("/api/lectures/upload", json=payload)
    assert response.status_code == 201, f"Expected 201, got {response.status_code}: {response.text}"
    data = response.json()
    assert data["success"] is True
    lecture_id = data["lecture_id"]

    try:
        # 2. Verify genuine transcript segments stored in MySQL
        with get_connection() as conn:
            cursor = conn.cursor(dictionary=True, buffered=True)

            cursor.execute("SELECT id, status FROM transcripts WHERE lecture_id = %s", (lecture_id,))
            t_row = cursor.fetchone()
            assert t_row is not None, "Transcript record missing in MySQL"
            transcript_id = t_row["id"]

            cursor.execute(
                "SELECT segment_id, start_time, end_time, text FROM transcript_segments WHERE transcript_id = %s ORDER BY segment_id",
                (transcript_id,),
            )
            segments = cursor.fetchall()
            assert len(segments) == 3, f"Expected 3 segments, got {len(segments)}"
            assert segments[0]["segment_id"] == 1
            assert segments[1]["segment_id"] == 2
            assert segments[2]["segment_id"] == 3
            assert float(segments[0]["start_time"]) == 0.0
            assert float(segments[0]["end_time"]) == 12.5
            assert segments[0]["text"] == payload["transcript"]["segments"][0]["text"]

        # 3. Create mock StudyMaterial grounded in genuine segment IDs {1, 2, 3}
        mock_material = StudyMaterial(
            lecture_overview="Introduction to RDBMS concepts, primary keys, and foreign key relations.",
            summary="A DBMS manages structured data efficiently using primary and foreign key constraints.",
            key_points=[
                StudyItem(
                    content="A DBMS is dedicated software for managing structured data.",
                    source_refs=[SourceRef(segment_id=2)]
                )
            ],
            important_concepts=[
                StudyItem(
                    content="Relational keys link database tables and ensure entity integrity.",
                    source_refs=[SourceRef(segment_id=3)]
                )
            ],
            definitions=[
                Definition(
                    term="DBMS",
                    explanation="Software designed to store, retrieve, and manage structured data efficiently.",
                    source_refs=[SourceRef(segment_id=2)]
                )
            ],
            exam_questions=[
                Question(
                    question="What is the role of a primary key in a relational database?",
                    type="SHORT_ANSWER",
                    source_refs=[SourceRef(segment_id=3)]
                )
            ]
        )

        # 4. Execute Gemini generation service using stored MySQL transcript
        gen_result = generate_study_material_for_lecture(lecture_id=lecture_id, mock_material=mock_material)
        assert gen_result["success"] is True
        assert gen_result["status"] == "READY"
        assert len(gen_result["invalid_segment_ids"]) == 0

        # 5. Verify database persistence in notes, study_items, and source_mappings
        with get_connection() as conn:
            cursor = conn.cursor(dictionary=True, buffered=True)

            # Check lecture status updated to READY
            cursor.execute("SELECT status FROM lectures WHERE id = %s", (lecture_id,))
            lec_status = cursor.fetchone()["status"]
            assert lec_status == "READY"

            # Check notes table
            cursor.execute("SELECT id, model_name, study_material_json FROM notes WHERE lecture_id = %s", (lecture_id,))
            notes_row = cursor.fetchone()
            assert notes_row is not None
            assert notes_row["model_name"] == "gemini-3.5-flash-lite"
            notes_id = notes_row["id"]

            # Check study_items table
            cursor.execute("SELECT id, item_type, content, term, question FROM study_items WHERE notes_id = %s", (notes_id,))
            items = cursor.fetchall()
            assert len(items) >= 4

            # Check source_mappings table
            cursor.execute("SELECT sm.id, sm.transcript_segment_id, ts.segment_id FROM source_mappings sm JOIN transcript_segments ts ON sm.transcript_segment_id = ts.id WHERE ts.transcript_id = %s", (transcript_id,))
            mappings = cursor.fetchall()
            assert len(mappings) >= 4
            mapped_seg_ids = {m["segment_id"] for m in mappings}
            assert mapped_seg_ids.issubset({1, 2, 3})

        # 6. Verify web endpoint GET /api/lectures/{id} returns parsed material and segments
        get_res = client.get(f"/api/lectures/{lecture_id}")
        assert get_res.status_code == 200
        get_data = get_res.json()
        assert get_data["status"] == "READY"
        assert "material" in get_data
        assert get_data["material"]["lecture_overview"] == mock_material.lecture_overview
        assert len(get_data["segments"]) == 3

        print("[OK] Android timestamped segments upload, MySQL storage, Gemini note generation, source mapping, and website API verification succeeded!")

    finally:
        # Cleanup test records from MySQL
        with get_connection() as conn:
            cursor = conn.cursor(buffered=True)
            cursor.execute("DELETE FROM lectures WHERE id = %s", (lecture_id,))
            conn.commit()


if __name__ == "__main__":
    test_android_timestamped_segments_and_gemini_pipeline()
    print("\nALL PIPELINE TESTS PASSED SUCCESSFULLY!")
