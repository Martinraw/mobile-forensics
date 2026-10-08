'''Acquisition layer: Android (ADB), iOS (libimobiledevice), import, method selection.
Only use on devices you own or are legally authorized to examine.

Every acquisition is hashed into a manifest, the manifest is re-verified, and each
step is written to the tamper-evident audit log. A GUI can pass a Control object to
receive progress messages and to cancel a running acquisition.'''
import re
import shutil
import subprocess
import threading
import time
from collections import deque
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from .evidence import AuditLog, build_manifest, sha256_file, verify_manifest

MIN_FREE_BYTES = 1024 ** 3  # refuse to start with less than 1 GiB free


class AcquisitionError(Exception):
    pass


class AcquisitionCancelled(AcquisitionError):
    pass


class VerificationError(AcquisitionError):
    '''Collected data no longer matches its manifest (never re-hashed over).'''


class Method(Enum):
    LOGICAL = 'logical'
    BACKUP = 'backup'
    FILESYSTEM = 'filesystem'


@dataclass
class DeviceInfo:
    platform: str          # 'android' or 'ios'
    serial: str
    model: str
    os_version: str
    is_rooted: bool = False


class Control:
    '''Optional hooks from a front end: progress messages and cooperative cancel.'''

    def __init__(self, on_progress=None, is_cancelled=None):
        self._on_progress = on_progress
        self._is_cancelled = is_cancelled

    def report(self, message: str, percent=None) -> None:
        if self._on_progress:
            self._on_progress(message, percent)

    def cancelled(self) -> bool:
        return bool(self._is_cancelled and self._is_cancelled())

    def check(self) -> None:
        if self.cancelled():
            raise AcquisitionCancelled('Cancelled by examiner')

    def scaled(self, lo: float, hi: float) -> 'Control':
        '''A Control whose 0-100 percentages are mapped into the lo-hi range.'''
        def rep(message, percent):
            self.report(message, None if percent is None
                        else int(lo + (hi - lo) * max(0, min(100, percent)) / 100))
        return Control(rep, self._is_cancelled)


NO_CONTROL = Control()


def human_size(n: float) -> str:
    for unit in ('B', 'KB', 'MB', 'GB'):
        if n < 1024 or unit == 'GB':
            return f'{n:.0f} {unit}' if unit == 'B' else f'{n:.1f} {unit}'
        n /= 1024


def _terminate(proc) -> None:
    proc.terminate()
    try:
        proc.wait(5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


def _run(cmd: list, timeout: int = 600) -> str:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                           encoding='utf-8', errors='replace')
    except (OSError, subprocess.TimeoutExpired) as e:
        raise AcquisitionError(f'{cmd[0]} failed: {e}')
    if p.returncode != 0:
        raise AcquisitionError(f'{cmd[0]} failed: {(p.stderr or p.stdout).strip()}')
    return p.stdout


def _stream(cmd: list, ctl: Control = NO_CONTROL, timeout: int = 3600, on_line=None):
    '''Run a text-producing command, forwarding each output line, honouring cancel.
    Returns (returncode, last_output_lines).'''
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, encoding='utf-8', errors='replace')
    except OSError as e:
        raise AcquisitionError(f'{cmd[0]} could not be started: {e}')
    tail = deque(maxlen=200)

    def reader():
        for line in proc.stdout:
            line = line.strip()
            if line:
                tail.append(line)
                if on_line:
                    on_line(line)

    t = threading.Thread(target=reader, daemon=True)
    t.start()
    start = time.monotonic()
    try:
        while proc.poll() is None:
            if ctl.cancelled():
                _terminate(proc)
                raise AcquisitionCancelled('Cancelled by examiner')
            if time.monotonic() - start > timeout:
                _terminate(proc)
                raise AcquisitionError(f'{cmd[0]} timed out after {timeout}s')
            time.sleep(0.2)
    finally:
        if proc.poll() is None:
            _terminate(proc)
        t.join(5)
    return proc.returncode, '\n'.join(tail)


def _stream_to_file(cmd: list, dest: Path, ctl: Control, timeout: int, label: str):
    '''Run a binary-producing command (e.g. tar over exec-out) straight into dest.
    Reports the growing file size. Returns (returncode, stderr_text).'''
    err = []
    with open(dest, 'wb') as f:
        try:
            proc = subprocess.Popen(cmd, stdout=f, stderr=subprocess.PIPE)
        except OSError as e:
            raise AcquisitionError(f'{cmd[0]} could not be started: {e}')
        t = threading.Thread(target=lambda: err.append(proc.stderr.read()), daemon=True)
        t.start()
        start = last = time.monotonic()
        try:
            while proc.poll() is None:
                if ctl.cancelled():
                    _terminate(proc)
                    raise AcquisitionCancelled('Cancelled by examiner')
                now = time.monotonic()
                if now - start > timeout:
                    _terminate(proc)
                    raise AcquisitionError(f'{cmd[0]} timed out after {timeout}s')
                if now - last >= 1:
                    last = now
                    ctl.report(f'{label}: {human_size(dest.stat().st_size)} written', None)
                time.sleep(0.2)
        finally:
            if proc.poll() is None:
                _terminate(proc)
            t.join(5)
    return proc.returncode, (err[0].decode('utf-8', 'replace').strip() if err else '')


