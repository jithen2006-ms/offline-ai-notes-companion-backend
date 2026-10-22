"""Gemini 3.5 Flash-Lite study material generation service for stored MySQL lecture transcripts."""

import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv
from google import genai
from google.genai import types
from pydantic import BaseModel, Field, ValidationError

ROOT_DIR = Path(__file__).resolve().parents[2]
load_dotenv(ROOT_DIR / ".env")

from app.db import DatabaseConfigurationError, get_connection

MODEL_NAME = "gemini-3.5-flash-lite"


class SourceRef(BaseModel):
    segment_id: int


class StudyItem(BaseModel):
    content: str
    source_refs: list[SourceRef] = Field(default_factory=list)


class Definition(BaseModel):
    term: str
    explanation: str
    source_refs: list[SourceRef] = Field(default_factory=list)


class Question(BaseModel):
    question: str
    type: str
    source_refs: list[SourceRef] = Field(default_factory=list)


class StudyMaterial(BaseModel):
    lecture_overview: str
    summary: str
    key_points: list[StudyItem] = Field(default_factory=list)
    important_concepts: list[StudyItem] = Field(default_factory=list)
    definitions: list[Definition] = Field(default_factory=list)
    examples: list[StudyItem] = Field(default_factory=list)
    formulas: list[StudyItem] = Field(default_factory=list)
    exam_questions: list[Question] = Field(default_factory=list)
    revision_points: list[StudyItem] = Field(default_factory=list)
    assignments: list[StudyItem] = Field(default_factory=list)
    announcements: list[StudyItem] = Field(default_factory=list)


def build_prompt(segments: list[dict[str, Any]]) -> str:
    """Build Gemini prompt from stored transcript segments."""
    transcript_text = "\n".join(
        f"SEGMENT {seg['segment_id']}: {seg['text'].strip()}" for seg in segments
    )
    return f"""You are a college study assistant. Transform the complete transcript below into detailed, useful study material.

Primary source and grounding:
- Use the transcript as the primary source. Do not expand it into a general textbook lesson.
- Limited domain knowledge is allowed only to correct an obvious ASR artifact when the surrounding transcript strongly supports the correction.
- Do not invent facts, definitions, examples, formulas, assignments, announcements, or technical concepts absent from the lecture.
- Preserve uncertainty when an ASR phrase is not clearly recoverable.
- Every study item based on transcript content must include source_refs with only original segment IDs.
- Use only segment IDs present in this transcript. Never invent IDs or timestamps.
- If a category is unsupported by the transcript, return an empty array.

Extraction requirements:
- Extract distinct independent ideas rather than compressing the lecture into a few vague points.
- Include explicit definitions, distinctions, limitations, applications, and lecturer-provided examples in the existing categories.
- Generate useful college-level exam_questions from material actually taught, even when the lecturer did not phrase it as a question. Do not require outside knowledge.
- Keep revision_points concise and different from the summary.
- Assignments and announcements must contain only actual tasks, deadlines, or notices from the transcript.

Transcript:
{transcript_text}
"""


def validate_source_refs(material: StudyMaterial, valid_ids: set[int]) -> list[int]:
    """Validate that all generated source_refs resolve to valid transcript segment IDs."""
    invalid_ids: list[int] = []
    collections = [
        material.key_points,
        material.important_concepts,
        material.definitions,
        material.examples,
        material.formulas,
        material.exam_questions,
        material.revision_points,
        material.assignments,
        material.announcements,
    ]
    for items in collections:
        for item in items:
            for source_ref in item.source_refs:
                if source_ref.segment_id not in valid_ids:
                    invalid_ids.append(source_ref.segment_id)
    return invalid_ids


def request_gemini_study_material(client: genai.Client, prompt: str) -> str:
    """Call Gemini 3.5 Flash-Lite API using structured JSON output schema."""
    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=StudyMaterial,
        temperature=0.2,
    )
    for attempt in range(2):
        try:
            response = client.models.generate_content(
                model=MODEL_NAME,
                contents=prompt,
                config=config,
            )
            if not response.text:
                raise ValueError("Gemini returned an empty response")
            return response.text
        except Exception:
            if attempt == 1:
                raise
    raise RuntimeError("Unreachable request state")


