/**
 * AI Lecture Notes Generator Module
 * Converts raw classroom lecture transcripts into structured academic notes.
 */

function generateAiNotes(transcript, courseName) {
    if (!transcript || transcript.trim().length === 0) {
        return {
            summary: "No speech detected in this lecture session.",
            importantConcepts: [],
            keyPoints: [],
            importantDefinitions: [],
            importantExamples: [],
            importantFormulas: [],
            announcements: [],
            studentQuestions: [],
            doubtsRaised: [],
            teacherInstructions: [],
            examImportantPoints: [],
            actionItems: []
        };
    }

    console.log(`[AI_PROCESSING_STARTED] Analyzing raw transcript for course: ${courseName}`);

    const lines = transcript.split(/(?<=[.!?])\s+/).filter(l => l.trim().length > 0);

    const summary = lines.slice(0, 3).join(' ') || `Overview of ${courseName} lecture session.`;
    
    const importantConcepts = [];
    const keyPoints = [];
    const importantDefinitions = [];
    const importantExamples = [];
    const importantFormulas = [];
    const announcements = [];
    const studentQuestions = [];
    const doubtsRaised = [];
    const teacherInstructions = [];
    const examImportantPoints = [];
    const actionItems = [];

    lines.forEach(sentence => {
        const lower = sentence.toLowerCase();

        // Exam Important
        if (lower.includes("exam") || lower.includes("test") || lower.includes("important") || lower.includes("mark")) {
            examImportantPoints.push(sentence);
        }

        // Definitions
        if (lower.includes("is defined as") || lower.includes("refers to") || lower.includes("means") || lower.includes("definition")) {
            importantDefinitions.push(sentence);
        }

        // Examples
        if (lower.includes("example") || lower.includes("for instance") || lower.includes("such as")) {
            importantExamples.push(sentence);
        }

        // Announcements & Instructions
        if (lower.includes("announcement") || lower.includes("assignment") || lower.includes("submit") || lower.includes("deadline")) {
            announcements.push(sentence);
            actionItems.push(sentence);
        }

        // Student Questions & Doubts
        if (lower.includes("?") || lower.includes("question") || lower.includes("doubt") || lower.includes("asked")) {
            studentQuestions.push(sentence);
            doubtsRaised.push(sentence);
        }

        // Key Points
        if (sentence.length > 25 && !keyPoints.includes(sentence)) {
            keyPoints.push(sentence);
        }
    });

    if (keyPoints.length === 0) keyPoints.push(...lines);
    if (importantConcepts.length === 0) importantConcepts.push(`Core principles of ${courseName}`);

    console.log(`[AI_NOTES_READY] Structured notes generated successfully for ${courseName}`);

    return {
        summary: summary,
        importantConcepts: importantConcepts.slice(0, 5),
        keyPoints: keyPoints.slice(0, 8),
        importantDefinitions: importantDefinitions.slice(0, 4),
        importantExamples: importantExamples.slice(0, 4),
        importantFormulas: importantFormulas.slice(0, 3),
        announcements: announcements.slice(0, 3),
        studentQuestions: studentQuestions.slice(0, 3),
        doubtsRaised: doubtsRaised.slice(0, 3),
        teacherInstructions: teacherInstructions.slice(0, 3),
        examImportantPoints: examImportantPoints.slice(0, 5),
        actionItems: actionItems.slice(0, 4)
    };
}

module.exports = { generateAiNotes };
