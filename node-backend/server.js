require('dotenv').config({ path: __dirname + '/.env' });
const express = require('express');
const cors = require('cors');
const bodyParser = require('body-parser');
const { generateAiNotes } = require('./aiNotesGenerator');
const { processDocumentImageVision } = require('./aiVisionOcrService');

const app = express();
const PORT = process.env.PORT || 5000;

app.use(cors());
app.use(bodyParser.json({ limit: '20mb' }));

// In-memory store for lecture transcripts and AI notes
const lecturesDb = [];

// Health check endpoint
app.get('/api/health', (req, res) => {
    res.json({
        status: 'ok',
        service: 'Classroom Lecture Capture Backend',
        ai_provider: process.env.GEMINI_API_KEY ? 'Google Gemini AI' : (process.env.OPENAI_API_KEY ? 'OpenAI' : 'Demo AI Engine (Set GEMINI_API_KEY in backend/.env)'),
        timestamp: new Date().toISOString()
    });
});

// 1. Online AI Vision & OCR Document Parsing Endpoint
app.post('/api/ai/vision-ocr', async (req, res) => {
    console.log('[API_VISION_REQUEST] Received AI Vision OCR request.');
    try {
        const { image_base64, document_type } = req.body;
        const targetType = document_type || 'WEEKLY_TIMETABLE';

        const visionResult = await processDocumentImageVision(image_base64 || '', targetType);

        res.status(200).json(visionResult);
    } catch (err) {
        console.error('[API_VISION_ERROR] Failed to process document image:', err);
        res.status(500).json({
            status: 'error',
            message: 'Failed to process document image with AI Vision: ' + err.message
        });
    }
});

// 2. Upload Lecture Transcript & Trigger AI Notes Generation
app.post('/api/lectures/upload', (req, res) => {
    console.log('[UPLOAD_STARTED] Received payload from Android app:', req.body);

    const { userId, course_name, course, date, day, start_time, startTime, end_time, endTime, transcript } = req.body;

    const finalCourse = course_name || course || 'General Lecture';
    const finalStart = start_time || startTime || '09:00';
    const finalEnd = end_time || endTime || '10:00';
    const rawTranscript = transcript || '';

    // Generate AI Structured Notes from raw transcript
    const aiNotes = generateAiNotes(rawTranscript, finalCourse);

    const lectureEntry = {
        id: lecturesDb.length + 1,
        userId: userId || 'student@college.edu',
        courseName: finalCourse,
        date: date || new Date().toISOString().split('T')[0],
        day: day || 'Today',
        startTime: finalStart,
        endTime: finalEnd,
        rawTranscript: rawTranscript,
        aiNotes: aiNotes,
        receivedAt: new Date().toISOString()
    };

    lecturesDb.push(lectureEntry);

    console.log(`[UPLOAD_SUCCESS] Lecture ID ${lectureEntry.id} saved. Raw transcript length: ${rawTranscript.length} chars.`);

    res.status(200).json({
        status: 'success',
        message: 'Lecture transcript received and AI structured notes generated successfully.',
        lectureId: lectureEntry.id,
        courseName: finalCourse,
        date: lectureEntry.date,
        timeRange: `${finalStart} - ${finalEnd}`,
        aiNotes: aiNotes
    });
});

// Get all uploaded lectures with class-wise transcripts & AI notes
app.get('/api/lectures', (req, res) => {
    res.json({
        count: lecturesDb.length,
        lectures: lecturesDb
    });
});

app.listen(PORT, '0.0.0.0', () => {
    console.log(`====================================================`);
    console.log(`Classroom Lecture Capture Backend REST API Server`);
    console.log(`Listening on http://localhost:${PORT}`);
    console.log(`AI Provider: ${process.env.GEMINI_API_KEY ? 'Google Gemini API Active' : 'Default AI Vision Engine'}`);
    console.log(`Android Emulator endpoint: http://10.0.2.2:${PORT}/api/lectures/upload`);
    console.log(`====================================================`);
});