def generate_study_material_for_lecture(
    lecture_id: int,
    client: Optional[Any] = None,
    mock_material: Optional[StudyMaterial] = None,
) -> dict[str, Any]:
    """
    Retrieve stored transcript from MySQL, call Gemini 3.5 Flash-Lite, validate output & source refs,
    and persist generated study material into notes, study_items, and source_mappings tables.
    """
    try:
        with get_connection() as conn:
            cursor = conn.cursor(dictionary=True)

            # 1. Fetch transcript and segments for lecture
            cursor.execute("SELECT id FROM transcripts WHERE lecture_id = %s LIMIT 1", (lecture_id,))
            t_row = cursor.fetchone()
            if not t_row:
                raise ValueError(f"No transcript found in MySQL for lecture {lecture_id}")
            transcript_id = t_row["id"]

            cursor.execute(
                "SELECT id AS db_id, segment_id, start_time, end_time, text FROM transcript_segments WHERE transcript_id = %s ORDER BY start_time, segment_id",
                (transcript_id,),
            )
            segments = cursor.fetchall()
            if not segments:
                raise ValueError(f"No transcript segments found for transcript {transcript_id}")

            # 2. Update status to GENERATING_NOTES
            cursor.execute("UPDATE lectures SET status = 'GENERATING_NOTES' WHERE id = %s", (lecture_id,))
            cursor.execute(
                "UPDATE processing_jobs SET status = 'RUNNING', started_at = NOW() WHERE lecture_id = %s AND job_type = 'STUDY_MATERIAL_GENERATION'",
                (lecture_id,),
            )
            conn.commit()

            # Map segment_id -> db_id for source_mappings foreign key
            segment_db_map = {seg["segment_id"]: seg["db_id"] for seg in segments}
            valid_segment_ids = set(segment_db_map.keys())

            # 3. Call Gemini (or use mock if provided for offline unit tests)
            if mock_material:
                material = mock_material
            else:
                api_key = os.environ.get("GEMINI_API_KEY")
                if not api_key:
                    raise ValueError("GEMINI_API_KEY environment variable is not configured.")

                if client is None:
                    client = genai.Client(api_key=api_key)

                prompt = build_prompt(segments)
                raw_json = request_gemini_study_material(client, prompt)
                material = StudyMaterial.model_validate_json(raw_json)

            # 4. Validate source references
            invalid_ids = validate_source_refs(material, valid_segment_ids)

            # 5. Persist into notes table
            material_json_str = json.dumps(material.model_dump())
            cursor.execute(
                "INSERT INTO notes (lecture_id, model_name, study_material_json, generated_at) VALUES (%s, %s, %s, NOW())",
                (lecture_id, MODEL_NAME, material_json_str),
            )
            notes_id = cursor.lastrowid

            # Helper to insert study item & source mappings
            def insert_items(items: list[Any], item_type: str):
                for idx, item in enumerate(items):
                    content = getattr(item, "content", None)
                    term = getattr(item, "term", None)
                    explanation = getattr(item, "explanation", None)
                    question = getattr(item, "question", None)
                    question_type = getattr(item, "type", None)

                    cursor.execute(
                        """
                        INSERT INTO study_items 
                            (notes_id, item_type, content, term, explanation, question, question_type, item_order)
                        VALUES 
                            (%s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (notes_id, item_type, content, term, explanation, question, question_type, idx),
                    )
                    study_item_id = cursor.lastrowid

                    source_refs = getattr(item, "source_refs", [])
                    for sref in source_refs:
                        seg_db_id = segment_db_map.get(sref.segment_id)
                        if seg_db_id:
                            cursor.execute(
                                "INSERT IGNORE INTO source_mappings (study_item_id, transcript_segment_id) VALUES (%s, %s)",
                                (study_item_id, seg_db_id),
                            )

            insert_items(material.key_points, "KEY_POINT")
            insert_items(material.important_concepts, "IMPORTANT_CONCEPT")
            insert_items(material.definitions, "DEFINITION")
            insert_items(material.examples, "EXAMPLE")
            insert_items(material.formulas, "FORMULA")
            insert_items(material.exam_questions, "EXAM_QUESTION")
            insert_items(material.revision_points, "REVISION_POINT")
            insert_items(material.assignments, "ASSIGNMENT")
            insert_items(material.announcements, "ANNOUNCEMENT")

            # 6. Update status to READY
            cursor.execute("UPDATE lectures SET status = 'READY' WHERE id = %s", (lecture_id,))
            cursor.execute(
                "UPDATE processing_jobs SET status = 'COMPLETED', completed_at = NOW() WHERE lecture_id = %s AND job_type = 'STUDY_MATERIAL_GENERATION'",
                (lecture_id,),
            )
            conn.commit()

            return {
                "success": True,
                "lecture_id": lecture_id,
                "status": "READY",
                "notes_id": notes_id,
                "invalid_segment_ids": invalid_ids,
            }

    except Exception as err:
        # On error: update status to FAILED and preserve lecture & transcript
        try:
            with get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("UPDATE lectures SET status = 'FAILED' WHERE id = %s", (lecture_id,))
                cursor.execute(
                    "UPDATE processing_jobs SET status = 'FAILED', error_message = %s WHERE lecture_id = %s AND job_type = 'STUDY_MATERIAL_GENERATION'",
                    (str(err)[:500], lecture_id),
                )
                conn.commit()
        except Exception:
            pass
        raise err
