# 2CPC — Plans interactifs générés par l'agent

> v2 du plan. Décisions prises : stockage dans chaque projet · aucun serveur, réponse renvoyée par copier-coller via un bouton · interface FR/EN · images web en simple lien · catalogue de blocs étendu.

## 1. Analyse du besoin

### Objectif
On demande un « plan 2CPC » à Claude depuis n'importe quel projet. L'agent produit alors une page web interactive, enregistrée dans le projet et ouverte dans le navigateur par défaut. L'utilisateur la lit et y répond, à son rythme, éventuellement plusieurs jours plus tard. Quand il a fini, il clique sur **« Générer la réponse »** et colle le texte obtenu dans Claude. L'agent exploite ces réponses et peut produire une nouvelle version du plan.

### Flux
```
Utilisateur ──"plan 2CPC …"──▶ Claude (projet X)
                                 │ DSL compact sur stdin (1 appel)
                                 ▼
                       cpc.py new ──▶ X/.2cpc/<id>/v1/index.html ──▶ navigateur (file://)
                                                      │ chaque interaction
                                                      ▼
                                               localStorage (sauvegarde auto)
Utilisateur ──clic « Générer la réponse »──▶ presse-papier ──collage──▶ Claude
                                 └──▶ cpc.py new --id <id> ──▶ v2 (réponses reprises)
```

### Exigences fonctionnelles
| # | Exigence | Solution |
|---|----------|----------|
| F1 | Créer la page à partir des données de l'agent | `cpc.py new`, un seul appel |
| F2 | L'ouvrir dans le navigateur par défaut | `webbrowser.open(file://…)` |
| F3 | Catalogue de blocs (titres, texte, images, graphiques, audio, questions, …) | §3 |
| F4 | Sauvegarder après chaque interaction | localStorage, sans délai |
| F5 | Signaler que le plan est terminé | bouton « Générer la réponse » : le texte copié sert de signal |
| F6 | Transmettre les réponses à l'agent | texte compact collé dans le chat |
| F7 | Versionner le plan | `new --id`, réponses reprises par identifiant de question |
| F8 | Utilisable depuis n'importe quel projet | skill Claude au niveau utilisateur |

### Exigences non fonctionnelles
- **Le moins de tokens possible**, en entrée comme en sortie (voir §6).
- **Aucune dépendance** : Python 3 et sa bibliothèque standard uniquement (3.14 est installé).
- **Aucun processus en arrière-plan** : un fichier HTML statique qui fonctionne en `file://` et hors ligne. Seules les images web et Mermaid ont besoin d'internet.
- **Page autonome** : CSS et JS intégrés, assets copiés à côté de la page.
- **Interface FR/EN**.

### Page ouverte par l'agent mais lue bien plus tard
- La page est un fichier statique dans le projet. Elle n'expire pas et ne dépend d'aucun serveur.
- Les réponses sont gardées dans le localStorage du navigateur, sous une clé `2cpc:<projet>:<id>:v<N>`. On peut fermer la page, redémarrer la machine et revenir des jours plus tard.
- Pour la retrouver : `cpc.py open [id]` rouvre le dernier plan ou celui indiqué, et `cpc.py list` les liste. Le dossier `.2cpc/` est aussi visible dans le projet.
- Pour une **nouvelle session Claude**, le bouton **« Réponse + Contexte »** ajoute un en-tête : titre, introduction du plan, chemin absolu sur le disque et consigne pour l'agent. La session peut ainsi reprendre sans historique (§5).
- **Limites connues** :
  - Le localStorage disparaît si l'on vide les données du navigateur.
  - Il est lié à un navigateur : les réponses ne suivent pas d'Edge vers Firefox.
  - Pour s'en protéger, un bouton « Exporter (.json) » permet de télécharger les réponses, et « Importer » de les recharger.

---

## 2. Architecture

