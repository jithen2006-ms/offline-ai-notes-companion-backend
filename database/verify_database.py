"""Verify the MySQL schema and core relationships using the real fixtures."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import mysql.connector
from mysql.connector import Error

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "database" / "schema.sql"
MATERIAL_PATH = ROOT / "ai-service" / "data" / "output" / "gemini_dbms_study_material.json"
TRANSCRIPT_PATH = ROOT / "ai-service" / "data" / "output" / "Lec_1_Introduction_to_DBMS_transcript.json"
DATABASE_NAME = os.getenv("DB_NAME", "offline_notes_companion")
TABLES = {
    "users", "subjects", "timetable", "lectures", "audio_metadata", "transcripts",
    "transcript_segments", "lecture_topics", "notes", "study_items", "source_mappings", "processing_jobs",
}


def required_config() -> dict[str, object]:
    missing = [name for name in ("DB_HOST", "DB_USER", "DB_PASSWORD") if not os.getenv(name)]
    if missing:
        raise RuntimeError("Missing required database variables: " + ", ".join(missing))
    return {
        "host": os.environ["DB_HOST"],
        "port": int(os.getenv("DB_PORT", "3306")),
        "user": os.environ["DB_USER"],
        "password": os.environ["DB_PASSWORD"],
    }


def statements() -> list[str]:
    cleaned = []
    for line in SCHEMA_PATH.read_text(encoding="utf-8").splitlines():
        if not line.strip().startswith("--"):
            cleaned.append(line)
    return [statement.strip() for statement in "\n".join(cleaned).split(";") if statement.strip()]


def verify() -> None:
    config = required_config()
    connection = mysql.connector.connect(**config)
    cursor = connection.cursor()
    try:
        for statement in statements():
            cursor.execute(statement)
        connection.commit()
        connection.database = DATABASE_NAME

        cursor.execute("SHOW TABLES")
        actual_tables = {row[0] for row in cursor.fetchall()}
        missing_tables = TABLES - actual_tables
        if missing_tables:
            raise AssertionError(f"Missing tables: {sorted(missing_tables)}")

        with TRANSCRIPT_PATH.open(encoding="utf-8") as transcript_file:
            transcript = json.load(transcript_file)
        with MATERIAL_PATH.open(encoding="utf-8") as material_file:
            material = json.load(material_file)
        segments = transcript["segments"]

        cursor.execute("INSERT INTO users (name, email) VALUES (%s, %s)", ("Verification User", "verify@example.invalid"))
        user_id = cursor.lastrowid
        cursor.execute("INSERT INTO subjects (user_id, name, code) VALUES (%s, %s, %s)", (user_id, "DBMS", "DBMS"))
        subject_id = cursor.lastrowid
        cursor.execute(
            "INSERT INTO timetable (user_id, subject_id, class_title, day_of_week, start_time, end_time) VALUES (%s, %s, %s, %s, %s, %s)",
            (user_id, subject_id, "DBMS fundamentals", 1, "09:00:00", "10:00:00"),
        )
        timetable_id = cursor.lastrowid
        cursor.execute(
            "INSERT INTO lectures (user_id, subject_id, timetable_id, title, duration_seconds, status) VALUES (%s, %s, %s, %s, %s, %s)",
            (user_id, subject_id, timetable_id, "Introduction to DBMS", transcript["audio_duration"], "READY"),
        )
        lecture_id = cursor.lastrowid
        cursor.execute(
            "INSERT INTO audio_metadata (lecture_id, filename, format, duration_seconds, file_size_bytes) VALUES (%s, %s, %s, %s, %s)",
            (lecture_id, "dbms.mp3", "mp3", transcript["audio_duration"], 0),
        )
        cursor.execute("INSERT INTO transcripts (lecture_id, language, status) VALUES (%s, %s, %s)", (lecture_id, "en", "READY"))
        transcript_id = cursor.lastrowid
        for segment in segments:
            cursor.execute(
                "INSERT INTO transcript_segments (transcript_id, segment_id, start_time, end_time, text) VALUES (%s, %s, %s, %s, %s)",
                (transcript_id, segment["id"], segment["start"], segment["end"], segment["text"]),
            )
        cursor.execute("SELECT segment_id FROM transcript_segments WHERE transcript_id = %s ORDER BY start_time, segment_id", (transcript_id,))
        assert [row[0] for row in cursor.fetchall()] == [segment["id"] for segment in segments]

        cursor.execute(
            "INSERT INTO notes (lecture_id, model_name, study_material_json, generated_at) VALUES (%s, %s, %s, NOW())",
            (lecture_id, material["model"], json.dumps(material["study_material"])),
        )
        notes_id = cursor.lastrowid
        first_item = material["study_material"]["key_points"][0]
        cursor.execute(
            "INSERT INTO study_items (notes_id, item_type, content, item_order) VALUES (%s, %s, %s, %s)",
            (notes_id, "KEY_POINT", first_item["content"], 0),
        )
        study_item_id = cursor.lastrowid
        source_segment_id = first_item["source_refs"][0]["segment_id"]
        cursor.execute("SELECT id FROM transcript_segments WHERE transcript_id = %s AND segment_id = %s", (transcript_id, source_segment_id))
        transcript_segment_id = cursor.fetchone()[0]
        cursor.execute("INSERT INTO source_mappings (study_item_id, transcript_segment_id) VALUES (%s, %s)", (study_item_id, transcript_segment_id))
        cursor.execute("INSERT INTO processing_jobs (lecture_id, job_type, status) VALUES (%s, %s, %s)", (lecture_id, "TRANSCRIPTION", "QUEUED"))
        job_id = cursor.lastrowid
        cursor.execute("UPDATE processing_jobs SET status = 'COMPLETED', started_at = NOW(), completed_at = NOW() WHERE id = %s", (job_id,))

        cursor.execute("SELECT JSON_LENGTH(study_material_json) FROM notes WHERE id = %s", (notes_id,))
        assert cursor.fetchone()[0] == len(material["study_material"])

        checks = [
            ("duplicate segment id", "INSERT INTO transcript_segments (transcript_id, segment_id, start_time, end_time, text) VALUES (%s, %s, 0, 1, 'duplicate')", (transcript_id, segments[0]["id"])),
            ("invalid source mapping", "INSERT INTO source_mappings (study_item_id, transcript_segment_id) VALUES (%s, 999999999)", (study_item_id,)),
        ]
        for label, statement, parameters in checks:
            try:
                cursor.execute(statement, parameters)
                connection.rollback()
                raise AssertionError(f"{label} was accepted")
            except Error:
                connection.rollback()

        cursor.execute("DELETE FROM users WHERE id = %s", (user_id,))
        connection.commit()
        print("database connection: OK")
        print("schema and tables: OK")
        print("fixture CRUD and chronological retrieval: OK")
        print("JSON preservation: OK")
        print("source mapping: OK")
        print("foreign-key and duplicate-segment rejection: OK")
    finally:
        cursor.close()
        connection.close()


if __name__ == "__main__":
    try:
        verify()
    except Exception as error:
        print(f"verification failed: {error}", file=sys.stderr)
        raise SystemExit(1)
