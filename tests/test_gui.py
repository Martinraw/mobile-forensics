import sqlite3

import pytest

from mobileforensics.gui.app import create_app
from tests.test_whatsapp_parser import make_modern_db


@pytest.fixture
def ctx(tmp_path):
    app = create_app(tmp_path / 'cases')
    app.config['TESTING'] = True
    return app.test_client(), app, tmp_path


def post(client, app, url, **data):
    data['token'] = app.config['TOKEN']
    return client.post(url, data=data, follow_redirects=True)


def new_case(client, app, case_id='T1'):
    return post(client, app, '/cases', case_id=case_id, examiner='Tester', authorization='TEST')


def test_index_loads(ctx):
    client, _, _ = ctx
    r = client.get('/')
    assert r.status_code == 200 and b'New case' in r.data


def test_post_without_token_is_rejected(ctx):
    client, _, _ = ctx
    r = client.post('/cases', data={'case_id': 'X', 'examiner': 'a', 'authorization': 'b'})
    assert r.status_code == 403


def test_foreign_host_is_rejected(ctx):
    client, _, _ = ctx
    assert client.get('/', base_url='http://evil.example').status_code == 400


def test_create_case_and_reject_bad_ids(ctx):
    client, app, tmp = ctx
    assert b'Case T1 created' in new_case(client, app).data
    assert (tmp / 'cases' / 'T1' / 'case.json').exists()
    assert b'letters, digits' in new_case(client, app, '../evil').data
    assert client.get('/case/..%2Fetc').status_code == 404


def test_authorization_is_required(ctx):
    client, app, _ = ctx
    r = post(client, app, '/cases', case_id='T2', examiner='Tester', authorization='  ')
    assert b'required' in r.data


def test_parse_search_and_html_escaping(ctx):
    client, app, tmp = ctx
    new_case(client, app)
    db = tmp / 'msgstore.db'
    make_modern_db(db)
    con = sqlite3.connect(db)
    con.execute("INSERT INTO message VALUES (3, 1, 0, 'X', 1, 1700000120000, 0, "
                "'<script>alert(1)</script>')")
    con.commit()
    con.close()

    r = post(client, app, '/case/T1/wa-parse', path=str(db))
    assert b'3 messages added' in r.data

    page = client.get('/case/T1').data
    assert b'hello' in page and b'hi back' in page
    assert b'<script>alert(1)</script>' not in page
    assert b'&lt;script&gt;' in page

    found = client.get('/case/T1?q=HI BACK').data
    assert b'hi back' in found and b'hello' not in found


def test_report_and_audit_pages(ctx):
    client, app, _ = ctx
    new_case(client, app)
    assert b'written to' in post(client, app, '/case/T1/report').data
    assert client.get('/case/T1/report.html').status_code == 200
    audit = client.get('/case/T1/audit')
    assert audit.status_code == 200 and b'chain intact' in audit.data


def test_acquire_requires_confirmation(ctx):
    client, app, _ = ctx
    new_case(client, app)
    r = post(client, app, '/case/T1/acquire')
    assert b'authorization confirmation' in r.data
