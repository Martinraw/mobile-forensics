'''Create a synthetic WhatsApp database (modern schema) for demos and testing.
No real data is involved. Usage: python scripts/make_demo_db.py samples/demo_msgstore.db'''
import sqlite3
import sys
from pathlib import Path

out = Path(sys.argv[1] if len(sys.argv) > 1 else 'samples/demo_msgstore.db')
out.parent.mkdir(parents=True, exist_ok=True)
if out.exists():
    out.unlink()

con = sqlite3.connect(out)
con.executescript('''
CREATE TABLE jid (_id INTEGER PRIMARY KEY, raw_string TEXT);
CREATE TABLE chat (_id INTEGER PRIMARY KEY, jid_row_id INTEGER, subject TEXT);
CREATE TABLE message (_id INTEGER PRIMARY KEY, chat_row_id INTEGER, from_me INTEGER,
    key_id TEXT, sender_jid_row_id INTEGER, timestamp INTEGER,
    message_type INTEGER, text_data TEXT);
INSERT INTO jid VALUES (1, '260970000001@s.whatsapp.net');
INSERT INTO jid VALUES (2, '260970000002@s.whatsapp.net');
INSERT INTO chat VALUES (1, 1, NULL);
INSERT INTO chat VALUES (2, 2, NULL);
INSERT INTO message VALUES (1, 1, 0, 'M1', 1, 1700000000000, 0, 'Hello, test message one');
INSERT INTO message VALUES (2, 1, 1, 'M2', NULL, 1700000060000, 0, 'Reply from device owner');
INSERT INTO message VALUES (3, 2, 0, 'M3', 2, 1700000120000, 0, 'Second contact says hi');
INSERT INTO message VALUES (4, 2, 1, 'M4', NULL, 1700000180000, 0, '<b>HTML should be escaped</b>');
''')
con.commit()
con.close()
print(f'Demo database written to {out}')
