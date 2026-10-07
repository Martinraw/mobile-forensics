'''Case database: one normalized artifact table shared by every parser.'''
import sqlite3

SCHEMA = '''
CREATE TABLE IF NOT EXISTS artifact (
    artifact_id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id TEXT NOT NULL,
    app TEXT,
    artifact_type TEXT,
    timestamp_utc TEXT,
    sender TEXT,
    recipient TEXT,
    chat TEXT,
    content TEXT,
    attachment TEXT,
    source_file TEXT,
    source_table TEXT,
    source_rowid INTEGER,
    source_sha256 TEXT
);
CREATE INDEX IF NOT EXISTS idx_artifact_ts ON artifact(timestamp_utc);
'''

INSERT = '''
INSERT INTO artifact (case_id, app, artifact_type, timestamp_utc, sender, recipient,
                      chat, content, attachment, source_file, source_table,
                      source_rowid, source_sha256)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
'''


def open_case_db(path):
    con = sqlite3.connect(path)
    con.executescript(SCHEMA)
    return con


def add_whatsapp_messages(con, case_id, messages, source_file, source_sha256) -> int:
    rows = []
    for m in messages:
        sent = m['from_me']
        sender = 'DEVICE_OWNER' if sent else (m['sender'] or m['chat'])
        recipient = m['chat'] if sent else 'DEVICE_OWNER'
        rows.append((case_id, 'whatsapp', 'message', m['timestamp_utc'], sender, recipient,
                     m['chat'], m['text'], None, source_file, m['source_table'],
                     m['source_rowid'], source_sha256))
    con.executemany(INSERT, rows)
    con.commit()
    return len(rows)
