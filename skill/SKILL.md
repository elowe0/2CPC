---
name: 2cpc
description: Interactive browser plans (2CPC). Use when the user asks for a "plan 2CPC" / "/2cpc" / an interactive plan to review in the browser, or pastes text starting with "2CPC <id> v" or "[2CPC]" (answers to such a plan).
---
# 2CPC — interactive plans

Tool: `python "{{CPC}}"` (stdlib only). Plans live in `<project>/.2cpc/<id>/vN/`.
DSL reference: read `{{DOCS}}` once before writing a plan, unless already known.

## Create (default method: file)
1. Write the DSL with the Write tool to a temp file (scratchpad dir if available, else `<project>/.2cpc/_draft.dsl`).
2. Long plan (>40 lines)? validate first: `python "{{CPC}}" new --check <file>` → summary + `WARN` lines, nothing written.
3. `python "{{CPC}}" new <file>` (run from the project dir, or add `--root <project>`).
   Output: `OK <id> v1 · N sections · N questions (…)` + `ids:` + `WARN` lines to fix. The browser opens.
Alternative: stdin heredoc `python "{{CPC}}" new <<'EOF' … EOF` — fragile with many apostrophes; avoid PowerShell pipes (breaks UTF-8).
End the plan with a `!next` line: 3–6 follow-up actions fitting this plan's stage, recommended one starred.
Then tell the user, in one short line, to answer and click "Générer la réponse" (same session) or
"Réponse + Contexte" (new session), then paste it here.

## Visuals
- Spatial content (layout, zones, distances, paths, trajectories, wireframes) → add a `!draw` sketch (few lines,
  see DSL) instead of describing coordinates in prose. Flow/sequence logic → `!mermaid`.
- `!img` only for files that exist in the project or URLs the user gave you; never guess web image URLs.

## Answers pasted back
`2CPC <id> vN` + `key=value` lines (or a `[2CPC]` header with project/plan paths). Use them directly — do not
re-read the plan unless needed (`python "{{CPC}}" path <id>`). A quoted value on a choice/multi/pick (`id="…"`)
is a custom answer typed by the user. `next=a>b>"…"` = what the user wants you to do now, **in that order** (quoted = their own step); run them one after
another without re-asking, except `next.pause=oui` → stop and report after each step. `next.note` = an instruction
for the whole sequence. `revise` (or similar) = produce the next plan version. No `next` line → integrate the answers and ask.
For a revision, write the full revised DSL to a file:
`python "{{CPC}}" new <file> --id <id>` → vN+1 (answers to unchanged ids/item keys carry over; keep them stable).

## Other
`open [id]` reopen · `list` · `path <id>` · `--no-open`

## Token rules
Concise DSL, no filler prose; prefer questions over long explanations; no "Other?" text question for a choice (an "Other…" field is built in); use item keys (`KEY=Label`) for long
lists so answers stay short; never cat the HTML.
