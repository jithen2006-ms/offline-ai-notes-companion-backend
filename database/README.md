# Database setup

The MySQL schema is defined in `schema.sql`. It creates the
`offline_notes_companion` database and the twelve core tables used by the
future service.

## Configure

Set these variables in `ai-service/.env` locally. Never commit that file:

```text
DB_HOST=127.0.0.1
DB_PORT=3306
DB_NAME=offline_notes_companion
DB_USER=your_mysql_user
DB_PASSWORD=your_mysql_password
```

The existing `GEMINI_API_KEY` entry must remain in that file and is unrelated
to database access.

## Recreate the database

Using the MySQL client:

```powershell
mysql -h 127.0.0.1 -P 3306 -u your_mysql_user -p < database/schema.sql
```

Or execute `database/schema.sql` in MySQL Workbench. The schema itself remains
the reproducible source of truth.

## Verify

From the repository root, after setting the database variables:

```powershell
$env:PYTHONPATH = (Resolve-Path 'ai-service').Path
& 'ai-service/.venv/Scripts/python.exe' database/verify_database.py
```

The verifier uses the real DBMS transcript and Gemini JSON fixtures, checks
chronological transcript retrieval, preserves the complete structured JSON,
and removes its temporary records when successful.