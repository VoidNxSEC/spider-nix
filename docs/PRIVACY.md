# Privacy And Trust Model

Spider-Nix JobOps is designed as a local-first job search toolkit. The core workflow should work without uploading your resume, profile, notes, or application history to a hosted account.

## Default Data Boundary

By default, Spider-Nix stores job hunt data in local files:

- job opportunities in SQLite;
- application pipeline status in SQLite;
- profile preferences in SQLite;
- exported jobs or applications only when the user asks for an export;
- browser autofill activity inside the local browser session.

The project should not add background telemetry, hidden sync, or remote profile upload to the core workflow.

## Sensitive Data

Job search workflows can include sensitive information:

- resume contents;
- email, phone, location, and links;
- work authorization answers;
- salary expectations;
- application notes;
- recruiter contact details;
- rejection and interview history.

Spider-Nix should treat these as user-controlled records. Features that inspect or transform sensitive data should run locally unless a future integration clearly asks for consent and documents what is sent.

## Autofill Boundary

Autofill is designed to reduce repeated typing, not to remove judgment from the application process.

Expected behavior:

- analyze fields before filling them;
- show confidence where possible;
- fill high-confidence standard fields;
- leave uncertain or sensitive fields for manual review;
- pause in live mode so the user can inspect the form before submission;
- avoid silent mass submission.

The user remains responsible for reviewing every application before submitting it.

## Exports And Sharing

Exports should be explicit. When the tool writes JSON, SQLite databases, reports, or diagnostic bundles, the user should choose that action and know where the file is written.

Future diagnostic exports should redact or omit sensitive profile fields by default.

## Future Paid Or Hosted Features

Paid features must preserve the trust boundary:

- Pro features can add workflow depth without taking away local data ownership.
- Optional sync must be opt-in.
- Optional hosted dashboards must clearly document uploaded data.
- License checks should not require uploading resume/profile contents.
- Marketplace templates or source packs should be verifiable and reviewable.

## Responsible Automation

Spider-Nix should optimize quality and consistency, not spam volume.

The product should avoid:

- silent mass applications;
- bypassing application systems;
- hiding generated answers from the user;
- filling sensitive compliance questions without review;
- ignoring source rate limits or site stability.

This boundary is both a product principle and a business advantage: technical candidates and coaches need a tool they can trust with career data.