def detect_device() -> DeviceInfo:
    '''Find the first connected Android (ADB) or iOS device.'''
    if shutil.which('adb'):
        lines = _run(['adb', 'devices']).splitlines()[1:]
        ready = [ln.split()[0] for ln in lines if ln.strip().endswith('device')]
        if ready:
            s = ready[0]

            def prop(key):
                return _run(['adb', '-s', s, 'shell', 'getprop', key]).strip()

            probe = subprocess.run(['adb', '-s', s, 'shell', 'su', '-c', 'id'],
                                   capture_output=True, text=True)
            return DeviceInfo('android', s, prop('ro.product.model'),
                              prop('ro.build.version.release'), 'uid=0' in probe.stdout)
    if shutil.which('ideviceinfo'):
        try:
            def get(key):
                return _run(['ideviceinfo', '-k', key]).strip()

            return DeviceInfo('ios', get('UniqueDeviceID'), get('ProductType'),
                              get('ProductVersion'))
        except AcquisitionError:
            pass
    raise AcquisitionError('No authorized device found. Check the cable, unlock the '
                           'phone and accept the USB debugging or Trust prompt.')


# Content providers readable by an authorized ADB shell session. Providers the OS
# denies are recorded in acquisition_errors.txt rather than aborting the run.
LOGICAL_QUERIES = {
    'sms': 'content query --uri content://sms',
    'mms': 'content query --uri content://mms',
    'call_log': 'content query --uri content://call_log/calls',
    'contacts': 'content query --uri content://com.android.contacts/data/phones',
    'calendar': 'content query --uri content://com.android.calendar/events',
}
# Shared storage reachable without root. Edit these lists to narrow or widen scope.
SHARED_PATHS = ['/sdcard/DCIM', '/sdcard/Pictures', '/sdcard/Movies', '/sdcard/Music',
                '/sdcard/Documents', '/sdcard/Download', '/sdcard/Android/media',
                '/sdcard/WhatsApp']
# Rooted, authorized test devices only. Each path is written to its own tar file.
ROOT_APP_PATHS = ['/data/data', '/data/system', '/data/system_ce', '/data/system_de',
                  '/data/misc', '/data/media/0']
# su syntaxes differ between root solutions; the first that yields data wins.
SU_WRAPPERS = ("su -c '{c}'", "su 0 sh -c '{c}'")

_ADB_PERCENT = re.compile(r'\[\s*(\d+)%\]')


