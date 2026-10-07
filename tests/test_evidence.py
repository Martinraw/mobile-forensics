from mobileforensics.evidence import AuditLog, build_manifest, verify_manifest


def test_manifest_detects_change(tmp_path):
    root = tmp_path / 'evidence'
    root.mkdir()
    (root / 'a.txt').write_text('hello')
    manifest = tmp_path / 'm.json'
    build_manifest(root, manifest)
    assert verify_manifest(root, manifest) == []
    (root / 'a.txt').write_text('changed')
    assert verify_manifest(root, manifest) == ['hash mismatch: a.txt']


def test_audit_log_detects_tampering(tmp_path):
    path = tmp_path / 'audit.jsonl'
    log = AuditLog(path)
    log.log('first_action')
    log.log('second_action')
    assert log.verify()
    lines = path.read_text().splitlines()
    path.write_text(lines[0].replace('first_action', 'altered') + '\n' + lines[1] + '\n')
    assert not AuditLog(path).verify()
