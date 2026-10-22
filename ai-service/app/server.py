"""FastAPI application entry point for Offline AI Notes Companion."""

from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from app.api.lectures import router as lectures_router

app = FastAPI(title="Offline AI Notes Companion AI Service")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(lectures_router)

APK_FILE_PATH = Path(r"C:\Users\ashok\OneDrive\Desktop\offline-ai-notes-companion\android\app\build\outputs\apk\debug\app-debug.apk")
WEB_DIST_PATH = Path(r"C:\Users\ashok\OneDrive\Desktop\offline-ai-notes-companion\web\dist")


@app.get("/download/app-debug.apk")
@app.get("/app-debug.apk")
def download_apk() -> FileResponse:
    """Serve the compiled Android debug APK via HTTP download."""
    if not APK_FILE_PATH.exists():
        raise HTTPException(status_code=404, detail="Compiled APK file not found.")
    return FileResponse(
        path=str(APK_FILE_PATH),
        filename="app-debug.apk",
        media_type="application/vnd.android.package-archive",
    )


if WEB_DIST_PATH.exists():
    app.mount("/", StaticFiles(directory=str(WEB_DIST_PATH), html=True), name="web")
