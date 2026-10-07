# Design

## Thesis claim

A modular, open-source framework for authorized logical and file-system acquisition of Android
and iOS devices, evidence preservation, WhatsApp and core artifact analysis, and import of
physical and file-system images created by other tools, validated against NIST CFTT criteria
and reference tool output.

## Principles

- Least intrusive method first (logical, then backup, then file system).
- Separate components: acquisition, preservation, parsing, reporting.
- Evidence integrity: SHA-256 manifests, tamper-evident audit log, read-only handling of originals.
- Open standards: SQLite, E01/dd/tar inputs, HTML/CSV/PDF outputs.
- Measure and report limitations; never promise universal extraction.

## Pipeline

```
Acquire (Android / iOS / Import) -> Preserve (hash, audit) -> Parse (WhatsApp, SMS, ...)
    -> Case database -> Reports
```

## Acquisition methods

| Platform | Method | Access needed | In prototype |
|---|---|---|---|
| Android | ADB logical | USB debugging authorized | Yes |
| Android | File system | Authorized rooted test device | Yes (test devices) |
| Android | Physical | Chipset dependent | Import only |
| iOS | Backup | Unlocked, trusted computer | Yes |
| iOS | Full file system / physical | Licensed tool or authorized jailbroken test device | Import only |

## WhatsApp key sources (lawful only)

1. Key file from a file system acquisition of an authorized device or an imported image.
2. 64-character backup key or password supplied by the owner or obtained under legal authority.
3. Already-decrypted database inside a file system image.

## WhatsApp schema versions handled

| Era | Tables |
|---|---|
| Legacy Android | `messages` (key_remote_jid, key_from_me, data, timestamp) |
| Modern Android | `message` + `chat` + `jid` |
| iOS (to do) | `ZWAMESSAGE`, `ZWACHATSESSION` (Apple epoch, seconds from 2001-01-01) |

Schemas change between versions. Verify against a database from every test device.

## Decisions taken

- Physical extraction is import-only (chipset-specific exploits are out of scope).
- WhatsApp decryption uses wa-crypt-tools instead of a hand-written decryptor.
- Reports use autoescaping because message text is untrusted content.

## GUI

A local Flask web app (`mobileforensics/gui`) sits on top of `workflow.py`, the same functions the
CLI uses, so both interfaces behave identically. Decisions:

- Web GUI instead of a desktop toolkit: no extra system packages on Kali, works offline, easy to demo.
- Binds to 127.0.0.1 only; Host-header check; per-launch token on all POST requests.
- Long-running acquisition runs in a background thread; one job per case at a time so the audit
  chain is never written concurrently.
- All artifact text is autoescaped because it is untrusted evidence content.
