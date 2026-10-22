"""Validated transcript contract shared by future backend inputs and Gemini."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, model_validator


class TranscriptSegment(BaseModel):
    id: int = Field(ge=0)
    start: float = Field(ge=0)
    end: float = Field(ge=0)
    text: str

    @model_validator(mode="after")
    def validate_time_range(self) -> "TranscriptSegment":
        if self.end < self.start:
            raise ValueError("Transcript segment end must not precede start")
        if not self.text.strip():
            raise ValueError("Transcript segment text must not be empty")
        return self


class Transcript(BaseModel):
    segments: list[TranscriptSegment] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_segment_ids(self) -> "Transcript":
        ids = [segment.id for segment in self.segments]
        if len(ids) != len(set(ids)):
            raise ValueError("Transcript segment IDs must be unique")
        return self


def validate_transcript_payload(payload: Any) -> Transcript:
    """Validate an Android/API transcript without knowing its origin."""
    if isinstance(payload, dict) and "segments" in payload:
        return Transcript.model_validate(payload)
    raise ValueError("Transcript payload must contain a non-empty segments list")
