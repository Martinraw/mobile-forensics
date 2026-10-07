import sqlite3

from mobileforensics.whatsapp_parser import parse_messages


def make_modern_db(path):
    con = sqlite3.connect(path)
    con.executescript('''
    CREATE TABLE jid (_id INTEGER PRIMARY KEY, raw_string TEXT);
    CREATE TABLE chat (_id INTEGER PRIMARY KEY, jid_row_id INTEGER, subject TEXT);
    CREATE TABLE message (_id INTEGER PRIMARY KEY, chat_row_id INTEGER, from_me INTEGER,
        key_id TEXT, sender_jid_row_id INTEGER, timestamp INTEGER,
        message_type INTEGER, text_data TEXT);
    INSERT INTO jid VALUES (1, '260970000001@s.whatsapp.net');
    INSERT INTO chat VALUES (1, 1, NULL);
    INSERT INTO message VALUES (1, 1, 0, 'ABC', 1, 1700000000000, 0, 'hello');
    INSERT INTO message VALUES (2, 1, 1, 'DEF', NULL, 1700000060000, 0, 'hi back');
    ''')
    con.commit()
    con.close()


def make_legacy_db(path):
    con = sqlite3.connect(path)
    con.executescript('''
    CREATE TABLE messages (_id INTEGER PRIMARY KEY, key_remote_jid TEXT, key_from_me INTEGER,
        key_id TEXT, timestamp INTEGER, media_wa_type INTEGER, data TEXT, remote_resource TEXT);
    INSERT INTO messages VALUES (1, '260970000002@s.whatsapp.net', 0, 'K1',
        1700000000000, 0, 'old hello', NULL);
    ''')
    con.commit()
    con.close()


def test_modern_schema(tmp_path):
    db = tmp_path / 'msgstore.db'
    make_modern_db(db)
    msgs = list(parse_messages(db))
    assert [m['text'] for m in msgs] == ['hello', 'hi back']
    assert msgs[0]['from_me'] is False and msgs[1]['from_me'] is True
    assert msgs[0]['timestamp_utc'].startswith('2023-11-14')
    assert msgs[0]['chat'] == '260970000001@s.whatsapp.net'


def test_legacy_schema(tmp_path):
    db = tmp_path / 'msgstore.db'
    make_legacy_db(db)
    msgs = list(parse_messages(db))
    assert len(msgs) == 1 and msgs[0]['text'] == 'old hello'
    assert msgs[0]['source_table'] == 'messages'
