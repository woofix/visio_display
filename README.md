# Visio-Display — Diaporama numérique · Digital Signage

[🇫🇷 Français](#français) · [🇺🇸 English](#english)

---

## Français

Application web légère de signalétique numérique conçue pour tourner sur Raspberry Pi. Elle affiche un diaporama plein écran d'images et de vidéos avec des transitions en fondu enchaîné, et génère automatiquement une carte éphéméride quotidienne.

### Fonctionnalités

**Diaporama**
- Plein écran avec transitions en fondu enchaîné
- Images (JPG, PNG), vidéos (MP4, MOV, AVI, MKV, WebM — ré-encodées automatiquement en H.264) et PDF (convertis en images)
- Durée d'affichage configurable par média
- Liste rafraîchie à chaque changement de diapo — les modifications s'appliquent immédiatement

**Carte éphéméride**
- Générée automatiquement chaque jour (rafraîchissement toutes les 2 heures)
- Saint du jour via [nominis.cef.fr](https://nominis.cef.fr)
- Météo actuelle (température, vent, précipitations) via [Open-Meteo](https://open-meteo.com)
- Heures de lever et coucher du soleil via [sunrise-sunset.org](https://sunrise-sunset.org)
- Comptes à rebours vers des événements configurables (bac, vacances, JPO…)

**Programmation temporelle**
- Plages horaires par média — ex. menu cantine visible seulement entre 11h et 13h
- Dates d'activation/désactivation — un média actif du 2 au 15 juin uniquement
- Les deux contraintes sont combinables et indépendantes par fichier

**Gestion des écrans multiples**
- Création d'écrans nommés (ex. `hall`, `refectoire`, `salle-b12`)
- Chaque écran dispose de sa propre liste de médias, son propre ordre, ses propres désactivations, durées et programmations
- Les médias de la médiathèque principale sont assignés à un ou plusieurs écrans
- Le diaporama s'adapte automatiquement selon le paramètre `?screen=<nom>` dans l'URL

**Interface d'administration**
- Importation par glisser-déposer avec barre de progression animée (shimmer) et prévisualisation
- Animation d'upload professionnelle : spinner rotatif, pourcentage en temps réel et overlay animé pendant l'envoi
- Validation des formats à la sélection : bannière d'erreur listant les fichiers refusés (extension non supportée) avec rappel des formats acceptés
- Activation / désactivation des médias sans suppression
- Réorganisation par bouton (vues grille et liste)
- Durée d'affichage personnalisée par média
- Programmation horaire et/ou par dates par média
- Assignation des médias aux écrans nommés par bouton — l'item devient immédiatement actif sur l'écran cible
- Encodage vidéo asynchrone à l'import — barre de progression en temps réel
- File de compression vidéo nocturne (fenêtre 22h–6h) — progression visible, forçable par le super-admin
- Statistiques d'utilisation du disque
- Visionneuse plein écran au clic
- Nom de l'application personnalisable
- Choix de la langue de l'interface (français / anglais)
- Choix du thème de l'interface : Violet, Noir, Bleu

**Sécurité & accès**
- Contrôle d'accès à deux niveaux : super-admin et utilisateurs limités
- Permissions granulaires configurables par compte
- Restrictions d'accès par écran — un utilisateur peut gérer un ou plusieurs écrans spécifiques

### Prérequis

- Docker
- Docker Compose

### Installation

```bash
git clone <url-du-dépôt>
cd Visio-Display
cp .env.example .env
# Éditer .env : renseigner ADMIN_USER, ADMIN_PASSWORD et SECRET_KEY
docker compose up -d --build
```

L'application est disponible sur `http://<hôte>:8081`.

**Générer une SECRET_KEY sécurisée :**

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

### Configuration

**Variables d'environnement (`.env`)**

| Variable         | Description                                                        |
|------------------|--------------------------------------------------------------------|
| `ADMIN_USER`     | Nom du compte super-admin (créé au premier démarrage uniquement)   |
| `ADMIN_PASSWORD` | Mot de passe du super-admin (8 caractères minimum)                 |
| `SECRET_KEY`     | Clé de signature des sessions Flask (obligatoire)                  |

> Ces variables ne sont lues qu'une seule fois, lors du premier démarrage (base de données absente).

**Coordonnées GPS et résolution** — modifier dans `web/app.py` :

| Variable           | Description                                            | Valeur par défaut |
|--------------------|--------------------------------------------------------|-------------------|
| `LAT` / `LNG`      | Coordonnées GPS pour météo et lever/coucher du soleil  | Perpignan         |
| `MAX_WIDTH/HEIGHT` | Dimensions maximales des images                        | 1920 × 1080       |

### Utilisation

**Diaporama (affichage) :** ouvrir `http://<hôte>:8081` dans un navigateur plein écran.

**Diaporama sur un écran nommé :** `http://<hôte>:8081?screen=<nom>`

**Mode kiosque sur Raspberry Pi :**

```bash
chromium-browser --kiosk --noerrdialogs --disable-infobars http://localhost:8081
```

**Interface d'administration :** ouvrir `http://<hôte>:8081/admin` et se connecter.

### Rôles et permissions

**Super-admin**
- Créé automatiquement au premier démarrage depuis `ADMIN_USER` / `ADMIN_PASSWORD`
- Accès complet à toutes les fonctionnalités, seul compte ne pouvant pas être supprimé
- Peut forcer l'encodage vidéo hors de la fenêtre nocturne
- Peut personnaliser le nom de l'application
- Accède au panneau dédié sur `/admin/superadmin`

**Utilisateurs réguliers**
- Créés par le super-admin, aucune permission par défaut
- Le super-admin accorde ou révoque chaque permission individuellement
- Le super-admin définit quels écrans chaque utilisateur peut gérer (aucune restriction par défaut)

| Permission    | Action autorisée                                                         |
|---------------|--------------------------------------------------------------------------|
| `upload`      | Importer des médias                                                      |
| `delete`      | Supprimer des médias                                                      |
| `reorder`     | Réordonner les médias                                                    |
| `toggle`      | Activer / désactiver des médias, assigner aux écrans                     |
| `duration`    | Modifier la durée d'affichage par média                                  |
| `compress`    | Mettre des vidéos en file de compression                                 |
| `logo`        | Changer ou réinitialiser le logo                                         |
| `ephemeris`   | Forcer la régénération de l'éphéméride et gérer les comptes à rebours    |
| `schedule`    | Programmer l'affichage des médias (horaires / dates)                     |

### Restrictions d'écrans par utilisateur

Depuis `/admin/superadmin`, le super-admin peut limiter chaque utilisateur à un sous-ensemble d'écrans nommés. Un utilisateur restreint ne voit que ses écrans autorisés dans la médiathèque et ne peut pas modifier les autres.

- Laisser toutes les cases décochées = accès à tous les écrans (comportement par défaut)
- Cocher un ou plusieurs écrans = accès limité à ces écrans uniquement
- Le super-admin a toujours accès à tous les écrans, sans restriction

### Gestion des écrans multiples

Les écrans sont créés depuis la médiathèque (`/admin/media`). Chaque écran nommé est accessible en lecture à l'adresse `/?screen=<nom>`.

- Les noms d'écran sont limités à 1–32 caractères (minuscules, chiffres, tirets, underscores)
- Les noms réservés (`default`, `admin`, `api`, `static`, `login`, `logout`) ne peuvent pas être utilisés
- Un même média peut appartenir à plusieurs écrans simultanément
- Chaque écran hérite des médias assignés mais dispose de son propre ordre, ses désactivations, durées et programmations

### Assignation des médias aux écrans

Depuis la médiathèque, en sélectionnant un écran nommé, les médias non encore assignés apparaissent dans une section dédiée en bas de page.

Pour assigner un média à l'écran courant, cliquer sur le bouton **« Ajouter à l'écran »** sous la vignette. La page se recharge automatiquement : le média apparaît aussitôt dans la grille de l'écran avec son état actif et toutes ses options de gestion (durée, programmation, désactivation).

Pour retirer un média de l'écran courant, cliquer sur **« Retirer de l'écran »** dans le menu de la vignette. La page se recharge automatiquement : le média disparaît de la grille de l'écran et reste disponible dans la médiathèque principale.

### Encodage vidéo

À l'import, les vidéos non conformes (hors H.264/MP4) sont **encodées en arrière-plan** : la page répond immédiatement et affiche une barre de progression par fichier. Un bouton « Voir les médias » apparaît une fois l'encodage terminé.

Une fois l'encodage initial effectué, la vidéo est ajoutée en file de compression nocturne (22h–6h) pour réduction de taille. La progression de cette étape est visible sur la page `/admin/queue`.

### Structure du projet

```
Visio-Display/
├── .github/workflows/ci.yml     # CI GitHub Actions (lint + tests)
├── docker-compose.yml           # Services : app, worker, redis
├── Dockerfile
├── .env.example
├── LICENSE
├── README.md
└── web/
    ├── app.py                   # Flask factory (create_app)
    ├── wsgi.py                  # Point d'entrée Gunicorn
    ├── db.py                    # Modèles SQLAlchemy (AppConfig, User, EncodeJob)
    ├── constants.py             # Constantes partagées
    ├── translations.py          # Traductions FR/EN
    ├── encode_now.py            # Encodage vidéo (exécuté par le worker RQ)
    ├── pyproject.toml           # Config ruff + pytest
    ├── requirements.txt         # Dépendances de production
    ├── requirements-dev.txt     # Dépendances de développement/test
    ├── blueprints/              # Blueprints Flask
    │   ├── admin.py             # Tableau de bord
    │   ├── api.py               # API JSON
    │   ├── auth.py              # Connexion / déconnexion
    │   ├── ephemeris.py         # Carte éphéméride
    │   ├── guards.py            # Helpers de contrôle d'accès
    │   ├── media.py             # Médiathèque
    │   ├── queue.py             # File d'encodage
    │   ├── screens.py           # Gestion des écrans
    │   ├── settings.py          # Paramètres (thème, langue, logo)
    │   └── users.py             # Gestion des utilisateurs
    ├── services/                # Logique métier
    │   ├── config_svc.py        # Configuration applicative (lecture/écriture)
    │   ├── ephemeris_svc.py     # Génération de la carte éphéméride
    │   ├── media_svc.py         # Opérations sur les fichiers médias
    │   ├── queue_svc.py         # File d'encodage + tâches RQ
    │   └── users_svc.py         # CRUD utilisateurs + permissions
    ├── static/
    │   ├── data/                # Médias + base SQLite ramses.db (non versionné)
    │   └── images/              # Logo et ressources statiques
    ├── templates/               # Templates Jinja2
    │   ├── index.html           # Diaporama plein écran
    │   ├── login.html           # Page de connexion
    │   ├── admin_layout.html    # Gabarit partagé (sidebar, topbar, thèmes)
    │   ├── admin_dashboard.html # Vue d'ensemble + espace disque
    │   ├── admin_media.html     # Médiathèque + réorganisation + écrans
    │   ├── admin_upload.html    # Import de médias + suivi d'encodage
    │   ├── admin_queue.html     # File d'encodage + progression
    │   ├── admin_settings.html  # Logo, thème, langue, mot de passe, événements
    │   └── admin_superadmin.html # Gestion des comptes, permissions et écrans
    └── tests/                   # Tests pytest (57 tests)
        ├── conftest.py
        ├── test_config_svc.py
        ├── test_queue_svc.py
        ├── test_queue_rq.py
        └── test_users_svc.py
```

> `web/static/data/` est exclu du contrôle de version.

### API

| Endpoint                                  | Méthode | Auth               | Description                                          |
|-------------------------------------------|---------|--------------------|------------------------------------------------------|
| `/api/images`                             | GET     | Non                | Liste des médias actifs (`?screen=<nom>` optionnel)  |
| `/api/durations`                          | GET     | Non                | Durées d'affichage par fichier (`?screen=<nom>`)     |
| `/api/config`                             | GET     | Non                | Configuration complète                               |
| `/api/diskusage`                          | GET     | Non                | Statistiques disque                                  |
| `/api/queue`                              | GET     | Connecté           | État de la file d'encodage (compression + upload)    |
| `/upload`                                 | POST    | `upload`           | Importer des fichiers (retourne JSON + jobs d'encodage) |
| `/delete/<filename>`                      | POST    | `delete`           | Supprimer un fichier                                 |
| `/toggle/<filename>`                      | POST    | `toggle`           | Activer / désactiver un fichier                      |
| `/set_duration/<filename>`                | POST    | `duration`         | Définir la durée d'affichage                         |
| `/reorder`                                | POST    | `reorder`          | Enregistrer le nouvel ordre                          |
| `/compress/<filename>`                    | POST    | `compress`         | Mettre une vidéo en file de compression              |
| `/queue/cancel/<job_id>`                  | POST    | `compress`         | Annuler un job en attente                            |
| `/regen_ephemeride`                       | POST    | `ephemeris`        | Forcer la régénération de l'éphéméride               |
| `/schedule/<filename>`                    | POST    | `schedule`         | Définir la programmation horaire/date d'un média     |
| `/screen_assign/<filename>`               | POST    | `toggle`           | Assigner / retirer un média d'un écran nommé         |
| `/admin/screens/add`                      | POST    | Connecté           | Créer un écran nommé                                 |
| `/admin/screens/delete/<name>`            | POST    | Connecté           | Supprimer un écran nommé                             |
| `/admin/settings/theme`                   | POST    | Connecté           | Changer le thème de l'interface                      |
| `/admin/settings/language`                | POST    | Connecté           | Changer la langue de l'interface (fr/en)             |
| `/admin/settings/appname`                 | POST    | Super-admin        | Personnaliser le nom de l'application                |
| `/admin/logo/upload`                      | POST    | `logo`             | Uploader un logo personnalisé                        |
| `/admin/logo/reset`                       | POST    | `logo`             | Réinitialiser le logo par défaut                     |
| `/admin/users/add`                        | POST    | Super-admin        | Créer un compte utilisateur                          |
| `/admin/users/delete/<username>`          | POST    | Super-admin        | Supprimer un compte utilisateur                      |
| `/admin/users/permissions/<username>`     | POST    | Super-admin        | Mettre à jour les permissions                        |
| `/admin/users/screens/<username>`         | POST    | Super-admin        | Définir les écrans accessibles à un utilisateur      |
| `/admin/users/password`                   | POST    | Connecté           | Modifier son propre mot de passe                     |
| `/admin/users/reset_password/<username>`  | POST    | Super-admin        | Réinitialiser le mot de passe d'un utilisateur       |
| `/admin/events/add`                       | POST    | `ephemeris`        | Ajouter un compte à rebours dans l'éphéméride        |
| `/admin/events/delete/<idx>`              | POST    | `ephemeris`        | Supprimer un compte à rebours                        |
| `/admin/queue/force`                      | POST    | Super-admin        | Forcer l'encodage de toute la file immédiatement     |
| `/admin/compress/<filename>/force`        | POST    | Super-admin        | Forcer l'encodage d'un seul fichier immédiatement    |

#### Réponse de `/api/queue`

```json
{
  "active":      [ { "id": "…", "filename": "…", "status": "pending|processing", "progress": 45 } ],
  "recent":      [ { "id": "…", "filename": "…", "status": "done|error", "before": 5.2, "after": 0.4, "ratio": 13.0 } ],
  "upload_jobs": [ { "filename": "…", "status": "processing|done|error", "progress": 72 } ],
  "window":      true,
  "now_hour":    23
}
```

### Format de `config.json`

**Programmation (`schedules`)**

```json
{
  "schedules": {
    "cantine.jpg": {
      "time_start": "11:00",
      "time_end":   "13:00"
    },
    "annonces_examens.jpg": {
      "date_start": "2026-06-02",
      "date_end":   "2026-06-15"
    }
  }
}
```

Les quatre champs (`time_start`, `time_end`, `date_start`, `date_end`) sont tous optionnels et combinables. Un média sans entrée dans `schedules` s'affiche toujours.

**Événements (`events`)**

```json
{
  "events": [
    { "label": "Baccalauréat", "date": "2026-06-16" },
    { "label": "Vacances d'été", "date": "2026-07-05" }
  ]
}
```

**Écrans nommés (`screens`)**

```json
{
  "screens": {
    "hall": {
      "order":     ["affiche.jpg", "video.mp4"],
      "disabled":  [],
      "durations": { "affiche.jpg": 20 },
      "schedules": {}
    }
  }
}
```

### Stockage des données

La configuration et les utilisateurs sont stockés dans une base SQLite (`web/static/data/ramses.db`), persistée via le volume Docker. La structure des utilisateurs est la suivante :

```json
{
  "alice": {
    "password":    "<bcrypt>",
    "superadmin":  true,
    "permissions": []
  },
  "bob": {
    "password":    "<bcrypt>",
    "superadmin":  false,
    "permissions": ["upload", "toggle", "duration"],
    "screens":     ["hall", "refectoire"]
  }
}
```

Le champ `screens` est optionnel. Absent ou `null` = accès à tous les écrans. Une liste vide ou un sous-ensemble = accès restreint aux écrans listés.

### Migration depuis une version antérieure

Si un fichier `users.json` au format ancien existe dans le volume, il est migré automatiquement vers la base SQLite au premier démarrage : le premier compte devient super-admin, les suivants deviennent des utilisateurs sans permissions.

### Licence

MIT License — Copyright (c) 2026 Woofix

---

## English

A lightweight web-based digital signage application designed to run on a Raspberry Pi. It displays a fullscreen slideshow of images and videos with smooth crossfade transitions, and automatically generates a daily ephemeris card.

### Features

**Slideshow**
- Fullscreen display with crossfade transitions
- Images (JPG, PNG), videos (MP4, MOV, AVI, MKV, WebM — automatically re-encoded to H.264) and PDFs (converted to images)
- Configurable display duration per media item
- Media list refreshed on every slide transition — changes apply immediately

**Ephemeris card**
- Generated automatically each day (refreshed every 2 hours)
- Saint of the day via [nominis.cef.fr](https://nominis.cef.fr)
- Current weather (temperature, wind, precipitation) via [Open-Meteo](https://open-meteo.com)
- Sunrise and sunset times via [sunrise-sunset.org](https://sunrise-sunset.org)
- Countdown timers to configurable events (exams, holidays, open days…)

**Time-based scheduling**
- Time-of-day slots per media — e.g. canteen menu visible only from 11 AM to 1 PM
- Date ranges — a media active from June 2 to June 15 only
- Both constraints are independent and combinable per file

**Multi-screen management**
- Create named screens (e.g. `hall`, `cafeteria`, `room-b12`)
- Each screen has its own media list, order, disabled items, durations, and schedules
- Media from the main library can be assigned to one or more screens
- The slideshow automatically adapts based on the `?screen=<name>` URL parameter

**Admin interface**
- Drag-and-drop file import with animated (shimmer) progress bar and preview
- Professional upload animation: rotating spinner, real-time percentage counter and animated overlay during transfer
- Format validation on file selection: error banner listing rejected files (unsupported extension) with a reminder of accepted formats
- Enable / disable media without deleting it
- Button-based reordering (grid and list views)
- Custom display duration per media item
- Time and/or date scheduling per media item
- Media assignment to named screens via button — item is immediately active on the target screen
- Asynchronous video encoding on upload — real-time per-file progress bar
- Overnight video compression queue (window: 10 PM–6 AM) — progress visible, force-startable by super-admin
- Disk usage statistics
- Fullscreen media viewer on click
- Customizable application name
- UI language selection (French / English)
- UI theme selection: Violet, Black, Blue

**Security & access**
- Two-level access control: super-admin and limited users
- Granular permissions configurable per account
- Per-screen access restrictions — a user can manage one or several specific screens

### Requirements

- Docker
- Docker Compose

### Installation

```bash
git clone <repository-url>
cd Visio-Display
cp .env.example .env
# Edit .env: set ADMIN_USER, ADMIN_PASSWORD and SECRET_KEY
docker compose up -d --build
```

The application will be available at `http://<host>:8081`.

**Generate a secure SECRET_KEY:**

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

### Configuration

**Environment variables (`.env`)**

| Variable         | Description                                                       |
|------------------|-------------------------------------------------------------------|
| `ADMIN_USER`     | Super-admin username (read only on first boot)                    |
| `ADMIN_PASSWORD` | Super-admin password (minimum 8 characters)                       |
| `SECRET_KEY`     | Flask session signing key (required)                              |

> These variables are only read once, on first boot (when the database does not yet exist).

**GPS coordinates and resolution** — edit in `web/app.py`:

| Variable           | Description                                   | Default         |
|--------------------|-----------------------------------------------|-----------------|
| `LAT` / `LNG`      | GPS coordinates for weather and sun times     | Perpignan, FR   |
| `MAX_WIDTH/HEIGHT` | Maximum image dimensions                      | 1920 × 1080     |

### Usage

**Slideshow (display):** open `http://<host>:8081` in a fullscreen browser.

**Slideshow on a named screen:** `http://<host>:8081?screen=<name>`

**Kiosk mode on Raspberry Pi:**

```bash
chromium-browser --kiosk --noerrdialogs --disable-infobars http://localhost:8081
```

**Admin interface:** open `http://<host>:8081/admin` and log in with your credentials.

### Roles & Permissions

**Super-admin**
- Created automatically on first boot from `ADMIN_USER` / `ADMIN_PASSWORD`
- Full access to every feature, the only account that cannot be deleted
- Can force video encoding outside the overnight window
- Can customize the application name
- Accesses the dedicated panel at `/admin/superadmin`

**Regular users**
- Created by the super-admin, no permissions by default
- The super-admin grants or revokes each permission individually
- The super-admin defines which screens each user can manage (no restriction by default)

| Permission    | Allowed action                                                        |
|---------------|-----------------------------------------------------------------------|
| `upload`      | Import media files                                                    |
| `delete`      | Delete media files                                                    |
| `reorder`     | Reorder media items                                                   |
| `toggle`      | Enable / disable media items, assign to screens                       |
| `duration`    | Set custom display duration per item                                  |
| `compress`    | Queue videos for compression                                          |
| `logo`        | Change or reset the application logo                                  |
| `ephemeris`   | Force ephemeris regeneration and manage countdown events              |
| `schedule`    | Schedule media display by time of day and/or date range               |

### Per-screen access restrictions

From `/admin/superadmin`, the super-admin can restrict each user to a subset of named screens. A restricted user only sees their allowed screens in the media library and cannot modify others.

- All boxes unchecked = access to all screens (default behaviour)
- One or more boxes checked = access limited to those screens only
- The super-admin always has unrestricted access to all screens

### Multi-screen management

Screens are created from the media library (`/admin/media`). Each named screen is accessible at `/?screen=<name>`.

- Screen names are limited to 1–32 characters (lowercase letters, digits, hyphens, underscores)
- Reserved names (`default`, `admin`, `api`, `static`, `login`, `logout`) cannot be used
- A single media item can be assigned to multiple screens at once
- Each screen inherits the assigned media but has its own order, disabled list, durations, and schedules

### Assigning media to screens

When a named screen is selected in the media library, unassigned media items appear in a dedicated section at the bottom of the page.

To assign a media item to the current screen, click the **"Add to screen"** button below the thumbnail. The page reloads automatically: the item immediately appears in the screen grid with its active state and all management options (duration, scheduling, enable/disable).

To remove a media item from the current screen, click **"Remove from screen"** in the thumbnail menu. The page reloads automatically: the item disappears from the screen grid and remains available in the main media library.

### Video encoding

On upload, non-conformant videos (not H.264/MP4) are **encoded in the background**: the page responds immediately and shows a per-file progress bar. A "View media" button appears once encoding is complete.

After initial encoding, the video is queued for overnight compression (10 PM–6 AM) to reduce file size. The progress of that step is visible on `/admin/queue`.

### Project structure

```
Visio-Display/
├── .github/workflows/ci.yml     # GitHub Actions CI (lint + tests)
├── docker-compose.yml           # Services: app, worker, redis
├── Dockerfile
├── .env.example
├── LICENSE
├── README.md
└── web/
    ├── app.py                   # Flask factory (create_app)
    ├── wsgi.py                  # Gunicorn entry point
    ├── db.py                    # SQLAlchemy models (AppConfig, User, EncodeJob)
    ├── constants.py             # Shared constants
    ├── translations.py          # FR/EN translations
    ├── encode_now.py            # Video encoding (run by the RQ worker)
    ├── pyproject.toml           # Ruff + pytest config
    ├── requirements.txt         # Production dependencies
    ├── requirements-dev.txt     # Dev/test dependencies
    ├── blueprints/              # Flask blueprints
    │   ├── admin.py             # Dashboard
    │   ├── api.py               # JSON API
    │   ├── auth.py              # Login / logout
    │   ├── ephemeris.py         # Ephemeris card
    │   ├── guards.py            # Access control helpers
    │   ├── media.py             # Media library
    │   ├── queue.py             # Encoding queue
    │   ├── screens.py           # Screen management
    │   ├── settings.py          # Settings (theme, language, logo)
    │   └── users.py             # User management
    ├── services/                # Business logic
    │   ├── config_svc.py        # App config (read/write)
    │   ├── ephemeris_svc.py     # Ephemeris card generation
    │   ├── media_svc.py         # Media file operations
    │   ├── queue_svc.py         # Encoding queue + RQ tasks
    │   └── users_svc.py         # User CRUD + permissions
    ├── static/
    │   ├── data/                # Media files + SQLite DB ramses.db (not versioned)
    │   └── images/              # Logo and static assets
    ├── templates/               # Jinja2 templates
    │   ├── index.html           # Fullscreen slideshow
    │   ├── login.html           # Login page
    │   ├── admin_layout.html    # Shared layout (sidebar, topbar, themes)
    │   ├── admin_dashboard.html # Overview + disk usage
    │   ├── admin_media.html     # Media library + reordering + screens
    │   ├── admin_upload.html    # Media import + encoding progress
    │   ├── admin_queue.html     # Encoding queue + progress bars
    │   ├── admin_settings.html  # Logo, theme, language, password, events
    │   └── admin_superadmin.html # Account, permission and screen management
    └── tests/                   # pytest test suite (57 tests)
        ├── conftest.py
        ├── test_config_svc.py
        ├── test_queue_svc.py
        ├── test_queue_rq.py
        └── test_users_svc.py
```

> `web/static/data/` is excluded from version control.

### API

| Endpoint                                  | Method  | Auth               | Description                                             |
|-------------------------------------------|---------|--------------------|-------------------------------------------------------|
| `/api/images`                             | GET     | No                 | Active media list (`?screen=<name>` optional)           |
| `/api/durations`                          | GET     | No                 | Per-file display durations (`?screen=<name>`)           |
| `/api/config`                             | GET     | No                 | Full configuration                                      |
| `/api/diskusage`                          | GET     | No                 | Disk usage stats                                        |
| `/api/queue`                              | GET     | Logged in          | Encoding queue state (compression + upload jobs)        |
| `/upload`                                 | POST    | `upload`           | Upload files (returns JSON with encoding job list)      |
| `/delete/<filename>`                      | POST    | `delete`           | Delete a file                                           |
| `/toggle/<filename>`                      | POST    | `toggle`           | Enable / disable a file                                 |
| `/set_duration/<filename>`                | POST    | `duration`         | Set display duration                                    |
| `/reorder`                                | POST    | `reorder`          | Save new media order                                    |
| `/compress/<filename>`                    | POST    | `compress`         | Queue a video for compression                           |
| `/queue/cancel/<job_id>`                  | POST    | `compress`         | Cancel a pending compression job                        |
| `/regen_ephemeride`                       | POST    | `ephemeris`        | Force ephemeris card regeneration                       |
| `/schedule/<filename>`                    | POST    | `schedule`         | Set time/date scheduling for a media item               |
| `/screen_assign/<filename>`               | POST    | `toggle`           | Assign / remove a media item from a named screen        |
| `/admin/screens/add`                      | POST    | Logged in          | Create a named screen                                   |
| `/admin/screens/delete/<name>`            | POST    | Logged in          | Delete a named screen                                   |
| `/admin/settings/theme`                   | POST    | Logged in          | Change the UI theme                                     |
| `/admin/settings/language`                | POST    | Logged in          | Change the UI language (fr/en)                          |
| `/admin/settings/appname`                 | POST    | Super-admin        | Set the application name                                |
| `/admin/logo/upload`                      | POST    | `logo`             | Upload a custom logo                                    |
| `/admin/logo/reset`                       | POST    | `logo`             | Reset to default logo                                   |
| `/admin/users/add`                        | POST    | Super-admin        | Create a user account                                   |
| `/admin/users/delete/<username>`          | POST    | Super-admin        | Delete a user account                                   |
| `/admin/users/permissions/<username>`     | POST    | Super-admin        | Update a user's permissions                             |
| `/admin/users/screens/<username>`         | POST    | Super-admin        | Set accessible screens for a user                       |
| `/admin/users/password`                   | POST    | Logged in          | Change own password                                     |
| `/admin/users/reset_password/<username>`  | POST    | Super-admin        | Reset another user's password                           |
| `/admin/events/add`                       | POST    | `ephemeris`        | Add a countdown event to the ephemeris card             |
| `/admin/events/delete/<idx>`              | POST    | `ephemeris`        | Delete a countdown event                                |
| `/admin/queue/force`                      | POST    | Super-admin        | Force-process all pending encoding jobs immediately     |
| `/admin/compress/<filename>/force`        | POST    | Super-admin        | Force-encode a single file immediately                  |

#### `/api/queue` response

```json
{
  "active":      [ { "id": "…", "filename": "…", "status": "pending|processing", "progress": 45 } ],
  "recent":      [ { "id": "…", "filename": "…", "status": "done|error", "before": 5.2, "after": 0.4, "ratio": 13.0 } ],
  "upload_jobs": [ { "filename": "…", "status": "processing|done|error", "progress": 72 } ],
  "window":      true,
  "now_hour":    23
}
```

### `config.json` format

**Scheduling (`schedules`)**

```json
{
  "schedules": {
    "canteen.jpg": {
      "time_start": "11:00",
      "time_end":   "13:00"
    },
    "exam_notice.jpg": {
      "date_start": "2026-06-02",
      "date_end":   "2026-06-15"
    }
  }
}
```

All four fields (`time_start`, `time_end`, `date_start`, `date_end`) are optional and combinable. A media item with no entry in `schedules` is always displayed.

**Events (`events`)**

```json
{
  "events": [
    { "label": "Baccalaureate", "date": "2026-06-16" },
    { "label": "Summer holidays", "date": "2026-07-05" }
  ]
}
```

**Named screens (`screens`)**

```json
{
  "screens": {
    "hall": {
      "order":     ["poster.jpg", "video.mp4"],
      "disabled":  [],
      "durations": { "poster.jpg": 20 },
      "schedules": {}
    }
  }
}
```

### Data storage

Configuration and users are stored in a SQLite database (`web/static/data/ramses.db`), persisted via the Docker volume. The user data structure is as follows:

```json
{
  "alice": {
    "password":    "<bcrypt>",
    "superadmin":  true,
    "permissions": []
  },
  "bob": {
    "password":    "<bcrypt>",
    "superadmin":  false,
    "permissions": ["upload", "toggle", "duration"],
    "screens":     ["hall", "cafeteria"]
  }
}
```

The `screens` field is optional. Absent or `null` = access to all screens. An empty list or a subset = restricted to the listed screens only.

### Migration from earlier versions

If a `users.json` file in the old format exists in the volume, it is migrated automatically to the SQLite database on first startup: the first account becomes the super-admin, all others become regular users with no permissions.

### License

MIT License — Copyright (c) 2026 Woofix
