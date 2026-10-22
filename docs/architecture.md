# Architecture Overview

## System goal

The project creates an offline-aware lecture processing pipeline for college students. The main objective is to turn classroom audio into structured study material while keeping the system practical on modest CPU-only hardware.

## Layered architecture

### 1. Client layer

- Android mobile app for lecture capture and upload
- Web application for searching, revising, and viewing notes

### 2. Application layer

- Backend service for lecture metadata and API orchestration
- AI service for transcription and later lecture processing tasks

### 3. Data layer

- MySQL for persistent storage
- Local file storage for uploaded audio and generated transcripts

### 4. AI layer

- Indian-English ASR inference using a Hugging Face Whisper model
- Later stages may include topic segmentation, extraction, and local LLM summarization

### 5. Deployment layer

- Docker and Docker Compose for local orchestration and future deployment

## Planned data flow

Audio recording -> upload -> validation -> ASR -> timestamped transcript -> structured lecture analysis -> notes -> database -> web access

## Design principles

- Prefer offline local processing
- Use CPU-friendly AI models
- Preserve transcript timestamps
- Keep each stage modular and testable
- Avoid large-scale overengineering in early stages
- Validate each model and pipeline stage with evidence

## Future roadmap

The architecture is intentionally staged:

1. ASR proof of concept
2. Evaluation and transcript storage
3. Topic segmentation research
4. Lecture information extraction
5. Local LLM integration
6. Source-linked notes
7. Backend integration
8. Web application
9. Android app
10. Testing and deployment

This phased approach minimizes risk and keeps the project realistic for a short development cycle.
