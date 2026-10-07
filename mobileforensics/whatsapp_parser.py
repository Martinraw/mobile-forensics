'''Parse WhatsApp msgstore.db into normalized message dictionaries.'''
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

MODERN_SQL = '''
SELECT m._id AS _id, m.key_id AS key_id, m.from_me AS from_me, m.timestamp AS timestamp,
       m.message_type AS message_type, m.text_data AS text,
       cj.raw_string AS chat_jid, sj.raw_string AS sender_jid
FROM message m
LEFT JOIN chat c ON m.chat_row_id = c._id
LEFT JOIN jid cj ON c.jid_row_id = cj._id
LEFT JOIN jid sj ON m.sender_jid_row_id = sj._id
ORDER BY m.timestamp
'''

LEGACY_SQL = '''
SELECT _id, key_id, key_from_me AS from_me, timestamp, media_wa_type AS message_type,
       data AS text, key_remote_jid AS chat_jid, remote_resource AS sender_jid
FROM messages
ORDER BY timestamp
'''


def _ts(ms):
    if not ms:
        return None
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat()


def _columns(con, table):
    return {row[1] for row in con.execute(f'PRAGMA table_info({table})')}


def parse_messages(db_path: Path):
    '''Yield one dictionary per message, whichever schema version the database uses.'''
    con = sqlite3.connect(f'file:{db_path}?mode=ro', uri=True)
    con.row_factory = sqlite3.Row
    tables = {r[0] for r in con.execute('SELECT name FROM sqlite_master WHERE type = ?',
                                        ('table',))}
    if 'message' in tables and 'chat_row_id' in _columns(con, 'message'):
        sql, table = MODERN_SQL, 'message'
    elif 'messages' in tables:
        sql, table = LEGACY_SQL, 'messages'
    else:
        raise ValueError('Unrecognized WhatsApp schema: add a parser for this version')
    for r in con.execute(sql):
        yield {
            'source_table': table,
            'source_rowid': r['_id'],
            'message_id': r['key_id'],
            'from_me': bool(r['from_me']),
            'timestamp_utc': _ts(r['timestamp']),
            'chat': r['chat_jid'],
            'sender': r['sender_jid'],
            'msg_type': r['message_type'],
            'text': r['text'],
        }
    con.close()