class AndroidAcquirer:
    def __init__(self, info: DeviceInfo):
        self.info = info

    def _adb(self, *args, timeout: int = 600) -> str:
        return _run(['adb', '-s', self.info.serial, *args], timeout)

    def logical(self, out: Path, ctl: Control = NO_CONTROL) -> list:
        '''Logical acquisition: what the OS exposes to an authorized ADB session.
        Returns a list of non-fatal errors (also written to acquisition_errors.txt).'''
        out = Path(out)
        (out / 'files').mkdir(parents=True, exist_ok=True)
        errors = []
        total = 2 + len(LOGICAL_QUERIES) + len(SHARED_PATHS)
        done = 0

        def begin(label):
            ctl.check()
            ctl.report(label, int(100 * done / total))

        begin('Reading device properties')
        (out / 'getprop.txt').write_text(self._adb('shell', 'getprop'), encoding='utf-8')
        done += 1
        begin('Listing installed packages')
        (out / 'packages.txt').write_text(
            self._adb('shell', 'pm', 'list', 'packages', '-f'), encoding='utf-8')
        done += 1
        for name, query in LOGICAL_QUERIES.items():
            begin(f'Querying {name}')
            try:
                (out / f'{name}.txt').write_text(
                    self._adb('shell', *query.split()), encoding='utf-8')
            except AcquisitionError as e:
                errors.append(f'{name}: {e}')
            done += 1
        for path in SHARED_PATHS:
            begin(f'Pulling {path}')

            def on_line(line, path=path, base=done):
                m = _ADB_PERCENT.search(line)
                frac = int(m.group(1)) / 100 if m else 0
                ctl.report(f'Pulling {path}  {line[:90]}',
                           int(100 * (base + frac) / total))

            rc, tail = _stream(['adb', '-s', self.info.serial, 'pull', path,
                                str(out / 'files')], ctl, 7200, on_line)
            if rc != 0:
                errors.append(f'{path}: {tail.splitlines()[-1] if tail else "pull failed"}')
            done += 1
        ctl.report('Logical acquisition finished', 100)
        (out / 'acquisition_errors.txt').write_text('\n'.join(errors), encoding='utf-8')
        return errors

    def filesystem_root(self, out: Path, ctl: Control = NO_CONTROL, paths=None) -> list:
        '''File-system acquisition on an AUTHORIZED ROOTED TEST DEVICE: each path in
        ROOT_APP_PATHS is archived with tar through a root shell.'''
        if not self.info.is_rooted:
            raise AcquisitionError('Device is not rooted. Use the import module instead.')
        out = Path(out)
        out.mkdir(parents=True, exist_ok=True)
        paths = list(paths or ROOT_APP_PATHS)
        errors = []
        for i, path in enumerate(paths):
            ctl.check()
            dest = out / (path.strip('/').replace('/', '_') + '.tar')
            ok, last_err = False, ''
            for wrapper in SU_WRAPPERS:
                shell_cmd = wrapper.format(c=f'tar -cf - {path}')
                scoped = ctl.scaled(100 * i / len(paths), 100 * (i + 1) / len(paths))
                rc, last_err = _stream_to_file(
                    ['adb', '-s', self.info.serial, 'exec-out', shell_cmd],
                    dest, scoped, 14400, f'Archiving {path}')
                size = dest.stat().st_size
                if rc == 0 or (rc == 1 and size > 0):  # tar rc 1 = files changed while read
                    if rc == 1:
                        errors.append(f'{path}: tar warning: {last_err[:300]}')
                    ok = True
                    break
            if not ok:
                errors.append(f'{path}: {last_err[:300] or "no data returned"}')
                dest.unlink(missing_ok=True)
        if len(errors) >= len(paths) and not any(out.glob('*.tar')):
            raise AcquisitionError('; '.join(errors))
        (out / 'acquisition_errors.txt').write_text('\n'.join(errors), encoding='utf-8')
        ctl.report('File-system acquisition finished', 100)
        return errors


class IosAcquirer:
    def __init__(self, info: DeviceInfo):
        self.info = info

    def backup(self, out: Path, ctl: Control = NO_CONTROL) -> list:
        '''Backup through Apple's backup service (device unlocked and trusted).'''
        if not shutil.which('idevicebackup2'):
            raise AcquisitionError('libimobiledevice (idevicebackup2) is not installed')
        Path(out).mkdir(parents=True, exist_ok=True)
        cmd = ['idevicebackup2']
        if self.info.serial:
            cmd += ['-u', self.info.serial]
        cmd += ['backup', str(out)]

        def on_line(line):
            m = re.search(r'(\d{1,3})%', line)
            ctl.report(line[:110], int(m.group(1)) if m else None)

        rc, tail = _stream(cmd, ctl, 14400, on_line)
        if rc != 0:
            raise AcquisitionError(f'idevicebackup2 failed: {tail[-300:]}')
        ctl.report('iOS backup finished', 100)
        return []


def import_evidence(src: Path, case_dir: Path, audit: AuditLog) -> Path:
    '''Register an image or folder created by another tool (file system or physical).
    The original is never modified; hashes are checked after copying.'''
    src, case_dir = Path(src), Path(case_dir)
    dest = case_dir / 'imported' / src.name
    dest.parent.mkdir(parents=True, exist_ok=True)
    if src.is_dir():
        shutil.copytree(src, dest)
        audit.log('evidence_imported', source=str(src), kind='folder')
    else:
        before = sha256_file(src)
        shutil.copy2(src, dest)
        if sha256_file(dest) != before:
            raise AcquisitionError('Hash mismatch after copy')
        audit.log('evidence_imported', source=str(src), kind='file', sha256=before)
    return dest


