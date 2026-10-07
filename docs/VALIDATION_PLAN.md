# Validation plan

## Test data

- Own test devices with seeded, known content (messages written, files created, messages deleted on purpose).
- Public reference images (CFReDS, Digital Corpora).
- Synthetic databases for parser unit tests.

## Metrics

| Area | Metric |
|---|---|
| Completeness | artifacts acquired / artifacts known to exist; deleted records recovered / deleted records created |
| Accuracy | precision = TP/(TP+FP); recall = TP/(TP+FN); field-level checks (time, sender, text) |
| Integrity | hashes match after acquisition and on re-verification; audit log verifies; repeat runs give identical hashes |
| Performance | acquisition time per GB; parse time per 1,000 messages; memory use |

## Reference tools to compare against

- Autopsy with ALEAPP / iLEAPP
- AndroidQF (acquisition output)
- A commercial tool if the Zambia Police lab can lend access
- NIST CFTT mobile device tool test specification

## Test matrix (fill in as you test)

| Device | OS version | WhatsApp version | Method | Result | Notes |
|---|---|---|---|---|---|
| | | | | | |
