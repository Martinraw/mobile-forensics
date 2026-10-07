'''Local web GUI (Flask). Binds to 127.0.0.1 only.

Safeguards: Host-header check (blocks DNS rebinding), per-launch token on every POST
(blocks cross-site requests), strict case-ID validation (no path traversal), and
autoescaped templates (message text is untrusted content).'''
import csv
import io
import re
import secrets
import threading
import uuid
from pathlib import Path

from flask import (Flask, Response, abort, flash, jsonify, redirect, render_template,
                   request, send_file, url_for)
from markupsafe import Markup, escape

from .. import workflow
from ..acquisition import AcquisitionError, AcquisitionManager, detect_device, import_evidence
from ..evidence import verify_manifest
from ..whatsapp_decrypt import decrypt_backup

ALLOWED_HOSTS = {'127.0.0.1', 'localhost'}
PAGE_SIZE = 100
PAGE_SIZE_OPTIONS = (25, 50, 100, 250)
EXPECTED_ERRORS = (ValueError, RuntimeError, AcquisitionError, FileNotFoundError, OSError)


def _page_window(page: int, pages: int, width: int = 7) -> list:
    '''Page numbers to show around the current page.'''
    if pages <= 1:
        return [1]
    start = max(1, min(page - width // 2, pages - width + 1))
    end = min(pages, start + width - 1)
    return list(range(start, end + 1))


def create_app(cases_root='cases') -> Flask:
    app = Flask(__name__)
    app.secret_key = secrets.token_bytes(32)
    app.config['TOKEN'] = secrets.token_hex(16)
    root = Path(cases_root)
    root.mkdir(parents=True, exist_ok=True)
    jobs = {}

    @app.before_request
    def guard():
        if request.host.split(':')[0] not in ALLOWED_HOSTS:
            abort(400)
        if request.method == 'POST':
            sent = request.form.get('token', '')
            if not secrets.compare_digest(sent, app.config['TOKEN']):
                abort(403)

    @app.context_processor
    def inject():
        return {'token': app.config['TOKEN']}

    @app.template_filter('highlight')
    def highlight(text, term):
        '''Escape text, then wrap the search term (case-insensitive) in <mark>.'''
        body = escape('' if text is None else text)
        if not term:
            return body
        needle = escape(term)
        return Markup(re.sub(re.escape(str(needle)),
                             lambda m: f'<mark>{m.group(0)}</mark>',
                             str(body), flags=re.IGNORECASE))

    def case_dir_or_404(case_id: str) -> Path:
        if not workflow.valid_case_id(case_id):
            abort(404)
        d = root / case_id
        if not (d / 'case.json').exists():
            abort(404)
        return d

    def running_job(case_id: str):
        for job_id, job in jobs.items():
            if job['case'] == case_id and job['status'] == 'running':
                return job_id
        return None

    def start_job(case_dir: Path, title: str, fn) -> str:
        job_id = uuid.uuid4().hex[:8]
        jobs[job_id] = {'title': title, 'status': 'running', 'message': '',
                        'case': case_dir.name}

        def worker():
            try:
                jobs[job_id]['message'] = fn()
                jobs[job_id]['status'] = 'done'
            except Exception as e:  # shown to the examiner, never swallowed silently
                jobs[job_id]['message'] = f'{type(e).__name__}: {e}'
                jobs[job_id]['status'] = 'error'

        threading.Thread(target=worker, daemon=True).start()
        return job_id

    def run_action(label: str, fn):
        try:
            flash(f'{label}: {fn()}', 'ok')
        except EXPECTED_ERRORS as e:
            flash(f'{label} failed: {e}', 'error')

    def user_path(field: str) -> Path:
        value = request.form.get(field, '').strip()
        if not value:
            raise ValueError('A file path is required')
        return Path(value).expanduser()

    # ---------- pages ----------
    @app.get('/')
    def index():
        return render_template('index.html', cases=workflow.list_cases(root))

    @app.post('/cases')
    def create_case():
        try:
            case_dir = workflow.create_case(root, request.form.get('case_id', '').strip(),
                                            request.form.get('examiner', ''),
                                            request.form.get('authorization', ''))
        except ValueError as e:
            flash(str(e), 'error')
            return redirect(url_for('index'))
        flash(f'Case {case_dir.name} created', 'ok')
        return redirect(url_for('case_view', case_id=case_dir.name))

    @app.get('/case/<case_id>')
    def case_view(case_id):
        case_dir = case_dir_or_404(case_id)
        case, audit = workflow.load_case(case_dir)
        q = request.args.get('q', '').strip()
        app_filter = request.args.get('app', '').strip()
        sort = request.args.get('sort', 'timestamp_utc').strip()
        order = request.args.get('order', 'desc').strip()
        page = max(request.args.get('page', 1, type=int), 1)
        page_size = request.args.get('page_size', PAGE_SIZE, type=int)
        if page_size not in PAGE_SIZE_OPTIONS:
            page_size = PAGE_SIZE
        rows, total = workflow.get_artifacts(case_dir, q, app_filter, sort, order,
                                             page_size, (page - 1) * page_size)
        pages = max((total + page_size - 1) // page_size, 1) if total else 0
        storage = []
        for m in sorted(case_dir.glob('*.manifest.json')):
            evidence_dir = case_dir / m.name.replace('.manifest.json', '')
            problems = (verify_manifest(evidence_dir, m) if evidence_dir.is_dir()
                        else ['folder missing'])
            meta = json.loads(m.read_text()) if m.exists() else {}
            files = meta.get('files', {})
            storage.append({'name': m.name, 'folder': evidence_dir.name,
                            'files': len(files),
                            'size': sum(f.get('size', 0) for f in files.values()),
                            'problems': problems})
        device = workflow.last_audit_action(case_dir,
                                            ('device_detected', 'device_detected_gui'))
        job_id = running_job(case_id)
        recent = [dict(id=i, **j) for i, j in jobs.items() if j['case'] == case_id][-5:]
        return render_template(
            'case.html', case=case, rows=rows, total=total, q=q, app=app_filter,
            sort=sort, order=order, page=page, page_size=page_size,
            page_size_options=PAGE_SIZE_OPTIONS, pages=pages,
            page_window=_page_window(page, pages),
            counts=workflow.artifact_counts_by_app(case_dir),
            audit_ok=audit.verify(), storage=storage, device=device,
            running=job_id, jobs=recent,
            has_report=(case_dir / 'report.html').exists())

    @app.get('/case/<case_id>/audit')
    def audit_view(case_id):
        case_dir = case_dir_or_404(case_id)
        q = request.args.get('q', '').strip()
        _, audit = workflow.load_case(case_dir)
        entries = workflow.read_audit(case_dir, q)
        return render_template('audit.html', case_id=case_id, q=q, entries=entries,
                               total=len(entries), audit_ok=audit.verify())

    @app.get('/case/<case_id>/report.html')
    def report_file(case_id):
        case_dir = case_dir_or_404(case_id)
        path = case_dir / 'report.html'
        if not path.exists():
            abort(404)
        return send_file(path.resolve(), mimetype='text/html')

    @app.get('/case/<case_id>/report.csv')
    def report_csv(case_id):
        case_dir = case_dir_or_404(case_id)
        path = case_dir / 'report.csv'
        if not path.exists():
            abort(404)
        return send_file(path.resolve(), as_attachment=True, download_name=f'{case_id}.csv')

    @app.get('/case/<case_id>/artifacts.csv')
    def artifacts_csv(case_id):
        '''Export the currently filtered and sorted artifact list as CSV.'''
        case_dir = case_dir_or_404(case_id)
        q = request.args.get('q', '').strip()
        app_filter = request.args.get('app', '').strip()
        sort = request.args.get('sort', 'timestamp_utc').strip()
        order = request.args.get('order', 'desc').strip()
        rows, _ = workflow.get_artifacts(case_dir, q, app_filter, sort, order,
                                         limit=1_000_000, offset=0)
        buf = io.StringIO()
        if rows:
            writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
        return Response(buf.getvalue(), mimetype='text/csv', headers={
            'Content-Disposition': f'attachment; filename="{case_id}_artifacts.csv"'})

    @app.get('/jobs/<job_id>')
    def job_status(job_id):
        job = jobs.get(job_id)
        if job is None:
            abort(404)
        return jsonify(status=job['status'], message=job['message'], title=job['title'])

    # ---------- actions ----------
    def guarded(case_id):
        case_dir = case_dir_or_404(case_id)
        if running_job(case_id):
            flash('A job is already running on this case. Wait for it to finish.', 'error')
            return None
        return case_dir

    @app.post('/case/<case_id>/detect')
    def detect(case_id):
        case_dir = case_dir_or_404(case_id)
        _, audit = workflow.load_case(case_dir)

        def do():
            info = detect_device()
            audit.log('device_detected_gui', **info.__dict__)
            rooted = 'rooted' if info.is_rooted else 'not rooted'
            return f'{info.platform} {info.model}, OS {info.os_version} ({rooted})'
        run_action('Device detection', do)
        return redirect(url_for('case_view', case_id=case_id))

    @app.post('/case/<case_id>/acquire')
    def acquire(case_id):
        case_dir = guarded(case_id)
        if case_dir is None:
            return redirect(url_for('case_view', case_id=case_id))
        if request.form.get('confirm') != 'yes':
            flash('Tick the authorization confirmation before acquiring.', 'error')
            return redirect(url_for('case_view', case_id=case_id))

        def do():
            _, audit = workflow.load_case(case_dir)
            results = AcquisitionManager(case_dir, audit).acquire(detect_device())
            return 'Completed: ' + ', '.join(m.value for m, _ in results)
        start_job(case_dir, 'Acquisition', do)
        flash('Acquisition started. This page refreshes when it finishes.', 'ok')
        return redirect(url_for('case_view', case_id=case_id))

    @app.post('/case/<case_id>/import')
    def import_ev(case_id):
        case_dir = guarded(case_id)
        if case_dir is not None:
            _, audit = workflow.load_case(case_dir)
            run_action('Import', lambda: f'saved to {import_evidence(user_path("path"), case_dir, audit)}')
        return redirect(url_for('case_view', case_id=case_id))

    @app.post('/case/<case_id>/wa-decrypt')
    def wa_decrypt(case_id):
        case_dir = guarded(case_id)
        if case_dir is not None:
            _, audit = workflow.load_case(case_dir)

            def do():
                key = request.form.get('key', '').strip()
                if not key:
                    raise ValueError('A key file path or 64-character key is required')
                out = case_dir / 'whatsapp' / 'msgstore.db'
                out.parent.mkdir(exist_ok=True)
                decrypt_backup(key, user_path('path'), out, audit)
                return f'decrypted database saved to {out}'
            run_action('WhatsApp decryption', do)
        return redirect(url_for('case_view', case_id=case_id))

    @app.post('/case/<case_id>/wa-parse')
    def wa_parse(case_id):
        case_dir = guarded(case_id)
        if case_dir is not None:
            run_action('WhatsApp parsing',
                       lambda: f'{workflow.parse_whatsapp(case_dir, user_path("path"))} messages added')
        return redirect(url_for('case_view', case_id=case_id))

    @app.post('/case/<case_id>/report')
    def make_report(case_id):
        case_dir = guarded(case_id)
        if case_dir is not None:
            pdf = request.form.get('pdf') == 'yes'
            run_action('Report', lambda: f'written to {workflow.generate_report(case_dir, pdf)}')
        return redirect(url_for('case_view', case_id=case_id))

    return app