### Outil (central, unique sur la machine)
```
C:\Users\blackbox\Desktop\2CPC\
├── cpc.py                 # CLI : new | open | list | path
├── cpc/
│   ├── parser.py          # DSL → blocs
│   ├── markdown.py        # Markdown minimal maison (titres, listes, gras/italique/code/liens)
│   ├── render.py          # blocs → HTML
│   ├── charts.py          # SVG : bar, hbar, line, pie, donut
│   ├── i18n.py            # textes de l'interface FR/EN
│   └── template/ page.html, style.css, app.js
├── docs/DSL.md            # aide-mémoire du format (≈50 lignes), lu par l'agent
├── skill/SKILL.md         # source du skill
├── install.py             # installe ~/.claude/skills/2cpc/ avec le chemin absolu de cpc.py
└── tests/
```

### Données (dans chaque projet)
```
<projet>/.2cpc/
├── index.json             # liste des plans : id, titre, version, date
└── <id>/                  # id = slug court du titre, ex. "refonte-paiement"
    ├── v1/ index.html  plan.txt (source DSL)  assets/
    └── v2/ …
```
- La racine du projet est le dossier courant de l'appel, ou la racine git si elle existe.
- Les chemins d'assets relatifs se résolvent depuis cette racine. Les fichiers sont copiés dans `vN/assets/`.
- `.2cpc/` peut être versionné ou ajouté au `.gitignore`. C'est au choix de l'utilisateur, l'outil n'y touche pas.

### Accès global (F8)
- `install.py` installe un `SKILL.md` **court** (≈25 lignes) dans `~/.claude/skills/2cpc/`. Il se déclenche sur « plan 2CPC », « /2cpc » ou « plan interactif ».
- Le skill contient : quand l'utiliser, les commandes, la façon de traiter une réponse collée, et un renvoi vers `docs/DSL.md`.

---

## 3. Format d'entrée : DSL compact

Le format est du Markdown, enrichi de directives sur une ligne. `!` introduit un bloc de contenu, `?` une question. Les mots-clés ne dépendent pas de la langue.

### En-tête
```text
title: Refonte du module paiement
lang: fr                       (fr|en ; langue de l'interface, auto si absent)
intro: Choisir l'architecture du nouveau module paiement avant le sprint 12.
                               (1–2 phrases ; reprises dans « Réponse + Contexte » ;
                                si absent, le premier paragraphe est utilisé)
```

### Contenu
```text
# Titre / ## Sous-titre / ### Sous-sous-titre
Texte libre = paragraphe (**gras**, *italique*, `code`, [lien](url)).
- puces / 1. numérotée
> citation
> note: texte                  (note|tip|warn|danger : encadré coloré)
---                            (séparateur)
!img assets/archi.png | Légende          (asset du projet, copié)
!img https://…/x.png | Légende           (image web, simple lien)
!audio assets/brief.mp3 | Légende
!video assets/demo.mp4 | Légende         (ou URL YouTube/Vimeo intégrée)
!chart bar|hbar|line|pie|donut | Titre | A=12, B=8, C=15
!kpi Budget=45k€ ; Délai=6 sem ; Risque=Moyen     (tuiles de chiffres clés)
!progress Avancement | 40                (barre de progression)
!table | Option | Coût | Délai          (lignes suivantes : | a | b | c)
!code python … !end
!mermaid … !end                          (diagramme ; CDN, affiche le code source hors ligne)
!steps Analyse ; Dev ; Recette ; Prod    (frise horizontale)
!gantt Analyse=S1-S2 ; Dev=S2-S5 ; Recette=S6      (planning simplifié)
!cards                                   (comparatif d'options en cartes)
Option A | Rapide, peu cher | + simple ; - limité
Option B | Robuste | + évolutif ; - coûteux
!end
!cols … !col … !end                      (deux colonnes côte à côte)
!tabs Onglet 1 … !tab Onglet 2 … !end
!details Titre repliable … !end
!link Spécification | docs/spec.pdf      (lien vers un fichier du projet ou une URL)
```

