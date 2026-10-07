'''Report generation from the case database.'''
import csv
import sqlite3
from pathlib import Path

from jinja2 import Environment

from .evidence import utc_now

TEMPLATE = Environment(autoescape=True).from_string('''<!doctype html>
<html><head><meta charset='utf-8'><title>Case {{ case.case_id }}</title>
<style>body{font-family:sans-serif;margin:2em}table{border-collapse:collapse;width:100%}
td,th{border:1px solid #ccc;padding:4px;font-size:13px;vertical-align:top}</style></head>
<body>
<h1>Forensic report: case {{ case.case_id }}</h1>
<p>Examiner: {{ case.examiner }}<br>Authorization: {{ case.authorization_ref }}<br>
Generated (UTC): {{ now }}</p>
<h2>Evidence manifests (SHA-256)</h2>
<ul>{% for name, sha in hashes %}<li>{{ name }}: <code>{{ sha }}</code></li>{% endfor %}</ul>
<h2>Artifacts ({{ rows|length }})</h2>
<table><tr><th>Time (UTC)</th><th>App</th><th>From</th><th>To</th><th>Content</th><th>Source</th></tr>
{% for r in rows %}<tr><td>{{ r.timestamp_utc }}</td><td>{{ r.app }}</td><td>{{ r.sender }}</td>
<td>{{ r.recipient }}</td><td>{{ r.content }}</td><td>{{ r.source_table }}#{{ r.source_rowid }}</td></tr>
{% endfor %}</table></body></html>''')


def build_report(db_path, case, hashes, out_html: Path, pdf: bool = False) -> None:
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    rows = con.execute('SELECT * FROM artifact WHERE case_id = ? ORDER BY timestamp_utc',
                       (case.case_id,)).fetchall()
    html = TEMPLATE.render(case=case, rows=rows, hashes=hashes, now=utc_now())
    out_html = Path(out_html)
    out_html.write_text(html, encoding='utf-8')
    if rows:
        with open(out_html.with_suffix('.csv'), 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(rows[0].keys())
            writer.writerows([tuple(r) for r in rows])
    if pdf:
        from weasyprint import HTML  # optional dependency
        HTML(string=html).write_pdf(str(out_html.with_suffix('.pdf')))
