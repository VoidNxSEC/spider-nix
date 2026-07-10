# Review Checklist

Use this checklist for deeper repo assessments or production-readiness reviews.

## Nix Surface

- Confirm the flake exports the shells, packages, apps, or checks that docs tell users to run.
- Confirm `nix develop --command` provides every tool required by the documented local workflow.
- Confirm shell hooks do not advertise commands that are unavailable or renamed.
- Confirm package or app outputs still build when they are claimed to be release artifacts.

## Developer Workflow

- Compare `justfile`, scripts, and docs for command-name drift.
- Look for commands that rely on tools not present in the dev shell.
- Look for repetitive manual sequences that should become a task runner entry or flake check.

## Quality Gates

- Identify whether lint, typecheck, unit tests, integration tests, and security checks exist.
- Confirm critical checks can run locally through the documented Nix workflow.
- Compare local guidance with CI commands; flag mismatches.
- Flag important code paths with no targeted tests.

## Production Readiness

- Check whether release/build instructions are concrete and reproducible.
- Check whether operational assumptions are documented: config, secrets, migrations, background services, or browsers/toolchains.
- Check whether the repository clearly separates experimental features from supported delivery paths.

## Reporting

- Distinguish verified defects from likely risks.
- Prefer concrete reproductions over generic advice.
- Suggest the smallest changes that improve alignment, not a full platform rewrite.
