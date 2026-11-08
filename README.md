# 2CPC — plans interactifs pour Claude Code

Claude génère un plan sous forme de page web interactive, enregistrée dans le projet (`.2cpc/`) et ouverte dans le navigateur. L'utilisateur y répond, et les réponses sont sauvegardées automatiquement dans le navigateur. Il clique ensuite sur **« Générer la réponse »** et colle le texte obtenu dans Claude, qui peut produire une v2.

Aucune dépendance (Python 3.8+), aucun serveur, fonctionne hors ligne.

## Installation
```
python install.py        # installe le skill dans ~/.claude/skills/2cpc/
```
Ensuite, dans n'importe quel projet : *« fais-moi un plan 2CPC pour … »*.

## Commandes
```
python cpc.py new plan.dsl [--id ID] [--check] [--no-open] [--root DIR]   # ou DSL sur stdin
python cpc.py new --check plan.dsl   # valide sans rien écrire (résumé + WARN)
python cpc.py open [ID] [--v N]      # rouvrir le dernier plan (ou ID)
python cpc.py list                   # plans du projet
python cpc.py path ID                # chemin du plan.txt
python cpc.py rebuild [ID]           # régénérer les pages après une mise à jour de l'outil
```
`new --id ID` crée la version suivante. Les réponses aux questions dont l'identifiant n'a pas changé sont reprises et surlignées.

## Format
Voir [docs/DSL.md](docs/DSL.md) : Markdown, plus des directives `!bloc` et des questions `?type id | libellé | options`.
- `!draw … !end` : croquis vectoriel en quelques lignes (`box`, `circle`, `arrow`, `dot`…), rendu en SVG dans la page, sans image externe.
- Les questions `?choice` / `?multi` / `?pick` ont toujours un champ « Autre… » ; la réponse libre revient entre guillemets (`id="…"`). En-tête `other: off` pour le retirer.

## Page
- **Générer la réponse** : texte compact (`2CPC id vN` puis une ligne `id=valeur` par réponse), pour la session Claude en cours.
- **Réponse + Contexte** : le même texte, précédé du titre, de l'intro, des chemins absolus du projet et du plan, et de la commande de l'outil. À utiliser dans une nouvelle session.
- Menu ⋯ : Exporter / Importer (.json), Réinitialiser, FR/EN.
- Les réponses sont stockées dans le localStorage, sous la clé `2cpc:<projet>:<id>:vN`. Elles sont propres au navigateur : utilisez Exporter pour les sauvegarder.

## Tests
```
python -m unittest discover tests
```
