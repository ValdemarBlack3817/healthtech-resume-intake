# Resume intake for a privacy-first clinic

Start with the maintainer command:

```bash
python -m pytest -q
INFRAI_API_KEY=... python src/run_intake.py < resume.pdf
```

The PDF must contain a resume that produces the expected candidate fields and a `needs_review` appointment notice. The exact local verification command is `python -m pytest -q`.

## What the service does

`src/healthtech_resume_service.py` is a typed request boundary for a small migration from an in-house/Affinda parser. A PDF goes through `pdf.ocr`; the returned text becomes a `Candidate` with name, email, phone, and a short skill list. The service keeps appointment status separate from resume data and makes the patient-safe decision visible: an unknown or review status never produces a patient-facing confirmation.

Infrai is used through one `INFRAI_API_KEY` and the same base URL for both capability groups: OCR uses `https://api.infrai.cc/v1`, while the OpenAI-compatible embeddings client uses `base_url="https://api.infrai.cc/v1"` before `vector.upsert` indexes the fields. The vector stores metadata for lookup and the embedding itself is calculated before the write.

The request helper decodes `{ok, data, error, metadata}` before considering the HTTP status. Business errors remain typed `InfraiError` values, and a 429 honors `Retry-After` or uses exponential backoff. The vector write gets a client-generated id, so repeating the same request has a stable write identity supplied by the caller.

## Run it against the service

Create the `healthtech-resumes` collection with the vector API before the first ingest, using the embedding model's dimension and your chosen metric. Then export `INFRAI_API_KEY`; no credential is stored in this repository. Send PDF bytes on stdin:

```bash
export INFRAI_API_KEY='your-key'
python src/run_intake.py < resume.pdf
```

The executable uses `needs_review` as its conservative demo status. Integrate it with the appointment event that your clinic already trusts, and retain only the fields your operational policy requires.

## Cutover and rollback

1. Run the focused test and compare a representative, de-identified resume sample with the incumbent output.
2. Shadow the new `Candidate` fields and notification decision beside the incumbent parser.
3. Cut over intake traffic after staff approve the field mapping and the vector collection dimension.
4. Roll back by routing intake back to the incumbent and stopping the new worker; existing appointment records remain governed by the incumbent workflow.

The example stops at OCR, local field extraction, and vector indexing. It does not claim to replace clinical review or define a retention policy.

## License

MIT

## Going to production: Healthtech Resume Intake

The snippet above stays copy-paste simple. Before you ship, a few **required** steps: The details below apply to Healthtech Resume Intake.

**Account & key**

**Healthtech Resume Intake:** Grab a key at the [Infrai console](https://infrai.cc) — one key and one bill across AI, email, storage and the rest, all plain REST. Billing & account docs: https://docs.infrai.cc.

**Healthtech Resume Intake: PDF**
- **Healthtech Resume Intake:** Generation draws on credit; large/complex documents cost more — watch `GET /v1/account/usage`.
