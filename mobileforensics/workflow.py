'''Shared workflow functions used by both the CLI and the GUI.'''
import json
import re
import sqlite3
from pathlib import Path

from .casedb import add_whatsapp_messages, open_case_db
from .evidence import AuditLog, CaseRecord, sha256_file
from .report import build_report
from .whatsapp_parser import parse_messages

CASE_ID_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$')
ARTIFACT_SORT_COLUMNS = frozenset({'timestamp_utc', 'app', 'artifact_type', 'sender',
                                   'recipient', 'chat', 'content'})


def valid_case_id(case_id: str) -> bool:
    return bool(CASE_ID_RE.match(case_id or ''))


def create_case(root, case_id: str, examiner: str, authorization: str) -> Path:
    if not valid_case_id(case_id):
        raise ValueError('Case ID may only contain letters, digits, - and _ (max 64 characters)')
    if not examiner.strip() or not authorization.strip():
        raise ValueError('Examiner and authorization reference are both required')
    case_dir = Path(root) / case_id
    if (case_dir / 'case.json').exists():
        raise ValueError(f'Case {case_id} already exists')
    case_dir.mkdir(parents=True, exist_ok=True)
    CaseRecord(case_id, examiner.strip(), authorization.strip()).save(case_dir)
    AuditLog(case_dir / 'audit.jsonl').log('case_created', case_id=case_id,
                                           examiner=examiner.strip(),
                                           authorization=authorization.strip())
    return case_dir


def load_case(case_dir):
    case_dir = Path(case_dir)
    case = CaseRecord(**json.loads((case_dir / 'case.json').read_text()))
    return case, AuditLog(case_dir / 'audit.jsonl')


def parse_whatsapp(case_dir, db) -> int:
    '''Parse a working copy of msgstore.db into the case database.'''
    case_dir, db = Path(case_dir), Path(db)
    if not db.is_file():
        raise FileNotFoundError(f'Database not found: {db}')
    case, audit = load_case(case_dir)
    con = open_case_db(case_dir / 'case.db')
    n = add_whatsapp_messages(con, case.case_id, parse_messages(db), str(db), sha256_file(db))
    con.close()
    audit.log('wa_parsed', db=str(db), messages=n)
    return n


def generate_report(case_dir, pdf: bool = False) -> Path:
    case_dir = Path(case_dir)
    case, audit = load_case(case_dir)
    hashes = [(m.name, sha256_file(m)) for m in sorted(case_dir.glob('*.manifest.json'))]
    if not (case_dir / 'case.db').exists():
        open_case_db(case_dir / 'case.db').close()
    out = case_dir / 'report.html'
    build_report(case_dir / 'case.db', case, hashes, out, pdf)
    audit.log('report_generated', pdf=pdf)
    return out


def list_cases(root) -> list:
    cases = []
    for p in sorted(Path(root).glob('*/case.json')):
        data = json.loads(p.read_text())
        data['artifacts'] = count_artifacts(p.parent)
        cases.append(data)
    return cases


def count_artifacts(case_dir) -> int:
    db = Path(case_dir) / 'case.db'
    if not db.exists():
        return 0
    con = sqlite3.connect(db)
    try:
        return con.execute('SELECT COUNT(*) FROM artifact').fetchone()[0]
    except sqlite3.OperationalError:
        return 0
    finally:
        con.close()


def artifact_counts_by_app(case_dir) -> list:
    db = Path(case_dir) / 'case.db'
    if not db.exists():
        return []
    con = sqlite3.connect(db)
    try:
        return con.execute('SELECT app, COUNT(*) FROM artifact GROUP BY app').fetchall()
    except sqlite3.OperationalError:
        return []
    finally:
        con.close()


def get_artifacts(case_dir, q: str = '', app: str = '', sort: str = 'timestamp_utc',
                  order: str = 'desc', limit: int = 100, offset: int = 0):
    '''Return (rows, total) for the case, filtered by a plain-text search and an
    optional app category, sorted by a whitelisted column.'''
    db = Path(case_dir) / 'case.db'
    if not db.exists():
        return [], 0
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    clauses, params = [], []
    if q:
        haystack = ("coalesce(content, '') || ' ' || coalesce(sender, '') || ' ' || "
                    "coalesce(recipient, '') || ' ' || coalesce(chat, '') || ' ' || "
                    "coalesce(source_file, '')")
        clauses.append(f'instr(lower({haystack}), lower(?)) > 0')
        params.append(q)
    if app:
        clauses.append('app = ?')
        params.append(app)
    where = f'WHERE {" AND ".join(clauses)}' if clauses else ''
    if sort not in ARTIFACT_SORT_COLUMNS:
        sort = 'timestamp_utc'
    order_sql = 'ASC' if order.lower() == 'asc' else 'DESC'
    try:
        total = con.execute(f'SELECT COUNT(*) FROM artifact {where}', params).fetchone()[0]
        rows = con.execute(
            f'SELECT * FROM artifact {where} ORDER BY {sort} {order_sql}, '
            f'artifact_id {order_sql} LIMIT ? OFFSET ?',
            params + [limit, offset]).fetchall()
        return [dict(r) for r in rows], total
    except sqlite3.OperationalError:
        return [], 0
    finally:
        con.close()


def read_audit(case_dir, q: str = '') -> list:
    '''Read the audit log, optionally keeping only entries matching a search term.'''
    path = Path(case_dir) / 'audit.jsonl'
    if not path.exists():
        return []
    term = q.strip().lower()
    entries = []
    for line in path.read_text().splitlines():
        entry = json.loads(line)
        if term:
            haystack = ' '.join([entry.get('time_utc', ''), entry.get('user', ''),
                                 entry.get('action', ''),
                                 json.dumps(entry.get('details', ''))]).lower()
            if term not in haystack:
                continue
        entries.append(entry)
    return entries


def last_audit_action(case_dir, actions) -> dict:
    '''Return the most recent audit entry whose action is in actions, or None.'''
    for entry in reversed(read_audit(case_dir)):
        if entry.get('action') in actions:
            return entry
    return None
