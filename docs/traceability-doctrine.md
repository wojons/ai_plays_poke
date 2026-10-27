# Repository Traceability Doctrine

## Purpose

Every material implementation, documentation, test, audit, and release claim in this
repository must be traceable to evidence that another developer or auditor can inspect.
The operational marker is `ch:trace`. It records the chain from a board row through the
work that was performed, the evidence observed, and the commit that contains the claim.

Traceability does not make a claim true by itself. It makes the claim reviewable:
repository artifacts must be readable from the committed tree, and claims about an
external system must name a witness that can be independently checked.

## The `ch:trace` marker

Write one single-line marker when reporting or closing material work:

```text
ch:trace row=<ID> spec=<path#anchor|none:reason> wave=<manifest#step|none:reason> test=<command-or-path|none:reason> doc=<path|none:reason> prompt=<path|none:reason> evidence=<artifact-or-witness|none:reason> witness=<external-locator|none:reason> verdict=<verdict-id|none:reason> commit=<sha|none:reason> memory=<key|none:reason>
```

All fields are required. A value must be one token; replace whitespace in a locator with
a stable, resolvable form. When a field is unavailable, use the explicit form
`none:<reason>` rather than leaving it blank or writing only `none`.

| Field | Records |
| --- | --- |
| `row` | The canonical board-row ID that owns the work. |
| `spec` | The governing specification or documented contract, preferably with an anchor. |
| `wave` | The wave manifest and dispatch step that produced the work. |
| `test` | The command, test identifier, or repeatable manual procedure that was run. |
| `doc` | The documentation artifact created, updated, or relied on. |
| `prompt` | The worker brief or governing skill/instruction artifact. |
| `evidence` | The concrete artifact that supports the claim: a committed file, test output, report, or durable external result. |
| `witness` | An independently checkable external or read-only source, such as `path@origin:<path>`, `live:<endpoint>`, `tag:<tag>@origin`, or `run:<id>`. |
| `verdict` | The independent review or judge result. |
| `commit` | The commit SHA containing the implementation or documentation being claimed. |
| `memory` | A supplementary, resolvable memory record for durable context. |

## Evidence rules

1. `row` identifies the owning work item and is never omitted.
2. Evidence must be a concrete artifact or a witness. `evidence=` must not point only to
   another board row, verdict, summary, or report that merely refers elsewhere. Follow
   links until the underlying artifact or witness is named.
3. A claim about repository behavior must be verifiable from a committed repository
   artifact and, where applicable, the recorded test or procedure. A claim about the
   outside world must name an independently checkable external witness.
4. Use `none:<reason>` for absent evidence, tests, witnesses, verdicts, commits, or
   memory. Absence is a disclosed state, not an empty field.
5. A verdict is valid evidence only when it binds to `commit=<sha>` for the exact
   reviewed change. A pre-change or unrelated verdict does not justify a later commit.
6. A passing status string, a green CI badge, or a self-authored summary is diagnostic
   context, not sufficient evidence on its own. Name the actual artifact, command
   result, witness, or verdict behind it.
7. `memory` is supplementary and never load-bearing. A memory key may preserve context,
   but it cannot replace a repository artifact, a test, evidence, a witness, or a
   verdict. Cite only memory records that resolve.

## Minimum closeout practice

Before declaring work complete, verify that the marker's paths, command, commit SHA,
and witness (if one is claimed) resolve. Keep the marker with the work report and use
it to make review reproducible. If a required link cannot yet be resolved, disclose it
with `none:<reason>` and do not represent the missing link as completed evidence.
