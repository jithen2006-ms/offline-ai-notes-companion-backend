"""FastAPI router for lectures, subjects, Android upload, and Gemini note generation."""

import json
import os
from typing import Any
from fastapi import APIRouter, BackgroundTasks, HTTPException, status
from app.db import DatabaseConfigurationError, get_connection
from app.models.upload import AndroidLectureUploadRequest
from app.services.gemini_service import generate_study_material_for_lecture

router = APIRouter(prefix="/api", tags=["lectures"])


@router.get("/health")
def health_check() -> dict[str, str]:
    """Lightweight health check endpoint for Android Test Ping."""
    return {"status": "ok"}


def fetch_all(query: str, params: tuple = ()) -> list[dict[str, Any]]:
    """Execute a SELECT query and return list of dicts."""
    try:
        with get_connection() as conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(query, params)
            rows = cursor.fetchall()
            return rows or []
    except DatabaseConfigurationError as err:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database configuration error: {err}",
        )
    except Exception as err:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error: {err}",
        )


def execute_write(query: str, params: tuple = ()) -> int:
    """Execute INSERT/UPDATE/DELETE statement and commit."""
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            affected = cursor.rowcount
            conn.commit()
            return affected
    except DatabaseConfigurationError as err:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database configuration error: {err}",
        )
    except Exception as err:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error: {err}",
        )


@router.get("/lectures")
def get_lectures() -> list[dict[str, Any]]:
    """Retrieve lightweight lecture metadata for My Lectures library view."""
    query = """
        SELECT 
            l.id,
            l.title,
            s.name AS subject,
            s.code AS subject_code,
            l.lecture_date,
            l.duration_seconds,
            l.status,
            l.created_at,
            l.updated_at
        FROM lectures l
        LEFT JOIN subjects s ON l.subject_id = s.id
        ORDER BY l.created_at DESC, l.id DESC
    """
    rows = fetch_all(query)
    for row in rows:
        if row.get("duration_seconds") is not None:
            row["duration_seconds"] = float(row["duration_seconds"])
        if row.get("lecture_date") is not None:
            row["lecture_date"] = str(row["lecture_date"])
        if row.get("created_at") is not None:
            row["created_at"] = str(row["created_at"])
        if row.get("updated_at") is not None:
            row["updated_at"] = str(row["updated_at"])
    return rows


@router.get("/subjects")
def get_subjects() -> list[dict[str, Any]]:
    """Retrieve all subjects from MySQL."""
    query = """
        SELECT id, name, code, created_at
        FROM subjects
        ORDER BY name ASC
    """
    rows = fetch_all(query)
    for row in rows:
        if row.get("created_at") is not None:
            row["created_at"] = str(row["created_at"])
    return rows


@router.get("/lectures/{lecture_id}")
def get_lecture_by_id(lecture_id: int) -> dict[str, Any]:
    """Retrieve specific lecture details, parsed study material, and transcript segments."""
    query = """
        SELECT 
            l.id,
            l.title,
            s.name AS subject,
            s.code AS subject_code,
            l.lecture_date,
            l.duration_seconds,
            l.status,
            l.created_at,
            l.updated_at
        FROM lectures l
        LEFT JOIN subjects s ON l.subject_id = s.id
        WHERE l.id = %s
    """
    rows = fetch_all(query, (lecture_id,))
    if not rows:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Lecture with ID {lecture_id} not found.",
        )
    lecture = rows[0]
    if lecture.get("duration_seconds") is not None:
        lecture["duration_seconds"] = float(lecture["duration_seconds"])
    if lecture.get("lecture_date") is not None:
        lecture["lecture_date"] = str(lecture["lecture_date"])
    if lecture.get("created_at") is not None:
        lecture["created_at"] = str(lecture["created_at"])
    if lecture.get("updated_at") is not None:
        lecture["updated_at"] = str(lecture["updated_at"])

    # Fetch notes study_material_json if exists
    notes_rows = fetch_all(
        "SELECT model_name, study_material_json, generated_at FROM notes WHERE lecture_id = %s ORDER BY id DESC LIMIT 1",
        (lecture_id,),
    )
    if notes_rows:
        n_row = notes_rows[0]
        lecture["notes"] = n_row
        try:
            lecture["material"] = json.loads(n_row["study_material_json"])
        except Exception:
            pass

    # Fetch transcript segments if exist
    t_rows = fetch_all("SELECT id FROM transcripts WHERE lecture_id = %s LIMIT 1", (lecture_id,))
    if t_rows:
        transcript_id = t_rows[0]["id"]
        segments = fetch_all(
            "SELECT segment_id AS id, start_time AS start, end_time AS end, text FROM transcript_segments WHERE transcript_id = %s ORDER BY start_time, segment_id",
            (transcript_id,),
        )
        for seg in segments:
            seg["start"] = float(seg["start"])
            seg["end"] = float(seg["end"])
        lecture["segments"] = segments

    return lecture


@router.delete("/lectures/{lecture_id}")
def delete_lecture(lecture_id: int) -> dict[str, Any]:
    """Delete lecture from MySQL database using CASCADE."""
    affected = execute_write("DELETE FROM lectures WHERE id = %s", (lecture_id,))
    if affected == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Lecture with ID {lecture_id} not found.",
        )
    return {"success": True, "deleted_id": lecture_id}


