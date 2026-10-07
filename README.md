# Mobile Forensic Acquisition & Analysis Framework

Master's research project in Digital Forensics, sponsored by the Zambia Police.
A modular, open-source framework for **authorized** logical and file-system acquisition of
Android and iOS devices, evidence preservation, WhatsApp and core artifact analysis, and
import of physical / file-system images created by other tools.

> **Use only on devices you own or are legally authorized to examine.** Record the
> authorization reference for every case. Never commit real case data to this repository.

## Status

Phase 1 (evidence layer, WhatsApp parser, case database, reports, CLI) is working and tested
on synthetic data. Acquisition modules (`acquisition.py`) and WhatsApp decryption
(`whatsapp_decrypt.py`) are written but **must be tested on your own test devices**.

| Phase | Deliverable | State |
|---|---|---|
| 1 | Evidence layer, audit log, tests | Done |
| 1b | Local web GUI | Done (tested on synthetic data) |
| 2 | Android logical acquisition | Written, needs device testing |
| 3 | WhatsApp decryption and parser | Parser tested; decrypt needs a real backup |
| 4 | iOS backup and ChatStorage parser | Acquisition written; parser not started |
| 5 | Import of E01 / dd / tar images | Folder and file import done; image reading not started |
| 6 | Reports and deleted-record recovery | HTML/CSV done; recovery not started |
| 7 | Validation and thesis | Not started |

## Setup (Kali Linux)

```bash
# System tools
sudo apt update
sudo apt install -y python3-venv python3-pip git adb libimobiledevice-utils usbmuxd

# Project environment
cd mobile-forensics
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Check everything works
pytest
```

You should see all tests pass.

## Try it with no phone (synthetic data)

```bash
python scripts/make_demo_db.py samples/demo_msgstore.db
python -m mobileforensics init DEMO001 "Your Name" "TEST-ONLY"
python -m mobileforensics wa-parse cases/DEMO001 samples/demo_msgstore.db
python -m mobileforensics report cases/DEMO001
python -m mobileforensics verify-audit cases/DEMO001
```

Open `cases/DEMO001/report.html` in a browser.

## GUI (local web interface)

```bash
python -m mobileforensics gui
```

Opens http://127.0.0.1:5000 in your browser (add `--port 8080` to change the port, or
`--no-open-browser` if the browser does not open automatically in your terminal).

What you can do from the GUI:

- Create cases (examiner and authorization reference are mandatory)
- Detect a connected device and start acquisition (runs in the background; page refreshes when done)
- Import evidence made by other tools
- Decrypt WhatsApp backups (key field is masked) and parse `msgstore.db` into the case
- Search and page through artifacts
- Generate HTML/CSV reports, view the audit log and verify evidence hashes

The GUI only listens on 127.0.0.1, checks the Host header, requires a per-launch token on every
action, validates case IDs and escapes all message text. Keep it local: do not expose it to a network.

## Commands

| Command | Purpose |
|---|---|
| `init CASE_ID EXAMINER AUTHORIZATION` | Create a case folder and audit log |
| `acquire CASE_DIR` | Detect a connected device and run every available method |
| `import-evidence CASE_DIR SOURCE` | Register an image or folder made by another tool |
| `wa-decrypt CASE_DIR ENCRYPTED KEY` | Decrypt a WhatsApp backup with a lawfully held key |
| `wa-parse CASE_DIR DB` | Parse a working copy of `msgstore.db` into the case database |
| `report CASE_DIR [--pdf]` | Write HTML and CSV reports |
| `verify-audit CASE_DIR` | Check the audit log has not been altered |
| `gui [--port N]` | Start the local web GUI |

Run `python -m mobileforensics --help` for details.

## Project layout

```
mobileforensics/
    evidence.py            hashing, manifests, tamper-evident audit log
    acquisition.py         Android (ADB), iOS (libimobiledevice), import, method manager
    whatsapp_decrypt.py    wrapper around wa-crypt-tools
    whatsapp_parser.py     version-aware WhatsApp message parser
    casedb.py              normalized artifact table (SQLite)
    report.py              HTML / CSV / optional PDF reports
    workflow.py            shared logic used by the CLI and the GUI
    cli.py                 Typer command-line interface
    gui/                   local web GUI (Flask app + templates)
tests/                     pytest suite (synthetic data only)
scripts/                   helper scripts (synthetic demo database)
docs/                      design, validation plan, ethics, research log
cases/                     case output (git-ignored)
samples/                   sample data (git-ignored)
```

## First real-device test (Android, your own phone)

1. Enable Developer options, then USB debugging, on a test phone with a few WhatsApp messages you wrote yourself.
2. Connect it and accept the RSA prompt. Check with `adb devices`.
3. `python -m mobileforensics init TEST001 "Your Name" "OWN-DEVICE"`
4. `python -m mobileforensics acquire cases/TEST001`
5. Check `cases/TEST001/acq_logical/` and the `*.manifest.json` hash manifest.
6. Record what worked and what failed in `docs/RESEARCH_LOG.md`.

## Documentation

- [docs/DESIGN.md](docs/DESIGN.md) architecture, scope and design decisions
- [docs/VALIDATION_PLAN.md](docs/VALIDATION_PLAN.md) how results will be measured
- [docs/ETHICS_AND_AUTHORIZATION.md](docs/ETHICS_AND_AUTHORIZATION.md) legal and ethical rules
- [docs/RESEARCH_LOG.md](docs/RESEARCH_LOG.md) running log of experiments (feeds the thesis)
- [docs/REFERENCES.md](docs/REFERENCES.md) tools and standards to study and cite

## Scope

In scope: logical and backup acquisition, file-system acquisition on authorized rooted test
devices, import of third-party images, WhatsApp decryption (lawfully held keys) and parsing,
SMS/calls/contacts, hashing, audit log, case database, reports.

Out of scope: exploit-based or lock-bypass extraction, chip-off/JTAG, cloud acquisition.
Physical extraction is supported by importing images made by other tools.

## Licence

To be decided with your supervisor. Check the licences of any third-party code before reuse
(MVT, for example, uses its own licence).
