'''Acquisition layer: Android (ADB), iOS (libimobiledevice), import, method selection.
Only use on devices you own or are legally authorized to examine.'''
import shutil
import subprocess
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from .evidence import AuditLog, build_manifest, sha256_file


class AcquisitionError(Exception):
    pass


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


def _run(cmd: list, timeout: int = 600) -> str:
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if p.returncode != 0:
        raise AcquisitionError(f'{cmd[0]} failed: {p.stderr.strip()}')
    return p.stdout


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


LOGICAL_QUERIES = {
    'sms': 'content query --uri content://sms',
    'call_log': 'content query --uri content://call_log/calls',
    'contacts': 'content query --uri content://com.android.contacts/data/phones',
}
SHARED_PATHS = ['/sdcard/DCIM', '/sdcard/Android/media/com.whatsapp', '/sdcard/WhatsApp']
ROOT_APP_PATHS = ['/data/data/com.whatsapp']  # acquire only what the case needs


class AndroidAcquirer:
    def __init__(self, info: DeviceInfo):
        self.info = info

    def _adb(self, *args, timeout: int = 600) -> str:
        return _run(['adb', '-s', self.info.serial, *args], timeout)

    def logical(self, out: Path) -> None:
        '''Logical acquisition: what the OS exposes to an authorized ADB session.'''
        out = Path(out)
        (out / 'files').mkdir(parents=True, exist_ok=True)
        (out / 'getprop.txt').write_text(self._adb('shell', 'getprop'))
        (out / 'packages.txt').write_text(self._adb('shell', 'pm', 'list', 'packages', '-f'))
        errors = []
        for name, query in LOGICAL_QUERIES.items():
            try:
                (out / f'{name}.txt').write_text(self._adb('shell', *query.split()))
            except AcquisitionError as e:
                errors.append(f'{name}: {e}')
        for path in SHARED_PATHS:
            try:
                self._adb('pull', path, str(out / 'files'), timeout=3600)
            except AcquisitionError as e:
                errors.append(f'{path}: {e}')
        (out / 'acquisition_errors.txt').write_text('\n'.join(errors))

    def filesystem_root(self, out: Path) -> None:
        '''Targeted app-data acquisition on an AUTHORIZED ROOTED TEST DEVICE.
        The su syntax differs between root solutions; adjust for your device.'''
        if not self.info.is_rooted:
            raise AcquisitionError('Device is not rooted. Use the import module instead.')
        out = Path(out)
        out.mkdir(parents=True, exist_ok=True)
        for path in ROOT_APP_PATHS:
            name = path.strip('/').replace('/', '_') + '.tar'
            with open(out / name, 'wb') as f:
                p = subprocess.run(['adb', '-s', self.info.serial, 'exec-out', 'su', '-c',
                                    f'tar -cf - {path}'],
                                   stdout=f, stderr=subprocess.PIPE, timeout=7200)
            if p.returncode != 0:
                raise AcquisitionError(p.stderr.decode(errors='replace'))


class IosAcquirer:
    def __init__(self, info: DeviceInfo):
        self.info = info

    def backup(self, out: Path) -> None:
        '''Backup through Apple's backup service (device unlocked and trusted).'''
        if not shutil.which('idevicebackup2'):
            raise AcquisitionError('libimobiledevice (idevicebackup2) is not installed')
        Path(out).mkdir(parents=True, exist_ok=True)
        _run(['idevicebackup2', 'backup', str(out)], timeout=14400)


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
    '''Runs every available method, least intrusive first, and logs each step.'''
    ORDER = [Method.LOGICAL, Method.BACKUP, Method.FILESYSTEM]

    def __init__(self, case_dir: Path, audit: AuditLog):
        self.case_dir = Path(case_dir)
        self.audit = audit

    @staticmethod
    def available(info: DeviceInfo) -> list:
        if info.platform == 'android':
            return [Method.LOGICAL] + ([Method.FILESYSTEM] if info.is_rooted else [])
        return [Method.BACKUP]

    def acquire(self, info: DeviceInfo, requested=None) -> list:
        self.audit.log('device_detected', **info.__dict__)
        android, ios = AndroidAcquirer(info), IosAcquirer(info)
        runners = {
            ('android', Method.LOGICAL): android.logical,
            ('android', Method.FILESYSTEM): android.filesystem_root,
            ('ios', Method.BACKUP): ios.backup,
        }
        results = []
        for method in self.ORDER:
            if method not in self.available(info):
                continue
            if requested and method not in requested:
                continue
            out = self.case_dir / f'acq_{method.value}'
            self.audit.log('acquisition_start', method=method.value, output=str(out))
            try:
                runners[(info.platform, method)](out)
            except AcquisitionError as e:
                self.audit.log('acquisition_failed', method=method.value, error=str(e))
                continue
            manifest = build_manifest(out, self.case_dir / f'acq_{method.value}.manifest.json')
            self.audit.log('acquisition_complete', method=method.value,
                           files=len(manifest['files']))
            results.append((method, out))
        if not results:
            raise AcquisitionError('No acquisition method succeeded')
        return results