### Questions (l'identifiant court et stable sert de clé de réponse)
```text
?choice db | Base de données ? | PostgreSQL* ; MySQL ; SQLite    (un seul choix ; * = recommandé)
?multi feat | Fonctions ? | Export ; Webhooks ; SSO              (plusieurs choix)
?text risk | Risques non identifiés ?                            (zone de texte)
?line name | Nom du module ?                                     (champ d'une ligne)
?number budget | Budget max (k€) ?
?date start | Date de démarrage ?
?scale prio | Priorité | 1-5                                     (échelle)
?yesno go | Valider la phase 1 ?
?rank order | Ordonner | Design ; Dev ; Tests                    (glisser-déposer)
?approve steps | Valider chaque étape | Migration ; API ; UI     (✓ / ✗ / ? par élément + commentaire)
?matrix fit | Adéquation | Coût ; Délai | Faible ; Moyen ; Fort  (grille lignes × colonnes)
?pick opt | Option retenue ?             (sélection d'une carte du !cards précédent)
!todo Écrire les tests ; Migrer la BDD   (cases à cocher suivies)
```
- Suffixe `!` sur l'identifiant (`?text risk! | …`) : la question est obligatoire. Elle est signalée si la réponse générée la laisse vide.
- Chaque section `#`/`##` reçoit automatiquement une zone de commentaire repliable. `comments: off` dans l'en-tête la désactive.

---

## 4. Commandes CLI (sorties minimales)