@router.post("/lectures/upload", status_code=status.HTTP_201_CREATED)
def upload_lecture_transcript(
    payload: AndroidLectureUploadRequest,
    background_tasks: BackgroundTasks,
) -> dict[str, Any]:
    """Receive Android lecture transcript upload and store in MySQL."""
    norm = payload.normalize()
    if not norm["transcript"] and not norm["segments"]:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Transcript content or segments cannot be empty.",
        )

    user_id = norm["user_id"]
    subject_name = norm["subject_name"]
    title = norm["title"]
    lecture_date = norm["lecture_date"]
    start_time = norm["start_time"]
    end_time = norm["end_time"]
    duration_seconds = norm["duration_seconds"]
    transcript_text = norm["transcript"]
    segments = norm["segments"]

    try:
        with get_connection() as conn:
            cursor = conn.cursor(dictionary=True)

            # 1. Ensure user exists
            cursor.execute("SELECT id FROM users WHERE id = %s", (user_id,))
            user_row = cursor.fetchone()
            if not user_row:
                cursor.execute(
                    "INSERT INTO users (id, name, email) VALUES (%s, %s, %s)",
                    (user_id, "Student", f"student_{user_id}@companion.local"),
                )
                user_id = cursor.lastrowid or user_id

            # 2. Identify or create subject
            cursor.execute(
                "SELECT id FROM subjects WHERE user_id = %s AND name = %s LIMIT 1",
                (user_id, subject_name),
            )
            subject_row = cursor.fetchone()
            if subject_row:
                subject_id = subject_row["id"]
            else:
                cursor.execute(
                    "INSERT INTO subjects (user_id, name, code) VALUES (%s, %s, %s)",
                    (user_id, subject_name, subject_name[:10].upper()),
                )
                subject_id = cursor.lastrowid

            # 3. Duplicate Upload Check (Idempotency)
            cursor.execute(
                """
                SELECT l.id, l.status 
                FROM lectures l
                WHERE l.user_id = %s 
                  AND l.subject_id = %s 
                  AND (l.lecture_date = %s OR l.lecture_date IS NULL)
                  AND (ABS(l.duration_seconds - %s) < 1.0 OR l.title = %s)
                LIMIT 1
                """,
                (user_id, subject_id, lecture_date, duration_seconds, title),
            )
            dup_row = cursor.fetchone()
            if dup_row:
                conn.commit()
                return {
                    "success": True,
                    "lecture_id": dup_row["id"],
                    "status": dup_row["status"],
                    "duplicate": True,
                    "message": "Duplicate transcript upload detected. Returned existing lecture record.",
                }

            # 4. Insert Lecture Record
            cursor.execute(
                """
                INSERT INTO lectures 
                    (user_id, subject_id, title, lecture_date, start_time, end_time, duration_seconds, status)
                VALUES 
                    (%s, %s, %s, %s, %s, %s, %s, 'TRANSCRIBED')
                """,
                (user_id, subject_id, title, lecture_date, start_time, end_time, duration_seconds),
            )
            lecture_id = cursor.lastrowid

            # 5. Insert Transcript Record
            cursor.execute(
                "INSERT INTO transcripts (lecture_id, language, status) VALUES (%s, 'en', 'READY')",
                (lecture_id,),
            )
            transcript_id = cursor.lastrowid

            # 6. Insert Transcript Segments
            for seg in segments:
                cursor.execute(
                    """
                    INSERT INTO transcript_segments 
                        (transcript_id, segment_id, start_time, end_time, text)
                    VALUES 
                        (%s, %s, %s, %s, %s)
                    """,
                    (transcript_id, seg["id"], seg["start"], seg["end"], seg["text"]),
                )

            # 7. Insert Processing Jobs
            cursor.execute(
                """
                INSERT INTO processing_jobs 
                    (lecture_id, job_type, status, started_at, completed_at)
                VALUES 
                    (%s, 'TRANSCRIPTION', 'COMPLETED', NOW(), NOW())
                """,
                (lecture_id,),
            )
            cursor.execute(
                """
                INSERT INTO processing_jobs 
                    (lecture_id, job_type, status)
                VALUES 
                    (%s, 'STUDY_MATERIAL_GENERATION', 'QUEUED')
                """,
                (lecture_id,),
            )

            conn.commit()

            # Enqueue Gemini study material generation in BackgroundTasks if GEMINI_API_KEY is available
            if os.environ.get("GEMINI_API_KEY"):
                background_tasks.add_task(generate_study_material_for_lecture, lecture_id)

            return {
                "success": True,
                "lecture_id": lecture_id,
                "status": "TRANSCRIBED",
                "message": "Lecture transcript uploaded and stored successfully.",
            }

    except DatabaseConfigurationError as err:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database configuration error: {err}",
        )
    except Exception as err:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database storage error: {err}",
        )


@router.post("/lectures/{lecture_id}/generate-notes")
def trigger_generate_notes(lecture_id: int, background_tasks: BackgroundTasks) -> dict[str, Any]:
    """Manually trigger or retry Gemini study material generation for a stored lecture."""
    background_tasks.add_task(generate_study_material_for_lecture, lecture_id)
    return {"success": True, "lecture_id": lecture_id, "message": "Gemini note generation queued."}