class AcquisitionManager:
    '''Runs every available method, least intrusive first, and logs each step.
    After acquire() (even when it raises) self.report holds one dict per method.'''
    ORDER = [Method.LOGICAL, Method.BACKUP, Method.FILESYSTEM]

    def __init__(self, case_dir: Path, audit: AuditLog):
        self.case_dir = Path(case_dir)
        self.audit = audit
        self.report = []

    @staticmethod
    def available(info: DeviceInfo) -> list:
        if info.platform == 'android':
            return [Method.LOGICAL] + ([Method.FILESYSTEM] if info.is_rooted else [])
        return [Method.BACKUP]

    def _unique_dir(self, method: Method) -> Path:
        '''Never write into an existing acquisition folder.'''
        out, n = self.case_dir / f'acq_{method.value}', 1
        while out.exists() or (self.case_dir / f'{out.name}.manifest.json').exists():
            n += 1
            out = self.case_dir / f'acq_{method.value}_{n}'
        return out

    def _preflight(self, info: DeviceInfo) -> None:
        free = shutil.disk_usage(self.case_dir).free
        if free < MIN_FREE_BYTES:
            raise AcquisitionError(
                f'Only {human_size(free)} free in the case folder; need at least '
                f'{human_size(MIN_FREE_BYTES)}.')
        if info.platform == 'android':
            state = _run(['adb', '-s', info.serial, 'get-state'], 15).strip()
            if state != 'device':
                raise AcquisitionError(f'Device is not ready (adb state: {state or "unknown"})')

    def _seal(self, method: Method, out: Path, ctl: Control, verify: bool) -> dict:
        '''Hash everything collected, write the manifest and (optionally) re-verify it.'''
        manifest_path = self.case_dir / f'{out.name}.manifest.json'

        def hashing(i, n, p):
            ctl.check()
            ctl.report(f'Hashing {i}/{n}: {p.name}', int(100 * i / max(n, 1)))

        manifest = build_manifest(out, manifest_path, hashing)
        entry = {'manifest': manifest_path, 'files': len(manifest['files']),
                 'size_bytes': sum(f['size'] for f in manifest['files'].values()),
                 'manifest_sha256': sha256_file(manifest_path), 'verified': None}
        if verify:
            def verifying(i, n, p):
                ctl.check()
                ctl.report(f'Verifying {i}/{n}: {p.name}', int(100 * i / max(n, 1)))

            problems = verify_manifest(out, manifest_path, verifying)
            entry['verified'] = not problems
            self.audit.log('manifest_verified', method=method.value, ok=not problems,
                           problems=problems[:20])
            if problems:
                raise VerificationError(
                    f'Verification failed after acquisition: {problems[0]}')
        self.audit.log('manifest_written', method=method.value, path=str(manifest_path),
                       sha256=entry['manifest_sha256'], files=entry['files'],
                       size_bytes=entry['size_bytes'])
        return entry

    def acquire(self, info: DeviceInfo, requested=None, ctl: Control = NO_CONTROL,
                verify: bool = True) -> list:
        self.report = []
        self.audit.log('device_detected', **info.__dict__)
        runners = {
            ('android', Method.LOGICAL): AndroidAcquirer(info).logical,
            ('android', Method.FILESYSTEM): AndroidAcquirer(info).filesystem_root,
            ('ios', Method.BACKUP): IosAcquirer(info).backup,
        }
        methods = [m for m in self.ORDER if m in self.available(info)
                   and (not requested or m in requested)]
        if not methods:
            raise AcquisitionError('None of the requested methods is available for '
                                   f'this {info.platform} device.')
        self._preflight(info)
        results = []
        for i, method in enumerate(methods):
            lo, hi = 100 * i / len(methods), 100 * (i + 1) / len(methods)
            # 90% of each method's slice is collection, 10% is hashing/verifying
            collect = ctl.scaled(lo, lo + (hi - lo) * 0.9)
            seal = ctl.scaled(lo + (hi - lo) * 0.9, hi)
            out = self._unique_dir(method)
            row = {'method': method, 'out': out, 'status': 'failed', 'errors': [],
                   'files': 0, 'size_bytes': 0, 'manifest': None, 'manifest_sha256': ''}
            self.report.append(row)
            self.audit.log('acquisition_start', method=method.value, output=str(out))
            try:
                row['errors'] = runners[(info.platform, method)](out, collect) or []
                row.update(self._seal(method, out, seal, verify))
            except AcquisitionCancelled:
                self.audit.log('acquisition_cancelled', method=method.value)
                row['status'] = 'cancelled'
                self._seal_partial(method, out, row)
                raise
            except AcquisitionError as e:
                self.audit.log('acquisition_failed', method=method.value, error=str(e))
                row['errors'] = row['errors'] + [str(e)]
                if not isinstance(e, VerificationError):
                    self._seal_partial(method, out, row)
                continue
            row['status'] = 'partial' if row['errors'] else 'complete'
            self.audit.log('acquisition_complete', method=method.value,
                           files=row['files'], size_bytes=row['size_bytes'],
                           warnings=len(row['errors']))
            results.append((method, out))
        if not results:
            raise AcquisitionError('No acquisition method succeeded: ' + '; '.join(
                e for r in self.report for e in r['errors'])[:500])
        return results

    def _seal_partial(self, method: Method, out: Path, row: dict) -> None:
        '''Keep whatever was collected before a failure/cancel, hashed and labelled.'''
        if not out.exists():
            return
        try:
            row.update(self._seal(method, out, NO_CONTROL, verify=False))
            self.audit.log('partial_evidence_preserved', method=method.value,
                           files=row['files'])
        except Exception as e:  # never mask the original problem
            row['errors'].append(f'could not hash partial data: {e}')
