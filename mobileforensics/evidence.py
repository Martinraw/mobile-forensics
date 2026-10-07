'''Evidence preservation: hashing, manifests and a tamper-evident audit log.'''
import getpass
import hashlib
import json
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path

TOOL_VERSION = '0.1.0'


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def sha256_file(path: Path, chunk: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        while block := f.read(chunk):
            h.update(block)
    return h.hexdigest()


@dataclass
class CaseRecord:
    case_id: str
    examiner: str
    authorization_ref: str  # warrant, court order or written consent reference
    created_utc: str = ''

    def save(self, case_dir: Path) -> None:
        self.created_utc = self.created_utc or utc_now()
        (Path(case_dir) / 'case.json').write_text(json.dumps(asdict(self), indent=2))


class AuditLog:
    '''Append-only JSON-lines log. Each entry stores the hash of the previous
    entry, so any later edit or deletion breaks the chain.'''

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._prev = '0' * 64
        if self.path.exists():
            for line in self.path.read_text().splitlines():
                self._prev = json.loads(line)['entry_hash']

    def log(self, action: str, **details) -> None:
        entry = {'time_utc': utc_now(), 'user': getpass.getuser(),
                 'tool_version': TOOL_VERSION, 'action': action,
                 'details': details, 'prev_hash': self._prev}
        entry['entry_hash'] = hashlib.sha256(
            json.dumps(entry, sort_keys=True).encode()).hexdigest()
        with open(self.path, 'a') as f:
            f.write(json.dumps(entry) + '\n')
        self._prev = entry['entry_hash']

    def verify(self) -> bool:
        prev = '0' * 64
        for line in self.path.read_text().splitlines():
            entry = json.loads(line)
            claimed = entry.pop('entry_hash')
            digest = hashlib.sha256(json.dumps(entry, sort_keys=True).encode()).hexdigest()
            if entry['prev_hash'] != prev or digest != claimed:
                return False
            prev = claimed
        return True


def build_manifest(root: Path, manifest_path: Path) -> dict:
    '''Hash every file under root and write a manifest (path -> sha256, size).'''
    files = {}
    for p in sorted(Path(root).rglob('*')):
        if p.is_file():
            files[str(p.relative_to(root))] = {'sha256': sha256_file(p),
                                               'size': p.stat().st_size}
    manifest = {'created_utc': utc_now(), 'root': str(root), 'files': files}
    Path(manifest_path).write_text(json.dumps(manifest, indent=2))
    return manifest


def verify_manifest(root: Path, manifest_path: Path) -> list:
    '''Return a list of problems (an empty list means every file matches).'''
    manifest = json.loads(Path(manifest_path).read_text())
    problems = []
    for rel, meta in manifest['files'].items():
        p = Path(root) / rel
        if not p.exists():
            problems.append(f'missing: {rel}')
        elif sha256_file(p) != meta['sha256']:
            problems.append(f'hash mismatch: {rel}')
    return problems
