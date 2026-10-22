"""Proof of concept: convert one existing transcript into grounded study material."""

import json
import os
import sys
import time
from argparse import ArgumentParser
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types
from pydantic import BaseModel, Field, ValidationError

SCRIPT_DIR = Path(__file__).resolve().parent
AI_SERVICE_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(AI_SERVICE_DIR))

from app.services.transcript_boundary import TranscriptSegment, validate_transcript_payload

MODEL_NAME = "gemini-3.5-flash-lite"
DEFAULT_TRANSCRIPT_PATH = AI_SERVICE_DIR / "data" / "output" / "Lec_1_Introduction_to_DBMS_transcript.json"
DEFAULT_OUTPUT_PATH = AI_SERVICE_DIR / "data" / "output" / "gemini_dbms_study_material.json"

load_dotenv(AI_SERVICE_DIR / ".env")


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


def load_transcript(path: Path) -> list[TranscriptSegment]:
    with path.open(encoding="utf-8") as transcript_file:
        transcript = validate_transcript_payload(json.load(transcript_file))
    return transcript.segments


def build_prompt(segments: list[TranscriptSegment]) -> str:
    transcript_text = "\n".join(
        f"SEGMENT {segment.id}: {segment.text.strip()}" for segment in segments
    )
    return f"""You are a college study assistant. Transform the complete transcript below into detailed, useful study material.

Primary source and grounding:
- Use the transcript as the primary source. Do not expand it into a general textbook lesson.
- Limited domain knowledge is allowed only to correct an obvious ASR artifact when the surrounding transcript strongly supports the correction, such as interpreting repeated "d b m" as DBMS.
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


def item_counts(material: StudyMaterial) -> dict[str, int]:
    return {
        "key_points": len(material.key_points),
        "important_concepts": len(material.important_concepts),
        "definitions": len(material.definitions),
        "examples": len(material.examples),
        "formulas": len(material.formulas),
        "exam_questions": len(material.exam_questions),
        "revision_points": len(material.revision_points),
        "assignments": len(material.assignments),
        "announcements": len(material.announcements),
    }


def request_study_material(client: genai.Client, prompt: str) -> str:
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


def parse_args() -> tuple[Path, Path]:
    parser = ArgumentParser(description="Extract grounded study material from a timestamped transcript.")
    parser.add_argument("transcript", nargs="?", type=Path, default=DEFAULT_TRANSCRIPT_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    args = parser.parse_args()
    return args.transcript, args.output


def main() -> int:
    started_at = time.perf_counter()
    transcript_path, output_path = parse_args()
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("ERROR: GEMINI_API_KEY is missing; no Gemini request was made.", file=sys.stderr)
        return 1
    if not transcript_path.exists():
        print(f"ERROR: transcript not found: {transcript_path}", file=sys.stderr)
        return 1

    try:
        segments = load_transcript(transcript_path)
        prompt = build_prompt(segments)
        input_size = transcript_path.stat().st_size
        client = genai.Client(api_key=api_key)

        request_started_at = time.perf_counter()
        raw_response = request_study_material(client, prompt)
        request_time = time.perf_counter() - request_started_at

        try:
            material = StudyMaterial.model_validate_json(raw_response)
        except (ValidationError, ValueError) as error:
            print(f"ERROR: malformed or schema-invalid Gemini response: {error}", file=sys.stderr)
            return 1

        invalid_ids = validate_source_refs(material, {segment.id for segment in segments})
        total_refs = sum(
            len(item.source_refs)
            for items in [
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
            for item in items
        )
        result = {
            "model": MODEL_NAME,
            "input_file": str(transcript_path),
            "segment_count": len(segments),
            "input_size_bytes": input_size,
            "request_status": "success",
            "request_time_seconds": round(request_time, 3),
            "total_processing_time_seconds": round(time.perf_counter() - started_at, 3),
            "pydantic_validation": "success",
            "item_counts": item_counts(material),
            "source_reference_validation": {
                "total_references": total_refs,
                "valid_references": total_refs - len(invalid_ids),
                "invalid_references": len(invalid_ids),
                "invalid_segment_ids": invalid_ids,
                "status": "success" if not invalid_ids else "error",
            },
            "study_material": material.model_dump(),
        }
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({key: value for key, value in result.items() if key != "study_material"}, indent=2))
        print(f"output_file={output_path}")
        return 0 if not invalid_ids else 1
    except (OSError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    except Exception as error:
        print(f"ERROR: Gemini request failed after at most one retry: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
