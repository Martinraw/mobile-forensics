'''WhatsApp backup decryption using wa-crypt-tools (pip install wa-crypt-tools).'''
import shutil
import subprocess
from pathlib import Path

from .evidence import AuditLog, sha256_file

SQLITE_HEADER = b'SQLite format 3' + bytes([0])


def decrypt_backup(key, encrypted: Path, output: Path, audit: AuditLog) -> Path:
    '''key: path to the Android key file, or the 64-character hex backup key.
    Use only a key obtained lawfully: from a file system acquisition of an
    authorized device, or supplied by the owner or under legal authority.'''
    if shutil.which('wadecrypt') is None:
        raise RuntimeError('wadecrypt not found. Run: pip install wa-crypt-tools')
    proc = subprocess.run(['wadecrypt', str(key), str(encrypted), str(output)],
                          capture_output=True, text=True)
    if proc.returncode != 0:
        audit.log('wa_decrypt_failed', source=str(encrypted), error=proc.stderr.strip())
        raise RuntimeError(proc.stderr.strip())
    with open(output, 'rb') as f:
        if f.read(len(SQLITE_HEADER)) != SQLITE_HEADER:
            raise RuntimeError('Output is not a SQLite database (wrong key or format)')
    # The key itself is never written to the log.
    audit.log('wa_decrypt_ok', source=str(encrypted),
              source_sha256=sha256_file(encrypted), output=str(output),
              output_sha256=sha256_file(output))
    return output
