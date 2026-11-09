# 2CPC DSL (cheat-sheet)
Markdown + one-line directives. `!` = content, `?` = question. `|` separates fields, `;` separates items.
Literal `|` or `;` inside a field: write `\|` / `\;`. Inline markdown (**b** *i* `code` [l](url)) works in all labels, items, details, cells.

Header (top, optional): `title:` · `lang: fr|en` · `intro:` 1–2 sentences (used by "Answer + Context") · `comments: off` · `other: off` · `next: off`
· `status: draft|active|done|archived` (or brouillon/actif/fait/archivé) · `editor: vscode|cursor|windsurf|idea|rider|none|<url with {path} {line} {col}>` (default: `~/.2cpc/config.json` → vscode)

Text: `#`/`##`/`###` headings (optional stable anchor: `# Phase 1 {#p1}`, used by `patch` and by the "changed" badges) · paragraphs · `- `/`1. ` lists · `> quote` · `> note|tip|warn|danger: text` · `---`

Content:
```
!img path-or-url | caption          (paths relative to project root; copied once per plan in .2cpc/<id>/assets/)
!compare before.png | after.png | caption   before/after slider (same size images)
!html mockup.html | 480 | caption  self-contained HTML page in a sandboxed iframe (height px; inline its CSS/JS)
!audio path | caption
!video path-or-youtube/vimeo-url | caption
!chart bar|hbar|line|pie|donut | Title | A=12, B=8
!kpi Budget=45k€ ; Délai=6 sem
!progress Label | 40
!table | H1 | H2                    header on the directive line…
| a | b                             …then one row per line starting with |
!steps A ; B ; C
!gantt A=S1-S2 ; B=S2-S5 ; C=S6
!link Label | path-or-url         local file: `src/Foo.cs:42[:col]` opens in the editor (header `editor:`)
!code lang [| title] … !end        code + Copy button (title: e.g. a file name)
                                   bash/sh/zsh/powershell/cmd: prompt per line (not copied), # comments,
                                   `\` `` ` `` `^` continuations; console: `$ ` lines are commands, the rest is
                                   output (shown, never copied). Copied blocks get a ✓ (remembered: tutorials)
!cmd npm install                   one copyable command line (verbatim, `|` allowed)
!mermaid … !end
!cards … !end        lines: Title | desc | + pro ; - con
!cols … !col … !end  !tabs Name … !tab Name … !end  !details Title … !end
!draw caption … !end  sketch, see below
!decisions [vN] [| caption]         table Question | Decision built from the answers saved for vN (default: previous
                                    version) with `cpc.py answers <id> --save`; refreshed when answers are saved later
```

### `!draw` — quick sketch (rendered as SVG, no image needed)
Use it whenever the plan talks about **positions, layouts, zones, paths, trajectories, UI wireframes**: a 5-line
sketch beats a paragraph of coordinates. One shape per line (or `;`-separated), `x,y` with **y down**, any unit
(auto-fitted, only relative positions matter):
```
box x,y w,h [label]     circle x,y r [label]     dot x,y [label]      text x,y label
line x,y x,y … [label]  arrow x,y x,y … [label]  poly x,y x,y x,y … [label]   grid [step]
```
Flags before the label: `.blue .orange .green .yellow .pink .purple .red .gray` · `.dash` · `.thick` ·
`.empty` (no fill) · `.solid` · `.curve` (smooth through the points) · `.both` (2 arrowheads). `//` = comment.
`grid` adds a light grid with coordinates (handy to discuss "the prop at 3,2").
```
!draw Parcelle, vue de dessus (porte en bas)
grid
circle 0,0 5.6 .empty .dash
box -3,-2 6,3.5 .blue Forge
box -0.6,1.5 1.2,4 .red .dash Couloir
dot 0,4.6 .red PathEndSpot
arrow 3.5,-3 4.6,-1.4 3.6,0.8 .curve .orange zone props
!end
```

Questions — `?type id | label | …` ; `id!` = required ; keep ids stable across versions (answers carry over by id):
```
?choice id | Q | A* ; B ; C        (single; * = recommended — choice/multi only)
                                   choice/multi/pick always get an extra "Other…" free-text option (`other: off` to disable)
?multi id | Q | A ; B ; C
?rank id | Q | A ; B ; C
?approve id | Q | Item1 ; Item2    (✓/✗/? + note per item)
?text id | Q [| default]    ?line id | Q [| default]    ?date id | Q [| YYYY-MM-DD]
?number id | Q [| min-max [| default]]     ?scale id | Q | 1-5 [| default]
?yesno id | Q [| oui|non]          (default)
?matrix id | Q | Row1 ; Row2 | Col1 ; Col2
?pick id | Q                       (choose one card of the previous !cards)
!todo A ; B                        (tracked checklist; or !todo id | KEY=A ; KEY2=B — keys for `cpc.py todo`)
```
Items of choice/multi/rank/approve: `KEY=Label :: detail` — KEY (`[A-Za-z0-9_.-]`, optional) is the stable
answer key; `:: detail` (optional) is a secondary line. Use keys whenever labels are long or contain , ( ) >.
Each `#`/`##` section gets a comment box (answer key `#Section`).

