# 📚 Offline AI Notes Companion — Backend

> 🎓 **Minor Academic Project**
> Service Layer: FastAPI AI Microservice, Node.js OCR Service & MySQL Database

---

## 📖 Overview

This repository contains the backend and data services for the **Offline AI Notes Companion** project:
1. **Python FastAPI AI Service (`ai-service/`)**: Primary REST API and AI pipeline for handling lecture uploads, MySQL database interactions, and Gemini note generation.
2. **MySQL Relational Database Layer (`database/`)**: Relational schema defining lectures, transcripts, segments, notes, and processing jobs.
3. **Node.js Express Backend (`node-backend/`)**: Secondary service providing vision OCR document parsing and timetable schedule processing.

---

## 📁 Repository Structure

```
offline-ai-notes-companion-backend/
├── ai-service/                # Python FastAPI microservice & MySQL access
│   ├── app/
│   │   ├── main.py            # Microservice entry point
│   │   ├── server.py          # FastAPI application & endpoints
│   │   ├── db.py              # MySQL connection pool
│   │   ├── api/lectures.py    # Lectures, uploads & subjects router
│   │   └── services/          # Gemini AI generation & transcript boundaries
│   ├── scripts/               # Pipeline verification scripts
│   ├── tests/                 # Unit & integration tests
│   ├── requirements-asr.txt   # Python dependencies
│   └── .env.example           # Environment template
├── database/                  # Relational database layer
│   ├── schema.sql             # MySQL database schema definition
│   ├── verify_database.py     # Verification script
│   └── README.md              # Database setup guide
├── node-backend/              # Express Node.js backend
│   ├── server.js              # Express API server
│   ├── aiNotesGenerator.js    # Note generation module
│   ├── aiVisionOcrService.js  # Document OCR processing
│   ├── package.json           # Node dependencies
│   └── .env.example           # Node environment template
├── docs/                      # Architectural specifications
│   └── architecture.md        # System architecture overview
└── docker-compose.yml         # Container orchestration
```

---

## 🚀 Getting Started

### 1. Database Setup

```bash
cd database
mysql -u root -p < schema.sql
python verify_database.py
```

### 2. FastAPI AI Service

```bash
cd ai-service
python -m venv venv
# On Windows:
.\venv\Scripts\activate
# On Linux/macOS:
source venv/bin/activate

pip install -r requirements-asr.txt
cp .env.example .env  # Configure your DB and Gemini credentials
python app/server.py
```
The FastAPI service runs on `http://localhost:8000`.

### 3. Node.js Express Backend

```bash
cd node-backend
npm install
cp .env.example .env  # Configure your port and API keys
npm start
```
The Node.js backend runs on `http://localhost:5000`.
