# pi-sessions — Spécifications

Gestionnaire de sessions en TUI pour [pi](https://github.com/earendil-works/pi)
(`@earendil-works/pi-coding-agent`), dérivé de
[ccsessions](https://github.com/miskiewiczm/ccsessions) v0.4.0 (MIT, Marek Miśkiewicz),
qui fait la même chose pour Claude Code.

Ce document décrit **le comportement complet de ccsessions** et, pour chaque point,
**son équivalent pi**. Une section marquée **[CC]** décrit ccsessions tel quel ; **[PI]**
décrit ce que pi-sessions doit faire. Quand rien n'est précisé, le comportement est
identique.

Sources : code de `../ccsessions` (commit `b56e6d8`), doc embarquée de pi 1.5.0
(`docs/session-format.md`, `sessions.md`, `message-types.md`,
`environment-variables.md`), `dist/core/session-manager.js`, et un scan réel de
441 sessions dans le volume `pi-agent-home` (voir §15).

---

## 1. Objectif et périmètre

Une application terminal, lancée par une commande unique, qui :

1. liste tous les projets et toutes les sessions pi de la machine, les plus récents d'abord ;
2. affiche pour la session sélectionnée ses métadonnées, ses tokens/coût et la fin de la conversation, sans lancer pi ;
3. reprend une session en une touche (remplace le processus par `pi`) ou copie la commande de reprise ;
4. archive / restaure / supprime une session ou un projet entier ;
5. exporte une session en Markdown (front matter YAML, prêt pour Quarto/Pandoc) ou en JSONL brut ;
6. tient à jour un document Markdown « live » d'une session en cours ;
7. permet de donner un alias d'affichage à un projet ;
8. filtre projets et sessions, change de thème, se rafraîchit seul.

Hors périmètre : modifier le contenu d'une session, naviguer dans l'arbre de branches
(`/tree` de pi le fait), tout accès réseau.

## 2. Glossaire

| Terme | Claude Code | pi |
|---|---|---|
| Racine de données | `~/.claude` | `~/.pi/agent` (`PI_CODING_AGENT_DIR`) |
| Dossier des sessions | `~/.claude/projects/` | `~/.pi/agent/sessions/` (`PI_CODING_AGENT_SESSION_DIR`, setting `sessionDir`) |
| Projet | sous-dossier `<chemin-encodé>` | sous-dossier `--<chemin-encodé>--` |
| Session | `<uuid>.jsonl` | `<timestamp>_<id>.jsonl` |
| Index de métadonnées | `sessions-index.json` | **aucun** |
| Registre des sessions vivantes | `~/.claude/sessions/*.json` (pid) | **aucun** |
| Nom donné par l'utilisateur | enregistrement `custom-title` (`/rename`) | entrée `session_info.name` (`/name`, `--name`) |
| Reprise | `claude --resume <id>` | `pi --session <id|chemin>` |

## 3. Format des données pi (lecture seule)

### 3.1 Emplacement

```
<sessionsRoot>/--<cwd-encodé>--/<timestamp>_<sessionId>.jsonl
```

- `sessionsRoot` = `$PI_CODING_AGENT_SESSION_DIR`, sinon `$PI_CODING_AGENT_DIR/sessions`, sinon `~/.pi/agent/sessions`. pi-sessions accepte en plus sa propre variable `PI_SESSIONS_ROOT` (prioritaire), utile pour le cas Docker (§15).
- Encodage du cwd (`session-manager.js:294`) : on retire le séparateur initial, puis `/`, `\` et `:` deviennent `-`, puis on entoure de `--`. **C'est avec perte** (`a-b` et `a/b` donnent la même chose) : le vrai chemin se lit dans l'en-tête de session.
- `<timestamp>` = ISO de création avec `:` et `.` remplacés par `-` (ex. `2026-10-14T14-40-04-385Z`). `<sessionId>` = UUID (ou ID fourni via `--session-id`).
- pi ne lit que les `*.jsonl` **à plat** dans un dossier projet (`readdirSync(dir).filter(.jsonl)`, non récursif) : un sous-dossier `archived/` est invisible pour `/resume`. Vérifié dans `session-manager.js:450,600`.

### 3.2 Lignes (un objet JSON par ligne)

Première ligne, l'en-tête :

```json
{"type":"session","version":3,"id":"<uuid>","timestamp":"<ISO>","cwd":"/chemin","parentSession":"/chemin/parent.jsonl"}
```

`parentSession` n'existe que pour une session issue de `/fork` ou `/clone`.

Entrées suivantes : base commune `{type, id, parentId, timestamp(ISO)}`. Elles forment un **arbre**
(`parentId`), pas une liste : plusieurs branches peuvent coexister dans un fichier.

| `type` | Utile pour pi-sessions | Champs lus |
|---|---|---|
| `message` | conversation, tokens, coût, compteur | `message.role`, `message.content`, `message.usage`, `message.model`, `message.provider` |
| `session_info` | titre de session | `name` (la dernière gagne) |
| `model_change` | modèle courant | `provider`, `modelId` |
| `thinking_level_change` | — (détail optionnel) | `thinkingLevel` |
| `compaction` | marqueur dans la conversation, tokens | `summary`, `tokensBefore`, `usage` |
| `branch_summary` | marqueur, tokens | `summary`, `usage` |
| `usage` | tokens | `usage` |
| `custom_message` | affiché si `display: true` | `customType`, `content` |
| `custom`, `label`, `context_edit` | ignorés | — |

Rôles de `message.role` observés : `system`, `user`, `assistant`, `toolResult`, `bashExecution` ;
documentés en plus : `custom`, `branchSummary`, `compactionSummary`. **Tout rôle ou type inconnu est ignoré sans erreur.**

Blocs de contenu : `text`, `thinking`, `toolCall {name, arguments}`, `image`.
`user.content` peut être une chaîne **ou** un tableau de blocs.

`usage` : `{input, output, cacheRead, cacheWrite, totalTokens, cost:{input, output, cacheRead, cacheWrite, total}}`.
Le coût en dollars est fourni par pi : c'est un **ajout** par rapport à ccsessions.

Horodatage : `timestamp` de l'entrée en ISO 8601 ; `message.timestamp` en millisecondes Unix. On utilise celui de l'entrée.

Version : pi migre les anciens fichiers (v1/v2) vers v3 **en les réécrivant** au chargement. pi-sessions doit lire la v3 et tolérer v1/v2 (absence de `id`/`parentId` → ordre du fichier).

## 4. Modèle de données

```text
Entry        role, text, ts (datetime aware UTC | None)
             role ∈ user | assistant | tool | command | command-output | marker

TokenStats   input, output, cache_read, cache_write, cost (float, $), messages,
             name (dernier session_info.name), first_prompt, cwd, created,
             model (dernier provider/modelId vu), parent_session
             total = input + output + cache_read + cache_write

Session      session_id, file_path, project_path (cwd), first_prompt, summary,
             message_count, created, modified, model, parent_session,
             is_live, is_archived, tokens
             display_title = summary or first_prompt or session_id

Project      project_path, encoded_dir, sessions[], is_archived, alias
             default_name = basename(project_path)
             display_name = alias or default_name
             total_tokens = somme des sessions ; has_live = une session live
```

Différences avec [CC] :
- **supprimés** : `git_branch` (pi ne le stocke pas), `is_sidechain`, `is_missing` (il n'y a pas d'index, donc pas de session « sans fichier »), la notion de worktree dans le nom de projet (pi crée un dossier par cwd exact, donc deux projets ne partagent jamais un chemin) ;
- **ajoutés** : `cost`, `model`, `parent_session` (affiché « ⑂ fork de … »).

## 5. Découverte (scan)

[CC] `discover_projects()` : pour chaque sous-dossier de `~/.claude/projects`, fusionne les `*.jsonl`, ceux de `archived/` et les entrées de `sessions-index.json` sans fichier ; trie les sessions par `modified` décroissant ; écarte les projets vides ; trie les projets par session la plus récente ; puis ajoute les projets archivés de `~/.claude/projects-archive/` (marqués archivés, jamais live), toujours après les actifs.

[PI] Même algorithme, sans l'index :

1. Lire les sessions vivantes une fois (§8).
2. Pour chaque sous-dossier de `sessionsRoot` (trié par nom) :
   - chaque `*.jsonl` → session active ; chaque `archived/*.jsonl` → session archivée (si l'ID n'a pas déjà été vu) ;
   - les métadonnées viennent du parse complet du fichier (§6), mis en cache (§7) ;
   - `project_path` = `cwd` de l'en-tête de la session la plus récente ; à défaut, décodage avec perte du nom de dossier (`--a-b--` → `/a/b`) ;
   - projet vide → écarté.
3. Trier les projets par `max(session.modified)` décroissant.
4. Projets archivés : même traitement sur `sessions-archive/` (à côté de `sessionsRoot`), marqués archivés, `is_live=False`, ajoutés après les actifs. Si `sessionsRoot` est personnalisé (tests), l'archive n'est lue que si elle est passée explicitement.
5. `session_id` = `id` de l'en-tête ; à défaut, la partie du nom de fichier après le premier `_`.
6. `created` = `timestamp` de l'en-tête ; `modified` = mtime du fichier.
7. Tout fichier illisible, JSON invalide ou en-tête absent : la session est quand même listée avec ce qu'on sait (nom de fichier, mtime), jamais d'exception.

Le scan tourne **hors du thread UI** (worker exclusif, groupe `scan`) et mesure sa durée, affichée dans la barre d'état.

## 6. Parsing

### 6.1 Statistiques d'une session (lecture complète, ligne par ligne)

[CC] Somme de `usage.input_tokens / output_tokens / cache_read_input_tokens / cache_creation_input_tokens`, compte des messages user/assistant non `isMeta`, dernier `custom-title`.

[PI] Un seul passage en streaming sur le fichier :
- en-tête → `cwd`, `created`, `parent_session` ;
- `message` avec rôle `user` ou `assistant` → `messages += 1` ;
- premier `user` dont le texte n'est pas vide → `first_prompt` ;
- tout `usage` trouvé sur un message `assistant`, une entrée `usage`, `compaction.usage` ou `branch_summary.usage` → ajouté aux tokens et à `cost` (`usage.cost.total`) ;
- `session_info` → `name` (le dernier gagne, après `strip`) ;
- `model_change` ou `assistant.provider/model` → `model` (le dernier gagne).

On compte **toutes les branches** du fichier, comme les totaux de pi. Les valeurs non numériques comptent pour 0.

### 6.2 Transformation d'une ligne en entrées de conversation

[CC] `entries_from_line()` : `user` → texte (ou `command` / `command-output` reconnus par les balises `<command-name>`, `<local-command-stdout>`) ; `assistant` → un `assistant` par bloc texte, un `tool` par `tool_use` résumé en `nom: argument` (premier argument parmi `command, description, file_path, pattern, prompt, query, url, skill`, première ligne, 80 caractères max).

[PI] :

| Source | Entrée produite |
|---|---|
| `message` `user` (chaîne ou blocs `text` joints par `\n`) | `user` (vide → rien) |
| `message` `assistant`, bloc `text` | `assistant` |
| `message` `assistant`, bloc `toolCall` | `tool` : `nom: argument`, argument pris dans `command, path, file_path, pattern, query, url, prompt, description, skill`, première ligne, tronqué à 80 (77 + `...`) |
| `message` `assistant`, bloc `thinking` | rien (option future) |
| `message` `bashExecution` (commande `!` de l'utilisateur) | `command` : `! <command>` puis `command-output` : `output` si non vide |
| `custom_message` avec `display: true` | `command-output` préfixé de `[customType]` |
| `compaction` | `marker` : `⧉ compaction (N tokens résumés)` |
| `branch_summary` | `marker` : `⑂ changement de branche` |
| `message` `system`, `toolResult`, `custom` ; `custom`, `label`, `context_edit`, `model_change`, `thinking_level_change`, `usage` | rien |

pi n'enregistre pas les commandes slash : elles n'apparaissent pas, contrairement à [CC].

### 6.3 Branches

Le fichier contient tout l'arbre. Pour l'aperçu et l'export, pi-sessions montre la **branche active** : on part de la dernière entrée ayant un `id` et on remonte les `parentId`. Dans l'aperçu (lecture de la fin du fichier seulement), on remonte tant que le parent est dans la portion lue. Si aucune entrée n'a d'`id` (v1), on suit l'ordre du fichier. Le panneau Détails affiche le nombre de feuilles s'il y en a plus d'une (`⑂ 3 branches`).

### 6.4 Lecture de la fin (aperçu)

[CC] `read_conversation_tail(path, max_entries=40, max_bytes=512_000)` : lit les 512 Ko de fin en binaire, décode en UTF-8 avec remplacement, jette la première ligne si on a commencé au milieu du fichier, garde les 40 dernières entrées. Identique pour [PI].

### 6.5 Lecture complète (export)

Streaming ligne par ligne, jamais le fichier entier en mémoire. Pour la branche active, une première passe garde seulement `id → parentId` et le numéro de ligne ; une seconde émet les entrées de la branche.

## 7. Cache

[CC] `~/.cache/ccsessions/token-stats.json` : `{chemin: {mtime_ns, size, input, output, cache_read, cache_write, messages, custom_title}}`. Valide tant que `(st_mtime_ns, st_size)` n'a pas changé ; une clé manquante force la relecture (migration gratuite) ; écriture atomique (fichier `.tmp` puis `rename`) seulement si modifié ; erreurs d'E/S ignorées.

[PI] Même mécanisme, dans `~/.cache/pi-sessions/stats.json`, avec **tous** les champs de `TokenStats` (§4). Comme pi n'a pas d'index, ce cache **sert d'index** : sans lui, chaque scan relirait des centaines de Mo. À la fin du scan, on supprime les entrées dont le fichier n'existe plus (`prune`).

## 8. Détection des sessions en cours (« live »)

[CC] Lit `~/.claude/sessions/*.json` (`{pid, sessionId}`), session live si `kill(pid, 0)` réussit (`PermissionError` = vivant).

[PI] **pi n'a ni registre ni fichier de verrou** (il écrit avec `appendFileSync` sans garder le fichier ouvert). Trois niveaux, du plus simple au plus fiable :

1. **V1, heuristique (par défaut)** : une session est live si son mtime date de moins de `PI_SESSIONS_LIVE_SECONDS` secondes (défaut 120). Le libellé dit « active récemment », pas « en cours ».
2. **V1, en plus si possible** : un processus `pi` dont le répertoire courant égale le `cwd` de la session (via `ps`/`lsof -a -d cwd`) rend live la session la plus récente de ce cwd. Inutilisable si pi tourne dans Docker (§15).
3. **V2, extension pi** : une petite extension `pi-sessions-live` écrit au démarrage de session `<agentDir>/pi-sessions/live/<sessionId>.json` = `{sessionId, file, cwd, pid, heartbeat}`, met `heartbeat` à jour toutes les 30 s et supprime le fichier à la fermeture. Live = fichier présent et `heartbeat` de moins de 90 s. On n'utilise pas le pid, il ne veut rien dire d'un conteneur à l'autre.

Les garde-fous (pas d'archivage ni de suppression d'une session live) utilisent cette valeur.

## 9. Gestion des sessions et projets

Toutes les opérations lèvent une `ManageError` avec un message lisible, affiché dans la barre d'état avec un bip.

| Opération | [CC] | [PI] |
|---|---|---|
| Archiver une session | déplace le `.jsonl` vers `<projet>/archived/` | identique (invisible pour `pi --resume`, vérifié §3.1) |
| Restaurer une session | `archived/x.jsonl` → `<projet>/x.jsonl` ; erreur si pas dans `archived/` | identique |
| Supprimer une session | supprime le `.jsonl` et son entrée d'index | supprime le `.jsonl` (pas d'index). Option `PI_SESSIONS_TRASH=1` : passer par la commande `trash` si elle existe, comme le fait pi |
| Archiver un projet | déplace le dossier vers `~/.claude/projects-archive/<nom>` ; erreur si la cible existe | vers `sessions-archive/<nom>`, à côté de `sessionsRoot` (soit `~/.pi/agent/sessions-archive` par défaut) |
| Restaurer un projet | retour dans `projects/` ; erreur si la cible existe | retour dans `sessionsRoot` |
| Supprimer un projet | `rmtree` du dossier | identique |

Règles de l'interface :
- refuser d'archiver ou supprimer une session live, ou un projet qui en contient une ;
- suppression toujours précédée d'une boîte de confirmation (§12.5) qui rappelle le nombre de sessions et de tokens, et prévient que si le dossier est synchronisé entre machines, la suppression se propage ;
- après toute opération réussie : rescan.

## 10. Reprise

[CC] `r` quitte la TUI en renvoyant `ResumeRequest(session_id, cwd)` ; `main()` fait `chdir(cwd)` si le dossier existe, puis `execvp("claude", ["claude","--resume",id])`. `c` copie `cd <cwd> && claude --resume <id>` (arguments passés par `shlex.quote`, `cd` omis si le dossier n'existe pas) dans le presse-papiers via OSC 52.

[PI] :
- commande : `pi --session <chemin-absolu-du-fichier>`. On passe le chemin plutôt que l'ID pour éviter toute ambiguïté (pi accepte un ID partiel et peut proposer un fork si le cwd diffère) ;
- binaire : `$PI_SESSIONS_PI_BIN`, sinon `pi` cherché dans le PATH ; erreur « `pi` introuvable dans le PATH » sinon ;
- toujours `chdir(cwd)` avant l'`exec` si le dossier existe : pi utilise de toute façon le cwd de la session, mais un lanceur comme pi-sandbox monte le dossier courant (§15) ;
- commande copiée : `cd '<cwd>' && pi --session '<fichier>'` ;
- impossible sur une session archivée (« restaurez-la d'abord (a) ») ou dans un projet archivé (« restaurez le projet (a dans le panneau Projets) ») ;
- si le cwd n'existe plus, le panneau Détails l'indique (« ⚠ le dossier du projet n'existe plus — pas de cd »).

## 11. Export

### 11.1 Destination

[CC] `resolve_destination(saisie, session, format)` :
- saisie vide → `.` ; `~` est développé ;
- si c'est un dossier, si ça finit par `/` ou s'il n'y a pas d'extension → on génère le nom `<AAAA-MM-JJ>-<slug>.<md|jsonl>` dans ce dossier (date = modified, sinon created, sinon maintenant ; slug = titre ou premier prompt en minuscules, sans ponctuation, espaces → `-`, 40 caractères max, sinon les 8 premiers caractères de l'ID) ;
- le dossier parent doit exister, sinon erreur ;
- **jamais d'écrasement** : on ajoute `-1`, `-2`, … avant l'extension.

Identique pour [PI].

### 11.2 Formats

- **Raw** : copie octet pour octet du `.jsonl` (`copy2`).
- **Markdown** : front matter puis conversation, écrits en streaming.

Front matter [CC] : `title, session_id, project, git_branch?, created?, modified?, messages, tokens{input, output, cache_read, cache_write, total}, exported_by: ccsessions`, plus des champs libres (doc live). Les chaînes passent par `json.dumps` (échappement YAML sûr).

[PI] : même chose, sans `git_branch`, avec en plus `model`, `cost` (USD, 4 décimales), `parent_session?`, et `exported_by: pi-sessions`.

Corps (`markdown_chunks`), identique en [PI] sauf le nom de l'interlocuteur :
- une section `## AAAA-MM-JJ` par jour (heure locale), ou `## Conversation` si aucune entrée n'a d'horodatage ;
- `### You · HH:MM` / `### Pi · HH:MM` (au lieu de `Claude`) ;
- appels d'outils et commandes groupés en liste serrée : `- ⚙ \`…\`` / `- ⌘ \`…\`` (les backticks du texte sont retirés) ;
- `command-output` dans un bloc ```` ```txt ```` ;
- `marker` [PI] en ligne en italique : `_⧉ compaction…_`.

`normalize_markdown(texte)`, appliqué au texte des messages :
- abaisse les titres pour que le plus haut soit `####` (on ignore ce qui est dans les blocs de code) ;
- un bloc de code sans langage reçoit `txt` ;
- ajoute une ligne vide avant une liste collée à un paragraphe, et avant une ligne qui n'est qu'un trait (`─—-`, 5 ou plus) ;
- ajoute de l'air après une ligne `★ Insight` (spécifique au style de sortie de Claude ; à garder, c'est sans effet ailleurs).

Erreurs : session sans fichier, dossier absent, erreur d'E/S → `ExportError`, affichée. En cas de succès, la barre d'état affiche `Exported (<format>, <N> kB): <chemin>`.

Option [PI] (non prioritaire) : troisième bouton « HTML » qui appelle `pi --export <fichier> <sortie>`.

## 12. Interface (Textual)

### 12.1 Mise en page

Quatre panneaux avec bordure arrondie et titre dans la bordure : **Projets**, **Sessions**, **Détails**, **Conversation**. En dessous : barre de filtre (cachée par défaut), barre d'état (1 ligne), pied de page avec les raccourcis. En-tête : `Pi Sessions`.

- **Large** (largeur ≥ 140 colonnes) : colonne gauche de 50 % avec Projets (40 % de la hauteur), Sessions (40 %) et Détails (le reste) empilés ; Conversation occupe toute la moitié droite.
- **Étroit** : moitié haute avec Projets à gauche (40 % de la largeur) et, à droite, Sessions (50 %) au-dessus de Détails ; Conversation occupe toute la largeur de la moitié basse.
- Le panneau qui a le focus a une bordure et un titre couleur accent, en gras.
- Curseur de ligne : fond neutre `$panel` quand la table n'a pas le focus ; `ansi_bright_black`, texte en gras, quand elle l'a (contraste mesuré à 5.46, contre 1.51 avec la couleur accent).
- En-têtes de colonnes : couleur `$secondary`, gras et souligné.

### 12.2 Table Projets

Colonnes : `" "` (état), `Project`, `Sessions`, `Tokens`. Lignes alternées (zebra).

- État : `▪` couleur erreur = projet archivé ; `●` couleur succès = contient une session live ; vide sinon.
- Nom : gras couleur primaire ; gris italique si toutes ses sessions sont archivées.
- Sessions : `N` actives, ou `N+M` avec M archivées ; couleur warning, alignées à droite.
- Tokens : total formaté (`1.2M`, `3.4k`, `999`), couleur secondaire (grise si tout est archivé). [PI] : ajouter une colonne `Cost` (`$1.23`) si la largeur le permet.

### 12.3 Table Sessions

Colonnes [CC] : `" "` (état), `"  "` (œil du doc live), `Title`, `Msgs`, `Tokens`, `Modified`.

- État : `▪` archivée (erreur), `●` live (succès), sinon vide ; [CC] `✕` sans fichier, supprimé en [PI] ; [PI] ajoute `⑂` (gris) pour une session issue d'un fork, si elle n'est ni archivée ni live.
- Titre : sur une ligne, tronqué à 80 (77 + `...`) ; gris si archivée ; gras si live.
- Msgs : warning ; Tokens : secondaire ; Modified : `AAAA-MM-JJ HH:MM` en gris. [PI] : colonne `Cost` optionnelle, comme en §12.2.
- Œil : `◉` vert = doc live suivi et session live ; `◉` jaune = suivi, session arrêtée ; `◌` couleur primaire (bleu) = le fichier existe mais personne ne le met à jour ; vide sinon. Glyphes modifiables (§13).

### 12.4 Panneau Détails (texte enrichi, couleurs du thème)

Dans l'ordre :
1. titre (si la session a un nom ou un résumé), en gras couleur primaire ;
2. état : `▪ archived (a = restore)` / `● live` / `○ inactive` ; [PI] puis `model` en secondaire, `⑂ fork de <nom de fichier parent>` et `⑂ N branches` le cas échéant ;
3. `ID`, `CWD` (avec `~`, suivi de `(does not exist)` si absent), `Created`, `Modified`, `Messages` ;
4. bloc **Tokens** : input, output, cache read, cache write, `Σ total`, en colonnes de 12 alignées à droite avec séparateur des milliers ; [PI] puis `$ cost` ;
5. **Resume command** `(c = copy to clipboard)` puis la commande (seulement si la session n'est pas archivée) ;
6. **Live document** `(l = toggle)`, son état et son chemin, si un document existe. ⚠ ccsessions affiche encore `w = toggle` alors que la touche est devenue `l` : bug à ne pas reproduire ;
7. **First prompt** : texte brut, 600 caractères max.

Les textes venant des données (titres, chemins) sont toujours échappés : la barre d'état et la boîte de confirmation sont en `markup=False`, pour qu'un `[` dans un nom ne soit pas interprété.

### 12.5 Panneau Conversation

- Les 40 dernières entrées (§6.4) de la branche active ; défilement automatique en bas après chaque rendu.
- Séparateur de jour `── AAAA-MM-JJ ──` (couleur accent) à chaque changement de date locale.
- Horodatage : `HH:MM` pour aujourd'hui, `AAAA-MM-JJ HH:MM` sinon.
- `▌ You  HH:MM` (primaire) suivi du texte brut (pas de Markdown, pour ne pas perdre de balises), indenté de 2.
- `▌ Pi  HH:MM` (succès) suivi du texte rendu en Markdown, avec le thème de code associé (§12.8), indenté de 2. [PI] : on peut afficher le modèle à la place de `Pi`.
- `  ⚙ outil: arg` en gris ; `  ⌘ commande` en gris gras ; sortie de commande en gris, indentée de 4, 400 caractères max ; [PI] `marker` en italique couleur accent.
- Texte d'un message tronqué à 1500 caractères.
- États vides : `No session selected`, `(empty conversation)`.
- **Ne pas re-rendre** si `(session_id, modified)` n'a pas changé (sinon l'auto-refresh ferait défiler le panneau sous les doigts de l'utilisateur), sauf rendu forcé (changement de thème ou de doc live).

### 12.6 Raccourcis

| Touche | Action |
|---|---|
| `j` / `k` / flèches | descendre / monter dans le panneau qui a le focus (curseur de table, ou défilement) |
| `Tab` / `Shift+Tab` | panneau suivant / précédent |
| `r` | reprendre la session (§10) |
| `c` | copier la commande de reprise |
| `a` | archiver ↔ restaurer : la session si le focus est sur Sessions, le projet si le focus est sur Projets. Deux bindings sur la même touche ; `check_action` active l'un ou l'autre selon l'état de la sélection, et le libellé du pied de page suit |
| `d` | supprimer la session ou le projet (avec confirmation) |
| `n` | renommer le projet (alias) |
| `e` | exporter |
| `l` | activer / désactiver le doc live |
| `/` | filtrer la liste qui a le focus (projets si focus Projets, sessions sinon) |
| `Ctrl+R` | rescanner maintenant (caché du pied de page) |
| `p` | palette de commandes Textual (changer de thème) |
| `q` | quitter |

Pied de page : libellés en minuscules, la lettre de la touche colorée dans le mot (`quit - resume - copy command - …`), séparés par ` - ` ; les touches absentes du mot (`/`) sont placées devant. Implémenté en remplaçant `FooterKey.render` (écrit pour Textual 8.2.8 : à revérifier à chaque mise à jour de Textual).

### 12.7 Fenêtres modales

- **Confirmation** : bordure couleur erreur, 70 colonnes de large, boutons `Yes (y)` / `No (n)`, focus par défaut sur **No** ; `y` confirme, `n` ou `Esc` annule.
- **Renommer** : `Alias for “<nom par défaut>”`, champ prérempli avec l'alias actuel, le nom par défaut en placeholder ; `Entrée` enregistre, `Esc` annule, une valeur vide supprime l'alias.
- **Exporter** : `Export “<titre[:50]>”`, champ chemin prérempli `.`, boutons `Markdown` / `Raw JSONL` ; `Entrée` exporte en Markdown, `Tab` mène aux boutons, `Esc` annule.

### 12.8 Filtre

`/` affiche une barre de saisie d'une ligne. Le filtre s'applique à chaque frappe, sans tenir compte de la casse :
- projets : `display_name`, `project_path`, `alias` ;
- sessions : `display_title`, `first_prompt`, `session_id`.

`Entrée` cache la barre et garde le filtre ; `Esc` vide le filtre et cache la barre. Le titre du panneau devient `Projects · /<filtre>`. Le focus revient à la table filtrée.

### 12.9 Rafraîchissement et stabilité

- Rescan automatique toutes les `PI_SESSIONS_REFRESH_SECONDS` (défaut 10, 0 = désactivé), silencieux, **mis en pause** si une fenêtre modale est ouverte ou si la barre de filtre a le focus.
- Le rescan reconstruit les tables en **gardant la sélection** (par `encoded_dir` pour un projet, par `session_id` pour une session), en **remettant le défilement** là où il était (avant le prochain affichage, puis encore après le défilement automatique de Textual), et en ramenant la ligne sélectionnée à l'écran si le tri l'a déplacée.
- Lecture de `cursor_row` sur la table elle-même plutôt que dans l'événement `RowHighlighted`, dont la valeur peut être périmée.
- Barre d'état après un scan : `N projects (+M archived) - S sessions (+A archived) - L live - scan 0.4s`.

### 12.10 Thèmes

- Défaut `ansi-dark` : suit la palette du terminal et garde sa transparence. Les thèmes RGB de Textual (`nord`, `gruvbox`, `tokyo-night`, `dracula`, …) peignent un fond opaque.
- Priorité : `PI_SESSIONS_THEME` > valeur enregistrée dans `settings.json` > `ansi-dark` ; un nom inconnu revient à `ansi-dark`.
- Un changement de thème via la palette est enregistré, repousse les styles Markdown de Rich (code en ligne en secondaire gras, puces et numéros en warning gras), reconstruit les tables en gardant le curseur, et force le rendu des Détails et de la Conversation.
- Couleurs toujours prises dans le thème (`success, warning, error, primary, secondary, accent, foreground`) ; les noms `ansi_*` sont convertis pour Rich. Gris « muted » = premier plan mélangé à 55 % avec le fond, ou `bright_black` pour un thème ANSI.
- Thème pygments des blocs de code : `PI_SESSIONS_CODE_THEME` si défini, sinon la table (`nord→nord`, `gruvbox→gruvbox-dark`, `dracula→dracula`, `monokai→monokai`, `tokyo-night/catppuccin-mocha/textual-dark/flexoki→one-dark`, `catppuccin-latte/textual-light→default`, `solarized-light→solarized-light`), sinon `nord` pour un thème sombre et `default` pour un clair.

## 13. Document live

[CC] / [PI] identiques, préfixe de variables mis à part :

- `l` sur une session : crée `LiveDoc` et écrit immédiatement. `l` à nouveau : arrête le suivi en **gardant** le fichier.
- Fichier : `<dossier>/_session_<session_id>.md`. `<dossier>` = `PI_SESSIONS_LIVE_DIR` (créé si besoin) sinon le cwd de la session (doit exister, sinon erreur « project directory not available »). Le cas d'usage : un projet Quarto, dont `quarto preview` ne sert pas les fichiers à côté de lui.
- Démarrage : on lit les 1 Mo de fin pour remplir une fenêtre de 30 entrées (`deque(maxlen=30)`), puis on retient la taille du fichier comme position.
- Toutes les 2 s (timer UI) : on lit **seulement les octets ajoutés** ; une ligne incomplète est gardée pour le tour suivant ; si le fichier a rétréci (pi réécrit les fichiers lors d'une migration de version), on repart de zéro.
- Écriture au plus toutes les 1,5 s (pour ne pas saturer une synchro cloud), atomique (`.md.tmp` puis `os.replace`).
- Contenu : front matter + champs `live: yes|no`, `window: 30`, `host` (nom court de la machine), `updated` ; corps = `markdown_chunks` de la fenêtre ; pied `_Session is not running._` si la session n'est pas live.
- Une erreur d'écriture arrête le suivi et s'affiche dans la barre d'état.
- Après activation : si le cwd est un dépôt git dont le `.gitignore` ne contient pas `_session_`, afficher l'astuce « add `_session_*` to .gitignore ».
- Quitter l'application arrête tous les suivis : aucun processus en arrière-plan.
- Branches [PI] : la fenêtre suit l'ordre d'ajout dans le fichier (pas de reconstruction de branche en suivi incrémental) ; c'est acceptable puisqu'une session en cours ajoute toujours à sa branche active.

## 14. Configuration et fichiers

| Élément | [CC] | [PI] |
|---|---|---|
| Réglages (`{"theme": …}`) | `~/.config/ccsessions/settings.json` | `~/.config/pi-sessions/settings.json` |
| Alias | `~/.config/ccsessions/aliases.json` | `~/.config/pi-sessions/aliases.json` |
| Cache | `~/.cache/ccsessions/token-stats.json` | `~/.cache/pi-sessions/stats.json` |
| Thème | `CCSESSIONS_THEME` | `PI_SESSIONS_THEME` |
| Thème du code | `CCSESSIONS_CODE_THEME` | `PI_SESSIONS_CODE_THEME` |
| Dossier des docs live | `CCSESSIONS_LIVE_DIR` | `PI_SESSIONS_LIVE_DIR` |
| Intervalle de rafraîchissement | `CCSESSIONS_REFRESH_SECONDS` | `PI_SESSIONS_REFRESH_SECONDS` |
| Glyphes de l'œil | `CCSESSIONS_NERD_FONT`, `CCSESSIONS_EYE`, `CCSESSIONS_EYE_OFF` | `PI_SESSIONS_NERD_FONT`, `PI_SESSIONS_EYE`, `PI_SESSIONS_EYE_OFF` |
| Racine des sessions | — | `PI_SESSIONS_ROOT` > `PI_CODING_AGENT_SESSION_DIR` > `$PI_CODING_AGENT_DIR/sessions` > `~/.pi/agent/sessions` |
| Binaire pi | — | `PI_SESSIONS_PI_BIN` (défaut `pi`) |
| Seuil live (§8) | — | `PI_SESSIONS_LIVE_SECONDS` (défaut 120) |
| Corbeille | — | `PI_SESSIONS_TRASH` (défaut 0) |

Tous les fichiers JSON de pi-sessions : écriture atomique, lecture tolérante (fichier absent ou corrompu = valeurs vides, jamais de plantage).

**Alias** : clé = nom du dossier projet (il ne change pas quand on archive). [CC] migre d'anciennes clés « chemin » vers des clés « dossier » : inutile en [PI], il n'y a pas d'historique à migrer. Retirer un alias rend le nom par défaut. Rien n'est jamais écrit sous `~/.pi`.

## 15. Spécificité de l'environnement cible : pi-sandbox (Docker)

Sur cette machine, `pi` est `../pi-sandbox/pi.sh`, qui lance pi dans un conteneur éphémère :

- `~/.pi/agent` du conteneur est le **volume Docker nommé `pi-agent-home`**, invisible depuis l'hôte : `~/.pi` n'existe pas sur le Mac ;
- les dossiers autorisés sont montés **à leur vrai chemin** quand pi est lancé depuis l'un d'eux, donc `cwd` dans l'en-tête de session est un chemin valide sur l'hôte ; sinon ils sont montés sous `/workspace/<nom>`, un chemin qui n'existe pas sur l'hôte ;
- les pids du conteneur ne veulent rien dire sur l'hôte.

Conséquences et solutions :

1. **Accès aux sessions** (bloquant). Solution recommandée : modifier pi-sandbox pour monter un dossier de l'hôte, par exemple `-v ~/.pi/agent/sessions:/root/.pi/agent/sessions`, tout en gardant le volume pour le reste. pi-sessions lit alors `~/.pi/agent/sessions` directement. Autres options : `PI_SESSIONS_ROOT` pointant vers le point de montage du volume (non accessible sous Docker Desktop pour macOS), ou une commande de synchronisation `docker cp`, à éviter.
2. **Reprise** : `PI_SESSIONS_PI_BIN=pi` reste le lanceur ; la TUI fait `chdir(cwd)` puis exécute `pi --session <fichier>`. Le chemin du fichier doit être celui **vu depuis le conteneur** (`/root/.pi/agent/sessions/...`) : ajouter un réglage `PI_SESSIONS_RESUME_ROOT` qui remplace `sessionsRoot` par ce préfixe dans la commande, ou passer l'ID de session plutôt que le chemin.
3. **cwd `/workspace/<nom>`** : traité comme un dossier absent (avertissement dans Détails, pas de `cd`, pas de doc live sans `PI_SESSIONS_LIVE_DIR`).
4. **Live** : seuls les niveaux 1 et 3 de §8 fonctionnent.
5. **Archivage** : se fait dans le dossier monté, il n'y a donc pas de problème de droits si le montage appartient à l'utilisateur. Les fichiers créés par le conteneur appartiennent à root sous Linux : prévoir une erreur claire en cas de permission refusée.

## 16. Exigences non fonctionnelles

- **Performances** : scan hors thread UI ; statistiques en cache (mtime + taille) ; aperçu limité à la fin du fichier (512 Ko) ; export et doc live en streaming ; suivi live en lecture incrémentale. Cible : un rescan à chaud de plus de 400 sessions en moins de 0,5 s.
- **Robustesse** : aucune ligne JSON invalide, aucun champ manquant ou de mauvais type, aucun rôle inconnu ne doit faire planter l'application. Les E/S en échec dégradent l'affichage, elles ne lèvent pas d'exception jusqu'à l'utilisateur.
- **Données** : pi-sessions n'écrit dans le dossier des sessions que pour archiver, restaurer ou supprimer. Il ne modifie jamais un `.jsonl`.
- **Confidentialité** : aucune requête réseau.
- **Plateformes** : macOS et Linux. Windows non testé (pi y encode `\` et `:`, à prévoir dans le décodage).
- **Accessibilité** : glyphes Unicode simples par défaut ; Nerd Font en option ; contrastes du curseur choisis et mesurés.

## 17. Pile technique, paquet, tests

- **Recommandation : repartir du code de ccsessions dans un dépôt autonome** (Python ≥ 3.10, seule dépendance `textual>=0.80`, build hatchling). GitHub n'autorise qu'un fork par compte et le fork existant sert aux contributions à ccsessions. On crée donc un dépôt `pi-sessions` normal, dans lequel on pousse l'historique de ccsessions (`git clone` de ccsessions, renommer `origin` en `upstream`, ajouter le nouveau dépôt comme `origin`, puis `push`). L'historique et les crédits sont conservés ; on récupère les correctifs de ccsessions avec `git fetch upstream` + `cherry-pick`. Environ 70 % du code se reprend tel quel : toute l'UI, `export.py`, `watch.py`, `cache.py`, `aliases.py`, `settings.py`, `manage.py`. Ce qui change : `parser.py` (nouveau format), `discovery.py` (plus d'index), `live.py` (nouvelle détection), `resume.py` (`pi --session`), `models.py`.
- Garder la mention de copyright de la licence MIT de ccsessions.
- Paquet : `pi-sessions-tui` ; commande `pisessions` ; point d'entrée `pi_sessions.__main__:main`, qui lance l'app puis exécute la reprise si l'app a renvoyé une `ResumeRequest` (code 1 avec message sur stderr en cas d'échec).
- Structure :
  ```
  pi_sessions/
    __main__.py
    core/ models parser discovery cache live manage resume export watch aliases settings
    ui/app.py
  tests/  (pytest, fixtures dans tmp_path)
  ```
- Tests reproduisant ceux de ccsessions (parser, discovery, cache, manage, export, watch, aliases, settings, resume, ui avec `App.run_test()`), à partir de **fixtures JSONL pi réelles anonymisées** couvrant : v3 avec branches, `session_info` multiples, `bashExecution`, `compaction`, `custom_message` affiché ou non, `toolResult` avec image, ligne tronquée en fin de fichier, en-tête absent, fichier v1.
- CI : GitHub Actions (pytest sur 3.10 à 3.13), publication PyPI sur tag, comme ccsessions (`.github/workflows/ci.yml`, `publish.yml`).

## 18. Points ouverts

1. **Montage des sessions sur l'hôte** (§15.1) : changement à faire dans pi-sandbox, préalable à tout le reste sur cette machine.
2. **Niveau de détection live** : V1 heuristique seulement, ou extension pi dès le départ ?
3. **Coût** : colonne dans les tables, ou seulement dans Détails ?
4. **Blocs `thinking`** : les montrer, repliés, dans l'aperçu ?
5. ~~Fork ou nouveau dépôt~~ : tranché. Dépôt autonome avec l'historique de ccsessions et un remote `upstream` (§17).
