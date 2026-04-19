---
name: nix-delivery-guardian
description: Govern development quality in Nix-based repositories. Use when diagnosing bugs, investigating why behavior differs from docs or declared tooling, checking consistency between flake/devShell/justfile/tests/CI, assessing production readiness, finding delivery gaps, or implementing changes that must stay aligned with what the repository actually builds and ships.
---

# Nix Delivery Guardian

Use this skill to keep a Nix repository honest about what it delivers.

Prefer direct verification over assumptions. Read the repo, compare declarations against executable reality, identify gaps, fix them, and validate the result with the smallest relevant Nix-backed check.

## Operating Rules

- Inspect before editing. Locate flake outputs, dev shells, task runners, CI definitions, tests, and release paths before proposing conclusions.
- Verify runtime claims with `nix develop --command` or another flake-native command whenever the question is about what the repo actually exposes.
- Treat docs, shell banners, task runners, CI workflows, and package outputs as separate sources of truth that must be reconciled.
- Fix the narrowest layer that restores alignment. Do not add abstractions unless repetition or fragility justifies them.
- Leave a repo more coherent than you found it: code, tooling, and docs should converge.

## Workflow

1. Build context.
Read `flake.nix`, task runners such as `justfile` or scripts, test entrypoints, and CI configuration. Search for duplicated command lists, installation steps, and release claims.

2. Reproduce the claim.
If the user reports a bug or inconsistency, run the minimal command that exercises the claim. Prefer `nix develop --command <tool>` for environment issues and targeted tests for behavior issues.

3. Compare declared versus actual behavior.
Check whether the same command or capability is represented consistently across:
- flake outputs and `devShell`
- shell hooks and printed onboarding text
- task runners such as `just`
- README, CONTRIBUTING, TESTING, and release docs
- CI jobs and local validation guidance

4. Classify the gap.
Use one of these buckets:
- Broken wiring: the repo declares a command, dependency, alias, or feature that is not actually available.
- Doc drift: documentation promises behavior that no longer exists.
- Validation gap: the repo lacks a reproducible check for a critical path.
- Prod-readiness gap: packaging, CI, tests, or operational docs are insufficient for reliable delivery.
- Feature opportunity: repeated manual work or recurring confusion indicates a missing command, check, module, or workflow.

5. Fix and verify.
Implement the smallest coherent change set, then rerun the relevant Nix-backed command, test, or dry-run to prove the gap is closed.

## Review Focus

When asked to assess the repository, explicitly check:
- Environment parity: what `nix develop` provides versus what docs and task runners assume.
- Build parity: what flake packages or apps expose versus what the repo claims is shippable.
- Test posture: whether unit, integration, lint, typecheck, and security checks exist and are runnable.
- CI/CD integrity: whether CI invokes the same commands recommended locally and whether there are obvious missing gates.
- Delivery readiness: whether a newcomer can build, validate, and release from documented steps without hidden tribal knowledge.

Use [review-checklist.md](/home/kernelcore/master/spider-nix/skills/nix-delivery-guardian/references/review-checklist.md) when you need the detailed checklist.

## Implementation Guidance

When the task includes code changes:
- Preserve existing repo patterns unless they are the source of the defect.
- Prefer wiring missing dependencies into the flake or task runner instead of documenting manual setup outside Nix.
- Update documentation whenever user-facing commands, outputs, or expectations change.
- Verify new helpers are live by searching the tree for references after adding them.
- Call out residual risk when full validation cannot run.

## Output Expectations

Report findings in severity order and include concrete file references.

For review-style tasks, provide:
- the broken or risky behavior
- why it matters
- the evidence or reproduction path
- the smallest credible fix or next step

For implementation tasks, provide:
- what changed
- what command validated it
- what remains unverified, if anything

## Examples

This skill should trigger for requests like:
- "Analisa o repo e verifica por que esse bug está ocorrendo no ambiente Nix."
- "Analisa se há inconsistências entre flake, docs, CI e testes."
- "Vê se o projeto está alinhado para produção e entrega contínua."
- "Implementa a correção sem deixar o dev shell, task runner e documentação divergirem."

Read `references/review-checklist.md` only when you need the expanded checklist during a deeper repo assessment.
