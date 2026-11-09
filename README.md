# 2CPC — plans interactifs pour Claude Code

Claude génère un plan sous forme de page web interactive, enregistrée dans le projet (`.2cpc/`) et ouverte dans le navigateur. L'utilisateur y répond, et les réponses sont sauvegardées automatiquement dans le navigateur. Il clique ensuite sur **« Générer la réponse »** et colle le texte obtenu dans Claude. Claude enregistre la réponse, puis enchaîne les étapes demandées : nouvelle version du plan, implémentation, etc.

Aucune dépendance (Python 3.8+), aucun serveur, fonctionne hors ligne.

## Installation
```
python install.py        # installe le skill dans ~/.claude/skills/2cpc/
```
Ensuite, dans n'importe quel projet : *« fais-moi un plan 2CPC pour … »*.
Après une mise à jour de l'outil, relancez `install.py`. Si le skill installé n'est plus à jour, la création d'un plan affiche `WARN skill outdated`.

## Cycle de travail
1. **Plan** : Claude écrit le DSL et lance `cpc.py new`. La page s'ouvre.
2. **Réponses** : vous répondez dans la page, puis « Générer la réponse » ou « Nouveautés », et vous collez le texte dans Claude. Le panneau « Et ensuite ? » indique à Claude quoi faire, et dans quel ordre.
3. **Enregistrement** : Claude enregistre la réponse collée (`cpc.py answers --save`) dans `.2cpc/<id>/vN/answers.txt`.
4. **Révision** : `cpc.py patch` pour des changements localisés, `cpc.py new --id` pour une réécriture. Les réponses aux questions inchangées sont reprises, et `!decisions` génère le tableau des décisions précédentes.
5. **Exécution** : Claude coche les `!todo` au fur et à mesure (`cpc.py todo`), puis passe le plan en `fait` (`cpc.py status`).

## Commandes
Toutes les commandes acceptent `--root DIR`. Par défaut, c'est la racine git ou le dossier courant.

**Plans**
```
python cpc.py new plan.dsl [--id ID] [--check] [--no-open]   # créer (ou vN+1 avec --id) ; DSL aussi sur stdin
python cpc.py new --check plan.dsl         # valider sans rien écrire (résumé + WARN)
python cpc.py patch ID ops.txt [--check]   # modifier la dernière version → vN+1 sans tout réécrire
python cpc.py open [ID] [--v N]            # rouvrir le dernier plan (ou ID)
python cpc.py path ID [--v N]              # chemin du plan.txt
```

**Réponses et suivi**
```
python cpc.py answers [ID] --save F        # enregistrer une réponse collée (une réponse Δ est fusionnée)
python cpc.py answers ID [--v N]           # afficher la dernière réponse enregistrée
python cpc.py todo ID [KEY…] [--undo]      # cocher des !todo côté agent (sans clé : les lister)
python cpc.py status ID fait               # brouillon | actif | fait | archivé (ou draft | active | done | archived)
```

**Projets et maintenance**
```
python cpc.py list [--archived]            # plans du projet (les archivés sont masqués par défaut)
python cpc.py list --all                   # plans de tous les projets enregistrés
python cpc.py rebuild [ID] [--v N]         # régénérer les pages après une mise à jour de l'outil
python cpc.py rebuild --all                # idem, pour tous les projets enregistrés
python cpc.py gc [ID] [--keep 3] [--yes]   # vieilles pages + assets inutilisés : simulation, --yes pour supprimer
```
`gc` conserve toujours `plan.txt` et `answers.txt`. Une page supprimée reste reconstructible avec `rebuild ID --v N`.

### `patch`
Le fichier d'opérations est appliqué à la dernière version. Tout ou rien : en cas d'erreur, rien n'est écrit.
```
@replace ## Phase 2        remplace la section, jusqu'au titre suivant de même niveau ou supérieur
@after {#p1}               insère après la section (@before : avant)
@delete ### Ancien détail
@append                    ajoute à la fin, avant !next
@meta intro: Nouvelle intro
@next exec=Implémenter* ; revise=Réviser
```
Une cible est désignée par son titre exact (ou un préfixe unique), ou par une ancre posée sur le titre : `# Phase 1 {#p1}`.

## Format
Voir [docs/DSL.md](docs/DSL.md) : Markdown, plus des directives `!bloc` et des questions `?type id | libellé | options`.
- **En-tête** : `title:` `lang:` `intro:` `status:` `editor:` `comments: off` `other: off` `next: off`.
- **Contenu** : tableaux, graphiques, KPI, gantt, cartes, onglets, mermaid, images, audio, vidéo…
  - `!draw … !end` : croquis vectoriel en quelques lignes (`box`, `circle`, `arrow`, `dot`…), rendu en SVG.
  - `!compare avant.png | après.png | légende` : curseur avant/après.
  - `!html maquette.html | 480 | légende` : maquette HTML autonome dans un cadre isolé (iframe *sandbox*).
  - `!link Code | src/Foo.cs:42` : ouvre le fichier à la ligne indiquée dans l'éditeur (voir *Configuration*).
  - `!decisions [vN] [| légende]` : tableau Question | Décision, construit à partir des réponses enregistrées (par défaut, celles de la version précédente).
