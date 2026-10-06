# Contrôle de l’aide intégrée — 6 octobre 2026

Périmètre : les 25 rubriques `/admin/wiki/s1` à `/admin/wiki/s25`, les traductions FR/EN, la navigation et le contenu indexé par la recherche, sur la branche `dev` après le correctif d’inventaire SMB `6c1fac4`.

Le contrôle compare les explications aux routes, permissions, paramètres, services et templates actuels. Il ne déclenche pas de restauration, suppression, installation client, arrêt distant ou écriture SMB pour vérifier une instruction.

| Rubrique | Référence contrôlée | Résultat et mise à jour |
| --- | --- | --- |
| 1 Accès | `blueprints/api.py`, `templates/index.html`, liens de prévisualisation | Adresse réelle, HTTPS et nécessité du jeton explicités. |
| 2 Affichage public | `static/js/display-screen.js` | Synchronisation de liste à environ 15 secondes ; attente du média courant, URL kiosque du serveur. |
| 3 Connexion | `blueprints/auth.py`, `services/users_svc.py` | Rôles et limites traduits en anglais ; droit d’alerte d’un utilisateur corrigé. |
| 4 Import | `services/upload_svc.py`, `templates/admin_upload.html` | Tous les imports vidéo vont en attente ; PDF par page, limites et conflits de noms documentés. |
| 5 Médiathèque | `blueprints/media.py`, `templates/admin_media.html` | Actions, ordre et affectations comparés ; droits propres à chaque action. |
| 6 Programmation | `services/media_svc.py`, `services/schedule_svc.py` | Combinaison des dates et heures, portée par écran et calendrier vérifiés. |
| 7 Écrans | `blueprints/screens.py`, `services/settings_sections.py`, installation client | Création, diffusion liée, clients et commandes distantes vérifiés ; halo et nom par défaut ajoutés. |
| 8 Éphéméride | `services/ephemeris_svc.py`, `blueprints/settings/theme.py` | Chemin Météo corrigé ; événements, saisons et vacances scolaires précisés. |
| 9 Paramètres | `services/settings_sections.py`, `blueprints/settings/language.py`, `blueprints/users.py` | Chemin et bouton de changement de mot de passe corrigés ; zones météo complétées. |
| 10 Comptes | `blueprints/users.py`, `services/users_svc.py` | Navigation Comptes & permissions corrigée ; cumul avec les rôles expliqué. |
| 11 Encodage | `services/queue_svc.py`, `blueprints/queue.py` | Fuseau, attente jusqu’à 20 h, réveil sur changement, états et encodage forcé précisés. |
| 12 Permissions | `constants.ALL_PERMISSIONS` | Tableau généré depuis les permissions réelles, dont `priority_alert` ; distinction Administrateur/super-admin. |
| 13 Groupes | actions de groupe de `blueprints/media.py`, configuration et playlist | Affectations, activation, portée écran et tirage comparés. |
| 14 Alerte | `blueprints/users.py`, `services/settings_sections.py` | Permission `priority_alert` explicitée à la place d’un accès exclusivement super-admin. |
| 15 Activité | `blueprints/activity.py`, `services/activity_svc.py` | Consultation, filtres, rétention et opérations réservées au super-admin comparés. |
| 16 Sauvegardes | `services/backup_svc.py`, `backup_scheduler_svc.py`, `backup_inventory_svc.py`, template Sauvegardes | Copie SMB, automatisation, créneau manqué, états, cache, badges, actions locales, rétention et récupération SMB avant restauration documentés. |
| 17 Campagnes | `blueprints/campaigns.py` | Consultation distinguée des actions ; `schedule` ou `toggle`, puis propriété de campagne. |
| 18 Recherche | `blueprints/search.py`, `services/search_index_svc.py` | Recherche dans l’aide et filtrage selon les droits explicités. |
| 19 Rôles | `services/rbac_svc.py`, `blueprints/roles.py` | Permissions du rôle Éditeur complétées ; droits du Lecteur et cumul corrigés. |
| 20 Modules | `constants.ALL_FEATURES` | Tableau généré depuis les modules réels. |
| 21 Version | `services/update_svc.py`, `update_log_svc.py`, `main.sh`, `dev.sh` | Commits distincts à version identique, workflow dev/main, scripts adaptés, états et migration expliqués ; aucune garantie erronée de survie après déconnexion SSH. |
| 22 À propos | `blueprints/about.py`, `templates/admin_about.html` | Identité, version, licence, technologie et accès comparés. |
| 23 Annonces | `blueprints/announcements.py`, `templates/admin_announcements.html` | `announcements` ou `upload`, reprise comme modèle, export et outil QR ajoutés/précisés. |
| 24 Menus | `blueprints/menus.py`, `services/menu_svc.py`, `services/queue_svc.py` | Permission `menus`, jour/semaine, suggestions, durée verrouillée et file comparés. |
| 25 Nettoyage | `services/media_cleanup_svc.py`, routes Nettoyage | Catégories et seuils 250 Mo/90 jours, suppression manuelle et permission comparés. |

Validation ajoutée : rendu HTTP des 25 rubriques dans les deux langues, présence des traductions utilisées, concordance des tableaux avec les définitions de l’application et recherche du nouveau contenu SMB.

Limite : ce contrôle de contenu et de rendu serveur ne constitue pas une validation visuelle dans tous les navigateurs, ni une garantie que toute future évolution sera automatiquement documentée. Les tableaux de permissions et de modules suivent automatiquement les définitions ; les explications de procédures doivent être révisées avec les changements de comportement.
