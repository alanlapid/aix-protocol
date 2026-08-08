# Contributing to aix-protocol

Thanks for considering a contribution to `.aix`. This document covers how
to propose changes, what we expect from them, and how governance works
while the spec is pre-1.0.

## Proposing Spec Changes

All changes to `AIX-SPEC.md` start as a [GitHub Issue](https://github.com/alanlapid/aix-protocol/issues).
Before opening one:

1. Check existing issues and closed PRs — your idea may already be
   discussed.
2. Describe the **problem**, not just the proposed field/change. "Memory
   records have no way to express X" is more useful than "add field Y".
3. If the change affects the JSON schema (new field, changed type,
   changed semantics), it needs an RFC (see below) before a PR will be
   merged — small typo/wording fixes to the spec text don't.

## RFC Process (schema changes)

1. Open an issue tagged `rfc` with: the problem, the proposed schema
   change (before/after JSON), and backward-compatibility impact.
2. Discussion happens on the issue. The maintainer (Geometrical, see
   Governance below) will label it `accepted`, `rejected`, or
   `needs-revision`.
3. Once `accepted`, submit a PR that updates `AIX-SPEC.md`,
   `aix_parser.py`, and at least one file in `examples/` demonstrating
   the new field. `CHANGELOG.md` gets an entry under `[Unreleased]`.
4. Merged RFCs land in the next MINOR (new optional field) or MAJOR
   (breaking change) version, per the versioning rules in
   `AIX-SPEC.md` Section 6.

**Out of scope for RFCs:** the specific mechanism behind PII
transformation (`AIX-SPEC.md` Section 5). The format's contract is
intentionally mechanism-agnostic — `pii_protected: true` plus the
restoration guarantee — so that any implementation can plug in its own
transformation. Geometrical's own mechanism is under Patent Application
P202631047 and isn't part of the open spec; RFCs proposing to specify
*how* transformation must work will be declined, RFCs proposing *what
metadata* the format should carry about it are welcome.

## Compatibility Requirements

- A parser claiming `.aix` vX.Y compliance **must** correctly read every
  file valid under vX.0 through vX.Y (backward compatibility within a
  MAJOR version — see `AIX-SPEC.md` Section 6).
- New required fields are a MAJOR bump, never a MINOR one. New *optional*
  fields are MINOR.
- Every schema change PR must update `examples/full.aix` (or add a new
  example) so `AIXEnvelope.validate()` exercises the new field, and must
  keep `examples/minimal.aix` valid under the new schema without
  modification — minimal files should stay minimal across MINOR bumps.
- Run `python -m unittest discover -s tests -v` before submitting; CI
  runs it again on Python 3.10/3.11/3.12.

## Adding Your Implementation

If you've built something that reads or writes `.aix` files, add it to
the **Implementations** table in `README.md`:

```markdown
| [Your Project](https://your-url) | One-line description | v0.x |
```

Open a PR with just that line. No approval process beyond "does it
actually implement the format" — we'll ask for a link to your parser or
a sample `.aix` file it produced if that's not obvious from your repo.

## Code of Conduct

This project follows the [Contributor Covenant](https://www.contributor-covenant.org/version/2/1/code_of_conduct/).
By participating, you're expected to uphold it. Report unacceptable
behavior via a GitHub Issue or by contacting the maintainers directly.

## Governance

Geometrical maintains `aix-protocol` through v0.x — final say on RFCs,
releases, and spec wording rests with the Geometrical team during this
period, in exchange for absorbing the cost of stewardship while the
format stabilizes.

At **v1.0**, governance opens to a community steering committee: seats
allocated to active implementers (parsers in production use, not just
toy projects), with Geometrical retaining a seat but not a veto. The
exact committee structure will be published as its own RFC before the
v1.0 cut, so the community that's supposed to run it gets to shape it.
