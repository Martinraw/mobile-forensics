'''Command-line interface: python -m mobileforensics --help'''
import webbrowser
from pathlib import Path

import typer

from . import workflow
from .acquisition import AcquisitionManager, detect_device, import_evidence
from .whatsapp_decrypt import decrypt_backup

app = typer.Typer(help='Mobile forensic acquisition and analysis framework')


@app.command()
def init(case_id: str, examiner: str, authorization: str, root: Path = Path('cases')):
    '''Create a case. AUTHORIZATION is the warrant, order or consent reference.'''
    try:
        case_dir = workflow.create_case(root, case_id, examiner, authorization)
    except ValueError as e:
        typer.echo(f'Error: {e}')
        raise typer.Exit(1)
    typer.echo(f'Case created: {case_dir}')


@app.command()
def acquire(case_dir: Path):
    '''Detect the connected device and run every available method.'''
    _, audit = workflow.load_case(case_dir)
    for method, out in AcquisitionManager(case_dir, audit).acquire(detect_device()):
        typer.echo(f'{method.value}: {out}')


@app.command('import-evidence')
def import_cmd(case_dir: Path, source: Path):
    '''Register an image or folder produced by another tool.'''
    _, audit = workflow.load_case(case_dir)
    typer.echo(f'Imported to {import_evidence(source, case_dir, audit)}')


@app.command('wa-decrypt')
def wa_decrypt(case_dir: Path, encrypted: Path, key: str):
    '''KEY is a key file path or the 64-character hex backup key.'''
    _, audit = workflow.load_case(case_dir)
    out = case_dir / 'whatsapp' / 'msgstore.db'
    out.parent.mkdir(exist_ok=True)
    decrypt_backup(key, encrypted, out, audit)
    typer.echo(f'Decrypted database: {out}')


@app.command('wa-parse')
def wa_parse(case_dir: Path, db: Path):
    '''Parse a working copy of msgstore.db into the case database.'''
    typer.echo(f'{workflow.parse_whatsapp(case_dir, db)} messages added')


@app.command()
def report(case_dir: Path, pdf: bool = False):
    '''Write report.html (and CSV, optionally PDF) to the case folder.'''
    workflow.generate_report(case_dir, pdf)
    typer.echo('Report written')


@app.command('verify-audit')
def verify_audit(case_dir: Path):
    '''Check that the audit log has not been altered.'''
    _, audit = workflow.load_case(case_dir)
    typer.echo('Audit log intact' if audit.verify() else 'AUDIT LOG HAS BEEN ALTERED')


@app.command()
def gui(port: int = 5000, root: Path = Path('cases'), open_browser: bool = True):
    '''Start the local web GUI (127.0.0.1 only).'''
    from .gui.app import create_app
    url = f'http://127.0.0.1:{port}'
    typer.echo(f'GUI running at {url}  (press Ctrl+C to stop)')
    if open_browser:
        webbrowser.open(url)
    create_app(root).run(host='127.0.0.1', port=port, debug=False)


if __name__ == '__main__':
    app()
