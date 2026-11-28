# bond_esign
Role: sign a PDF on the app's own page: evidence chain, signed PDF, optional seal (SQLAlchemy 2.0 mixins, no router, no env, no mail). Contract: docs/contracts/esign.md; tests/test_schema.py pins the tables.

## Key files
- `models.py` mixins (`esign_requests`, `esign_signers`, `esign_events`); `events.py` kinds + hash chain (`append`, `verify_chain`)
- `service.py` create_request + re-exports; `signing.py` signing_view/sign; `lifecycle.py` decline/void/expire; `tokens.py` (incl. find_signer_by_key), `codes.py`
- `documents.py` build_signed_pdf/complete; `verify.py` verify_evidence (rows vs hashed events); `evidence_export.py` export; `signature_image.py` PNG + typed-name checks; `consent.py`
- `anchor.py`, `stamping.py`, `certificate*.py`, `build.py`, `seal.py`, `certs.py` PDF side; `webform.py` + `web/` panel; `types.py`, `errors.py`

## Commands
- `make setup-py` at the repo root, once (workspace venv)
- `make test T=tests/test_x.py`; `make lint`
- Postgres-marked tests (row locks): `make pg-up && make test-pg`, then `make pg-down`

## Rules
- No imports from sibling bond_* libs; no FastAPI; no `os.environ`; never read the clock (the caller passes `now`, naive UTC); never send mail.
- Service functions flush, never commit. Nothing updates or deletes an event row. Event `data` holds only str/int/bool/None/list/dict (no floats).
- The barrel names `stamp` and `evidence` are functions; their modules are `stamping.py` and `evidence_export.py` so no public function shares a submodule's name. Seal names load lazily so `import bond_esign` needs no `seal` extra (`hasattr(bond_esign, "Sealer")` raises ImportError without it).
- Never log or export a token, a code or their hashes. No keys or certificates in the tree (tests generate them).
- 300-line soft cap per source file. No customer names, real addresses or non-example.com emails.