### `!next` — "What next?" panel (bottom of page)
```
!next KEY=Label :: detail* ; KEY=Label ; …     (same item syntax as ?multi; * = pre-ticked)
```
The user ticks and **orders** the follow-up actions you should run after reading the answers, can add their own
steps, ask for a pause between steps and leave an instruction. One per plan, anywhere (rendered at the bottom).
Without `!next`, defaults are shown: `revise` (integrate answers → new version, pre-ticked) · `synth` · `tech` · `exec`.
Write 3–6 options **adapted to the plan's stage** (e.g. early: `revise`, `explore`, `proto`; settled: `tech`,
`exec`, `tests`, `pr`), pre-tick the one you recommend.

Answer pasted back: `2CPC <id> vN` then one `key=value` line per answer (unanswered omitted):
`choice`→key · `multi`→`k1,k2` · a **quoted** value is the user's own "Other" answer (`psp="Mollie"`, `f=a,"PDF export"`) · `rank`→`k1>k2` · `scale`→`4/5` · `matrix`→`Row:Col, …` · text→JSON string ·
`approve`→ one line per item: `id.KEY=✓` / `id.KEY=✗ "note"` / `id.KEY=?` / `id.KEY="note"`.
`!next` → `next=k1>k2>"user step"` (ticked, in order) · `next.pause=oui` · `next.note="…"`.
"Answer + Context" adds a header (title, intro, absolute paths) and short labels: `id(Label)=…`, `k(Label)`.

## Revisions: `patch` and `answers`
`cpc.py answers [<id>] --save <file|stdin>` stores pasted answers in `.2cpc/<id>/vN/answers.txt` (vN read from the
header). `cpc.py answers <id>` prints the last saved ones.
`cpc.py patch <id> <file> [--check]` applies operations to the last version and writes vN+1 (all or nothing):
```
@replace ## Phase 2            whole section, up to the next heading of the same or a higher level
?choice db | … (no heading in the body → the original heading is kept)
@after {#p1}                   insert after the section (@before: before it)
# Phase 1b
…
@delete ### Old detail
@append                        at the end, before !next
@meta intro: New intro
```
Target: `## Exact title` (else a unique prefix; level must match) or `{#anchor}` / `#slug`.
From v2 on, the page shows **changed** / **new** badges on sections, the removed ones, a "Changes only" filter, and,
under a question whose label or options changed, the answer given in the previous version.

## Agent-side commands
`cpc.py todo <id> KEY… [--undo]` marks `!todo` items done (shown checked/locked "done by the agent", kept across
versions by key; `todo <id>` lists them) · `cpc.py status <id> done` (no new version; `list` hides archived) ·
`cpc.py gc [<id>] [--keep 3] [--yes]` removes old pages + unused assets (dry run by default; plan.txt kept) ·
`list --all` / `rebuild --all`: every project registered in `~/.2cpc/registry.json` · `.2cpc/index.html`: dashboard
(sort / filter / status menu; status changes are copied as `cpc.py apply "status <id> <value> ; …"`).
Each plan gets a 64×64 pixel-art icon (`.2cpc/<id>/icon.png`), picked from the title + intro keywords (80 motifs,
cpc/motifs.py), colors from the id hash; generated once. Clear, specific titles give better icons.
"What's new" answers (`2CPC <id> vN Δ`) only hold changed lines (`key=` = cleared); `answers --save` merges them.

## Example
```
title: Refonte paiement
intro: Choisir le prestataire et valider le périmètre avant le sprint 12.
# Contexte
Le module date de **2019** et ne gère pas 3-D Secure 2.
> warn: Migration sans interruption de service.
!table | Option | Coût | Délai
| Stripe | 12 k€ | 3 sem
| Adyen | 18 k€ | 6 sem
# Décisions
?choice psp! | Prestataire | stripe=Stripe* :: intégration rapide ; adyen=Adyen :: multi-devises
?approve scope | Périmètre | PAY-01=Paiement CB (P1) ; PAY-02=Apple Pay (P2) :: si budget ; PAY-03=Remboursements (P1)
?rank order | Ordre de livraison | cb=CB ; refund=Remboursements ; wallet=Wallets
?number budget | Budget max (k€) | 5-50 | 20
?yesno go | Lancer le sprint 12 ? | oui
?text risks | Risques non identifiés ?
```
→ answer: `psp=stripe` · `scope.PAY-01=✓` · `scope.PAY-02=✗ "trop tôt"` · `order=cb>refund>wallet` · `budget=20` · `go=oui`
