'''Acquisition engine tests against a fake `adb` (no phone needed; POSIX only).'''
import io
import json
import os
import stat
import sys
import tarfile
import threading
import time

import pytest

from mobileforensics.acquisition import (AcquisitionCancelled, AcquisitionError,
                                         AcquisitionManager, Control, DeviceInfo, Method)
from mobileforensics.evidence import AuditLog, verify_manifest

pytestmark = pytest.mark.skipif(sys.platform == 'win32', reason='fake adb is a POSIX script')

FAKE_ADB = r'''#!/usr/bin/env python3
import io, os, sys, tarfile, time
a = sys.argv[1:]
if a[:1] == ['-s']:
    a = a[2:]
if a[0] == 'get-state':
    print('device')
elif a[0] == 'shell':
    if a[1] == 'getprop':
        print('[ro.product.model]: [TestPhone]' if len(a) == 2 else 'TestPhone')
    elif a[1] == 'pm':
        print('package:/data/app/com.whatsapp/base.apk=com.whatsapp')
    elif a[1] == 'content':
        if 'calendar' in a[-1]:
            sys.stderr.write('Permission Denial\n'); sys.exit(1)
        print('Row: 0 address=+260000000, body=hello')
elif a[0] == 'pull':
    if os.environ.get('FAKE_ADB_SLOW'):
        time.sleep(30)
    src, dest = a[1], a[2]
    if src == '/sdcard/DCIM':
        d = os.path.join(dest, 'DCIM'); os.makedirs(d, exist_ok=True)
        open(os.path.join(d, 'a.jpg'), 'wb').write(b'\xff\xd8photo-bytes')
        print('[ 50%] /sdcard/DCIM/a.jpg'); print('[100%] /sdcard/DCIM/a.jpg')
    else:
        sys.stderr.write("adb: error: remote object '%s' does not exist\n" % src); sys.exit(1)
elif a[0] == 'exec-out':
    cmd = a[1]
    if 'tar -cf - /data/data' in cmd and cmd.startswith("su -c '"):
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode='w') as t:
            info = tarfile.TarInfo('data/data/com.whatsapp/msgstore.db'); data = b'SQLite'
            info.size = len(data); t.addfile(info, io.BytesIO(data))
        sys.stdout.buffer.write(buf.getvalue())
    else:
        sys.stderr.write('tar: no such path\n'); sys.exit(2)
'''


@pytest.fixture
def fake_adb(tmp_path, monkeypatch):
    bindir = tmp_path / 'bin'
    bindir.mkdir()
    exe = bindir / 'adb'
    exe.write_text(FAKE_ADB)
    exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv('PATH', f'{bindir}{os.pathsep}{os.environ["PATH"]}')
    return exe


@pytest.fixture
def case(tmp_path):
    case_dir = tmp_path / 'case'
    case_dir.mkdir()
    return case_dir, AuditLog(case_dir / 'audit.jsonl')


def test_logical_acquisition_is_real_hashed_and_verified(fake_adb, case):
    case_dir, audit = case
    mgr = AcquisitionManager(case_dir, audit)
    messages = []
    results = mgr.acquire(DeviceInfo('android', 'SER1', 'TestPhone', '14'),
                          {Method.LOGICAL}, Control(lambda m, p: messages.append((m, p))))
    (method, out), = results
    assert method is Method.LOGICAL
    assert (out / 'files' / 'DCIM' / 'a.jpg').read_bytes() == b'\xff\xd8photo-bytes'
    assert 'hello' in (out / 'sms.txt').read_text()
    row = mgr.report[0]
    assert row['status'] == 'partial'                  # calendar denied -> recorded, not hidden
    assert any('calendar' in e for e in row['errors'])
    assert row['verified'] is True and row['files'] >= 5 and row['size_bytes'] > 0
    assert verify_manifest(out, row['manifest']) == []
    assert audit.verify()
    actions = [json.loads(ln)['action'] for ln in (case_dir / 'audit.jsonl').read_text().splitlines()]
    assert {'acquisition_start', 'manifest_written', 'manifest_verified',
            'acquisition_complete'} <= set(actions)
    assert any(p == 100 for _, p in messages) and any('DCIM' in m for m, _ in messages)


def test_second_run_never_overwrites_first(fake_adb, case):
    case_dir, audit = case
    info = DeviceInfo('android', 'SER1', 'TestPhone', '14')
    first = AcquisitionManager(case_dir, audit).acquire(info, {Method.LOGICAL})[0][1]
    second = AcquisitionManager(case_dir, audit).acquire(info, {Method.LOGICAL})[0][1]
    assert first != second and first.exists() and second.exists()


def test_rooted_filesystem_archives_with_correct_su_quoting(fake_adb, case):
    case_dir, audit = case
    info = DeviceInfo('android', 'SER1', 'TestPhone', '14', is_rooted=True)
    mgr = AcquisitionManager(case_dir, audit)
    (method, out), = mgr.acquire(info, {Method.FILESYSTEM})
    tar_path = out / 'data_data.tar'
    with tarfile.open(tar_path) as t:
        assert 'data/data/com.whatsapp/msgstore.db' in t.getnames()
    assert any('/data/system' in e for e in mgr.report[0]['errors'])  # failing paths are logged


def test_filesystem_refused_when_not_rooted(fake_adb, case):
    case_dir, audit = case
    with pytest.raises(AcquisitionError, match='None of the requested methods'):
        AcquisitionManager(case_dir, audit).acquire(
            DeviceInfo('android', 'SER1', 'TestPhone', '14'), {Method.FILESYSTEM})


def test_cancel_stops_quickly_and_preserves_partial_evidence(fake_adb, case, monkeypatch):
    monkeypatch.setenv('FAKE_ADB_SLOW', '1')
    case_dir, audit = case
    stop = threading.Event()
    threading.Timer(1.0, stop.set).start()
    mgr = AcquisitionManager(case_dir, audit)
    t0 = time.monotonic()
    with pytest.raises(AcquisitionCancelled):
        mgr.acquire(DeviceInfo('android', 'SER1', 'TestPhone', '14'), {Method.LOGICAL},
                    Control(is_cancelled=stop.is_set))
    assert time.monotonic() - t0 < 10
    assert mgr.report[0]['status'] == 'cancelled'
    assert mgr.report[0]['manifest'] is not None       # what was collected is still hashed
    assert audit.verify()
    actions = [json.loads(ln)['action'] for ln in (case_dir / 'audit.jsonl').read_text().splitlines()]
    assert 'acquisition_cancelled' in actions
