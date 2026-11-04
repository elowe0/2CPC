# 2CPC DSL (cheat-sheet)
Markdown + one-line directives. `!` = content, `?` = question. `|` separates fields, `;` separates items.
Literal `|` or `;` inside a field: write `\|` / `\;`. Inline markdown (**b** *i* `code` [l](url)) works in all labels, items, details, cells.

Header (top, optional): `title:` · `lang: fr|en` · `intro:` 1–2 sentences (used by "Answer + Context") · `comments: off`

Text: `#`/`##`/`###` headings · paragraphs · `- `/`1. ` lists · `> quote` · `> note|tip|warn|danger: text` · `---`

Content:
```
!img path-or-url | caption          (paths relative to project root; copied)
!audio path | caption
!video path-or-youtube/vimeo-url | caption
!chart bar|hbar|line|pie|donut | Title | A=12, B=8
!kpi Budget=45k€ ; Délai=6 sem
!progress Label | 40
!table | H1 | H2                    header on the directive line…
| a | b                             …then one row per line starting with |
!steps A ; B ; C
!gantt A=S1-S2 ; B=S2-S5 ; C=S6
!link Label | path-or-url
!code lang … !end    !mermaid … !end
!cards … !end        lines: Title | desc | + pro ; - con
!cols … !col … !end  !tabs Name … !tab Name … !end  !details Title … !end
```

Questions — `?type id | label | …` ; `id!` = required ; keep ids stable across versions (answers carry over by id):
```
?choice id | Q | A* ; B ; C        (single; * = recommended — choice/multi only)
?multi id | Q | A ; B ; C
?rank id | Q | A ; B ; C
?approve id | Q | Item1 ; Item2    (✓/✗/? + note per item)
?text id | Q [| default]    ?line id | Q [| default]    ?date id | Q [| YYYY-MM-DD]
?number id | Q [| min-max [| default]]     ?scale id | Q | 1-5 [| default]
?yesno id | Q [| oui|non]          (default)
?matrix id | Q | Row1 ; Row2 | Col1 ; Col2
?pick id | Q                       (choose one card of the previous !cards)
!todo A ; B                        (tracked checklist; or !todo id | A ; B)
```
Items of choice/multi/rank/approve: `KEY=Label :: detail` — KEY (`[A-Za-z0-9_.-]`, optional) is the stable
answer key; `:: detail` (optional) is a secondary line. Use keys whenever labels are long or contain , ( ) >.
Each `#`/`##` section gets a comment box (answer key `#Section`).

Answer pasted back: `2CPC <id> vN` then one `key=value` line per answer (unanswered omitted):
`choice`→key · `multi`→`k1,k2` · `rank`→`k1>k2` · `scale`→`4/5` · `matrix`→`Row:Col, …` · text→JSON string ·
`approve`→ one line per item: `id.KEY=✓` / `id.KEY=✗ "note"` / `id.KEY=?` / `id.KEY="note"`.
"Answer + Context" adds a header (title, intro, absolute paths) and short labels: `id(Label)=…`, `k(Label)`.

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
