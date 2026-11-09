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
- Tutorials / setup steps → `!cmd <one command>` and `!code bash` (or `console` with `$ ` lines + output) blocks:
  each gets a Copy button; prompts and console output are never copied.
- Before/after screenshots → `!compare a.png | b.png`; an HTML mockup → `!html file.html | 480`; code → `!link Label | src/File.cs:42`.

## Answers pasted back
`2CPC <id> vN` + `key=value` lines (or a `[2CPC]` header with project/plan paths).
**First save them** (write the pasted text to a temp file): `python "{{CPC}}" answers [<id>] --save <file>` →
`.2cpc/<id>/vN/answers.txt` (feeds `!decisions`; `answers <id>` prints the last saved). Use them directly — do not
re-read the plan unless needed (`python "{{CPC}}" path <id>`). A quoted value on a choice/multi/pick (`id="…"`)
is a custom answer typed by the user. `next=a>b>"…"` = what the user wants you to do now, **in that order** (quoted = their own step); run them one after
another without re-asking, except `next.pause=oui` → stop and report after each step. `next.note` = an instruction
for the whole sequence. `revise` (or similar) = produce the next plan version. No `next` line → integrate the answers and ask.
For a revision (answers to unchanged ids/item keys carry over; keep them stable; the page flags changed sections):
- **Localized changes → patch** (cheaper): write ops to a file, `python "{{CPC}}" patch <id> <file>` → vN+1.
  `@replace ## Title` (whole section up to the next same-level heading; body without heading keeps the old one) ·
  `@after` / `@before <target>` · `@delete <target>` · `@append` (before `!next`) · `@meta key: value` · `@next <options>` (replaces the !next line).
  Target = `## Exact title` (or unique prefix) or `{#anchor}`. `--check` validates without writing.
- **Large rewrite** → full DSL: `python "{{CPC}}" new <file> --id <id>`.
- Previous decisions: put `!decisions` (table generated from the saved answers of vN-1) instead of retyping them.
- Give `{#anchor}` ids to headings you expect to patch (`# Phase 1 {#p1}`).

## Tracking
- Execution plans: give `!todo` items keys (`!todo t | build=Build APK ; test=Test`), then mark each one as you finish it:
  `python "{{CPC}}" todo <id> build` (shows checked "done by the agent", kept across versions).
- Plan finished / abandoned: `python "{{CPC}}" status <id> done|archived`.
- A pasted `… cpc.py … apply "status … ; …"` line comes from the dashboard (.2cpc/index.html): run it as is.
- Titles: concrete subject words ("Sons de la scène Village", "Paiement Stripe") → the plan icon is picked from them.
- A pasted header `2CPC <id> vN Δ` = only what changed since the last answer (`key=` = cleared): save it (merged), act on
  the merged set (`answers <id>` prints it).

## Other
`open [id]` reopen · `list [--all]` · `path <id>` · `answers [id]` · `apply` · `gc` · `rebuild [--all]` · `--no-open`

## Token rules
Concise DSL, no filler prose; prefer questions over long explanations; no "Other?" text question for a choice (an "Other…" field is built in); use item keys (`KEY=Label`) for long
lists so answers stay short; never cat the HTML.