- **Questions** : choice, multi, rank, approve, text, line, number, date, scale, yesno, matrix, pick, todo.
  - `?choice` / `?multi` / `?pick` ont toujours un champ « Autre… » ; la réponse libre revient entre guillemets (`id="…"`).
  - `!todo id | build=Compiler ; test=Tester` : avec des clés, l'agent peut cocher les items (`cpc.py todo`).
- **`!next …`** : panneau « Et ensuite ? ». L'utilisateur coche et ordonne les actions que l'agent doit enchaîner, ajoute ses propres étapes, une pause entre les étapes et une consigne.

## Page
- **Générer la réponse** : texte compact (`2CPC id vN`, puis une ligne `id=valeur` par réponse), pour la session Claude en cours.
- **Réponse + Contexte** : le même texte, précédé du titre, de l'intro, des chemins du projet et du plan, et de la commande de l'outil. À utiliser dans une nouvelle session.
- **Nouveautés** : seulement ce qui a changé depuis le dernier envoi (`2CPC id vN Δ` ; `clé=` signifie que la réponse a été effacée).
- **Navigation** : recherche (Ctrl+Maj+F ; Échap pour effacer), filtre « Sans réponse seulement », sommaire avec le nombre de questions restantes par section (en rouge s'il manque une réponse obligatoire).
- **D'une version à l'autre** :
  - les réponses aux questions inchangées sont reprises et surlignées ;
  - les sections portent un badge **modifié** ou **nouveau**, et les sections supprimées sont listées ;
  - un filtre « Changements seulement » masque le reste ;
  - sous une question dont le libellé a changé, l'ancienne réponse est rappelée.
- **Suivi** : les todos cochés par l'agent sont marqués « fait par l'agent » ; le statut du plan s'affiche dans l'en-tête.
- **Menu ⋯** : Exporter / Importer (.json), Réinitialiser, FR/EN.
- **Stockage des réponses** : localStorage, sous la clé `2cpc:<projet>:<id>:vN`. Elles sont propres au navigateur : utilisez Exporter pour les sauvegarder.

## Fichiers
```
<projet>/.2cpc/
  index.html              tableau de bord : plans, statut, todos, réponses enregistrées, avancement
  index.json              index des plans (versions, dates, statut)
  <id>/assets/            images et maquettes, copiées une seule fois par plan (<hash>-<nom>)
  <id>/state.json         todos cochés par l'agent
  <id>/vN/plan.txt        source DSL de la version
  <id>/vN/index.html      page générée
  <id>/vN/answers.txt     réponse enregistrée (cpc.py answers --save)
~/.2cpc/registry.json     projets connus (list --all, rebuild --all)
~/.2cpc/config.json       réglages globaux, ex. {"editor": "cursor"}
```

## Configuration
- **Éditeur des liens `!link`** : en-tête `editor:` du plan, sinon `~/.2cpc/config.json`, sinon `vscode`. Valeurs possibles :
  - `vscode`, `cursor`, `windsurf`, `idea`, `rider`, `none` ;
  - un modèle d'URL contenant `{path}`, `{line}` et `{col}`.
  Un lien `file://` de secours est toujours ajouté. Le format des URL `idea` et `rider` dépend de l'installation JetBrains.
- **Variables d'environnement** :
  - `CPC_HOME` remplace `~/.2cpc` ;
  - `CPC_SKILL_FILE` désigne le skill installé à comparer.
  Les tests s'en servent pour ne jamais toucher aux vrais fichiers.

## Développement
```
cpc.py                    CLI
cpc/parser.py             DSL → blocs
cpc/render.py             blocs → page HTML (cpc/template/ : page.html, style.css, app.js, answers.js)
cpc/patch.py              sections, @opérations de patch, changements entre versions
cpc/answers.py            lecture des réponses collées, tableau !decisions, fusion Δ
cpc/dashboard.py          .2cpc/index.html
cpc/skill.py              rendu du skill (install.py et vérification « skill outdated »)
cpc/charts.py, draw.py    graphiques SVG et croquis !draw
```

## Tests
```
python -m unittest discover tests      # Python (+ test de bout en bout via Node s'il est installé)
node --test tests/answers.test.js      # génération du texte de réponse (cpc/template/answers.js)
```
La CI (`.github/workflows/test.yml`) lance les deux sous Python 3.8 et 3.12, sur Linux et Windows, puis valide le plan de démo sans aucun `WARN`.
