CREATE DATABASE IF NOT EXISTS offline_notes_companion
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE offline_notes_companion;

CREATE TABLE IF NOT EXISTS users (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  name VARCHAR(150) NOT NULL,
  email VARCHAR(254) NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_users_email (email)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS subjects (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  user_id BIGINT UNSIGNED NOT NULL,
  name VARCHAR(150) NOT NULL,
  code VARCHAR(50) NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_subjects_user_name (user_id, name),
  KEY idx_subjects_user_id (user_id),
  CONSTRAINT fk_subjects_user FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS timetable (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  user_id BIGINT UNSIGNED NOT NULL,
  subject_id BIGINT UNSIGNED NOT NULL,
  class_title VARCHAR(200) NOT NULL,
  day_of_week TINYINT UNSIGNED NOT NULL,
  start_time TIME NOT NULL,
  end_time TIME NOT NULL,
  is_enabled BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_timetable_user_day (user_id, day_of_week),
  KEY idx_timetable_subject (subject_id),
  CONSTRAINT chk_timetable_day CHECK (day_of_week BETWEEN 0 AND 6),
  CONSTRAINT chk_timetable_time CHECK (end_time > start_time),
  CONSTRAINT fk_timetable_user FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
  CONSTRAINT fk_timetable_subject FOREIGN KEY (subject_id) REFERENCES subjects (id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS lectures (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  user_id BIGINT UNSIGNED NOT NULL,
  subject_id BIGINT UNSIGNED NULL,
  timetable_id BIGINT UNSIGNED NULL,
  title VARCHAR(255) NOT NULL,
  lecture_date DATE NULL,
  start_time DATETIME NULL,
  end_time DATETIME NULL,
  duration_seconds DECIMAL(12,3) NULL,
  status ENUM('RECEIVED', 'TRANSCRIBING', 'TRANSCRIBED', 'GENERATING_NOTES', 'READY', 'FAILED') NOT NULL DEFAULT 'RECEIVED',
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_lectures_user_date (user_id, lecture_date),
  KEY idx_lectures_subject (subject_id),
  KEY idx_lectures_status (status),
  CONSTRAINT chk_lectures_duration CHECK (duration_seconds IS NULL OR duration_seconds >= 0),
  CONSTRAINT chk_lectures_time CHECK (end_time IS NULL OR start_time IS NULL OR end_time >= start_time),
  CONSTRAINT fk_lectures_user FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
  CONSTRAINT fk_lectures_subject FOREIGN KEY (subject_id) REFERENCES subjects (id) ON DELETE SET NULL,
  CONSTRAINT fk_lectures_timetable FOREIGN KEY (timetable_id) REFERENCES timetable (id) ON DELETE SET NULL
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS audio_metadata (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  lecture_id BIGINT UNSIGNED NOT NULL,
  filename VARCHAR(255) NOT NULL,
  format VARCHAR(32) NOT NULL,
  duration_seconds DECIMAL(12,3) NULL,
  file_size_bytes BIGINT UNSIGNED NULL,
  storage_reference VARCHAR(1024) NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_audio_metadata_lecture (lecture_id),
  KEY idx_audio_metadata_format (format),
  CONSTRAINT chk_audio_duration CHECK (duration_seconds IS NULL OR duration_seconds >= 0),
  CONSTRAINT fk_audio_metadata_lecture FOREIGN KEY (lecture_id) REFERENCES lectures (id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS transcripts (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  lecture_id BIGINT UNSIGNED NOT NULL,
  language VARCHAR(32) NOT NULL DEFAULT 'en',
  status ENUM('PENDING', 'READY', 'FAILED') NOT NULL DEFAULT 'PENDING',
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_transcripts_lecture (lecture_id),
  KEY idx_transcripts_status (status),
  CONSTRAINT fk_transcripts_lecture FOREIGN KEY (lecture_id) REFERENCES lectures (id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS transcript_segments (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  transcript_id BIGINT UNSIGNED NOT NULL,
  segment_id INT UNSIGNED NOT NULL,
  start_time DECIMAL(12,3) NOT NULL,
  end_time DECIMAL(12,3) NOT NULL,
  text TEXT NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_transcript_segment_id (transcript_id, segment_id),
  UNIQUE KEY uq_transcript_segment_lookup (id, transcript_id),
  KEY idx_segments_chronological (transcript_id, start_time, segment_id),
  CONSTRAINT chk_segment_times CHECK (start_time >= 0 AND end_time >= start_time),
  CONSTRAINT fk_segments_transcript FOREIGN KEY (transcript_id) REFERENCES transcripts (id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS lecture_topics (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  lecture_id BIGINT UNSIGNED NOT NULL,
  topic_name VARCHAR(200) NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_lecture_topic (lecture_id, topic_name),
  KEY idx_lecture_topics_name (topic_name),
  CONSTRAINT fk_lecture_topics_lecture FOREIGN KEY (lecture_id) REFERENCES lectures (id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS notes (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  lecture_id BIGINT UNSIGNED NOT NULL,
  model_name VARCHAR(150) NOT NULL,
  study_material_json JSON NOT NULL,
  generated_at DATETIME NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_notes_lecture (lecture_id),
  KEY idx_notes_model (model_name),
  CONSTRAINT fk_notes_lecture FOREIGN KEY (lecture_id) REFERENCES lectures (id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS study_items (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  notes_id BIGINT UNSIGNED NOT NULL,
  item_type ENUM('KEY_POINT', 'IMPORTANT_CONCEPT', 'DEFINITION', 'EXAMPLE', 'FORMULA', 'EXAM_QUESTION', 'REVISION_POINT', 'ASSIGNMENT', 'ANNOUNCEMENT') NOT NULL,
  content TEXT NULL,
  term VARCHAR(255) NULL,
  explanation TEXT NULL,
  question TEXT NULL,
  question_type VARCHAR(64) NULL,
  item_order INT UNSIGNED NOT NULL DEFAULT 0,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_study_items_notes_type (notes_id, item_type, item_order),
  CONSTRAINT chk_study_item_payload CHECK (
    (item_type IN ('DEFINITION') AND term IS NOT NULL AND explanation IS NOT NULL AND content IS NULL AND question IS NULL)
    OR (item_type IN ('EXAM_QUESTION') AND question IS NOT NULL AND question_type IS NOT NULL AND content IS NULL AND term IS NULL AND explanation IS NULL)
    OR (item_type NOT IN ('DEFINITION', 'EXAM_QUESTION') AND content IS NOT NULL AND term IS NULL AND explanation IS NULL AND question IS NULL)
  ),
  CONSTRAINT fk_study_items_notes FOREIGN KEY (notes_id) REFERENCES notes (id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS source_mappings (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  study_item_id BIGINT UNSIGNED NOT NULL,
  transcript_segment_id BIGINT UNSIGNED NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_source_mapping (study_item_id, transcript_segment_id),
  KEY idx_source_mappings_segment (transcript_segment_id),
  CONSTRAINT fk_source_mappings_item FOREIGN KEY (study_item_id) REFERENCES study_items (id) ON DELETE CASCADE,
  CONSTRAINT fk_source_mappings_segment FOREIGN KEY (transcript_segment_id) REFERENCES transcript_segments (id) ON DELETE RESTRICT
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS processing_jobs (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  lecture_id BIGINT UNSIGNED NOT NULL,
  job_type ENUM('TRANSCRIPTION', 'STUDY_MATERIAL_GENERATION') NOT NULL,
  status ENUM('QUEUED', 'RUNNING', 'COMPLETED', 'FAILED') NOT NULL DEFAULT 'QUEUED',
  started_at DATETIME NULL,
  completed_at DATETIME NULL,
  error_message TEXT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_processing_jobs_lecture_status (lecture_id, status),
  CONSTRAINT chk_processing_job_times CHECK (completed_at IS NULL OR started_at IS NULL OR completed_at >= started_at),
  CONSTRAINT fk_processing_jobs_lecture FOREIGN KEY (lecture_id) REFERENCES lectures (id) ON DELETE CASCADE
) ENGINE=InnoDB;
