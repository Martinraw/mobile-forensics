'''End-to-end test: init case -> parse WhatsApp -> report -> verify audit log.'''
from typer.testing import CliRunner

from mobileforensics.cli import app
from tests.test_whatsapp_parser import make_modern_db

runner = CliRunner()


def test_full_pipeline(tmp_path):
    root = tmp_path / 'cases'
    db = tmp_path / 'msgstore.db'
    make_modern_db(db)

    r = runner.invoke(app, ['init', 'T1', 'Test Examiner', 'TEST-AUTH', '--root', str(root)])
    assert r.exit_code == 0, r.output
    case_dir = root / 'T1'

    r = runner.invoke(app, ['wa-parse', str(case_dir), str(db)])
    assert r.exit_code == 0, r.output
    assert '2 messages added' in r.output

    r = runner.invoke(app, ['report', str(case_dir)])
    assert r.exit_code == 0, r.output
    html = (case_dir / 'report.html').read_text()
    assert 'hello' in html and 'hi back' in html
    assert (case_dir / 'report.csv').exists()

    r = runner.invoke(app, ['verify-audit', str(case_dir)])
    assert 'intact' in r.output