| Commande | Effet | Sortie |
|---|---|---|
| `cpc.py new "Titre" <<'EOF' … EOF` | crée v1 dans le projet courant et l'ouvre | `OK refonte-paiement v1` |
| `cpc.py new --id <id> <<'EOF' … EOF` | crée v(N+1) ; la page reprend les réponses de vN aux identifiants inchangés | `OK refonte-paiement v2` |
| `cpc.py open [id] [--v N]` | rouvre le dernier plan, ou celui indiqué | `OK …` |
| `cpc.py list` | plans du projet | 1 ligne par plan |
| `cpc.py path <id>` | chemin de `plan.txt` (si l'agent doit relire le source) | 1 ligne |

Option `--no-open` : créer sans ouvrir le navigateur.

---

## 5. Page web

### Interface
- **En-tête** : titre, version, projet, sélecteur de langue FR/EN, indicateur « ✓ Sauvegardé », progression (répondues / total, obligatoires en évidence).
- **Sommaire latéral** généré depuis les titres. Une seule colonne sur mobile. Thème clair/sombre automatique. Feuille de style d'impression.
- **Sauvegarde** : chaque événement `input`/`change` écrit dans le localStorage.
- **Deux boutons de réponse** :
  - **« Générer la réponse »** produit le texte compact seul. C'est le cas courant : la session Claude qui a créé le plan est toujours ouverte.
  - **« Réponse + Contexte »** produit le même texte, précédé d'un en-tête de contexte. C'est pour un plan rouvert plus tard dans une nouvelle session.
  - Le déroulé est le même pour les deux :
    1. Si des questions obligatoires sont vides, ils les signalent et proposent « Générer quand même ».
    2. Ils copient le texte avec `navigator.clipboard`. Si ça échoue, le texte s'affiche dans une zone sélectionnée, prêt à copier.
    3. Ils affichent « Copié ! Collez-le dans Claude ».
- **Boutons secondaires** : Exporter / Importer (.json) · Réinitialiser · Versions précédentes.
- **Versions** : la page vN tente de lire les réponses de v(N−1) dans le localStorage et les pré-remplit en les surlignant (« reprise de v1 »). Les éléments ajoutés depuis la version précédente portent un badge *nouveau*.

### Format « Générer la réponse » (minimal)
```
2CPC refonte-paiement v1
db=PostgreSQL
feat=Export,SSO
prio=4/5
go=oui
steps=Migration✓ API✗ UI?
order=Dev>Design>Tests
risk="Pas de rollback prévu sur la migration"
#Options="Préférer B si le budget baisse"
todo=1/2
```
- Les questions sans réponse sont omises.
- Pas de libellés : la session qui a créé le plan connaît déjà les identifiants.
- `#Section="…"` correspond au commentaire d'une section.

### Format « Réponse + Contexte » (nouvelle session)
```
[2CPC] Réponses au plan interactif « Refonte du module paiement » (v1, 2026-11-04)
Intro : Choisir l'architecture du nouveau module paiement avant le sprint 12.
Projet : C:\…\mon-projet
Plan : C:\…\mon-projet\.2cpc\refonte-paiement\v1\plan.txt
Outil : python C:\Users\blackbox\Desktop\2CPC\cpc.py (skill 2cpc ; v2 : new --id refonte-paiement)
---
db(Base de données)=PostgreSQL
feat(Fonctions)=Export,SSO
prio(Priorité)=4/5
go=oui
…
```
- L'intro vient de la directive `intro:` (sinon du premier paragraphe).
- Les chemins sont **absolus**. `cpc.py new` les inscrit dans la page au moment de la création.
- Les libellés sont ajoutés, tronqués à environ 30 caractères. La session peut ainsi comprendre les réponses sans ouvrir `plan.txt`, et ne le relit que si elle a besoin de plus de détails.
- La ligne `[2CPC]` sert de déclencheur au skill.

---

## 6. Économie de tokens

1. **Entrée de l'agent** : le DSL est environ 3 à 5 fois plus court que du JSON. Les graphiques se réduisent à `A=12, B=8`, le SVG est calculé par le script.
2. **Un seul appel shell** : le contenu passe par heredoc sur stdin. Aucun fichier temporaire à écrire puis relire.
3. **Sortie du script** : une ligne, `OK <id> vN`. Jamais de HTML ni de log.
4. **Réponse collée** : `clé=valeur` sur une ligne par réponse, réponses vides omises. En mode minimal il n'y a pas de libellés. Le contexte et les libellés ne sont ajoutés qu'avec « Réponse + Contexte ». L'agent n'a pas besoin de relire le plan.
5. **Skill paresseux** : le SKILL.md fait environ 25 lignes et `DSL.md` n'est lu qu'au besoin. Toute la mise en forme est dans les gabarits.
6. **Versions** : l'agent réécrit seulement le DSL, et la reprise des réponses est faite par la page. Évolution possible : `cpc.py patch <id>` pour remplacer ou ajouter des sections sans tout réécrire.

---

## 7. Plan de réalisation

| Étape | Contenu | Livrable |
|---|---|---|
| 1 | Squelette, `cpc.py` (argparse), détection de la racine du projet, `.2cpc/index.json` | CLI qui répond |
| 2 | `markdown.py` et `parser.py` : DSL → blocs (+ tests) | AST validé |
| 3 | `render.py`, gabarit, CSS (thèmes, impression), blocs de contenu de base, copie des assets | page statique |
| 4 | `charts.py` (SVG), kpi, progress, table, code, steps, gantt, cards, cols, tabs, details, link, audio, video, mermaid | catalogue de contenu |
| 5 | Questions + `app.js` : sauvegarde localStorage, progression, obligatoires | page interactive |
| 6 | « Générer la réponse » et « Réponse + Contexte » (presse-papier et secours), export/import JSON | boucle de retour |
| 7 | Versionnement `new --id`, reprise des réponses de v(N−1), badges *nouveau*, liens entre versions | itérations |
| 8 | `i18n.py` FR/EN, sélecteur de langue | bilingue |
| 9 | `docs/DSL.md`, `skill/SKILL.md`, `install.py` | utilisable partout |
| 10 | Test de bout en bout depuis un autre projet (Edge et Firefox), réglage des sorties pour les tokens | validation |

**Critère de réussite** : depuis un projet quelconque, « plan 2CPC pour X » crée `X/.2cpc/…` et ouvre la page. Les réponses tiennent après fermeture et réouverture. « Générer la réponse » colle dans une nouvelle session un texte que Claude comprend sans autre contexte, et `new --id` produit une v2 avec les réponses reprises.
