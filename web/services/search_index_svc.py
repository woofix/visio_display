# Licensed under the GNU General Public License v3.0 (GPL-3.0). Copyright (c) 2026 Eric TOMAS (Woofix). See the LICENSE file for details.

import json
import logging
import re

from db import ActivityLog, SearchIndex, db
from translations import TRANSLATIONS

LOGGER = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Search index data — admin pages and wiki sections.
# Reseeded on every startup (lightweight table, ~80 rows).
# ---------------------------------------------------------------------------

_PAGES_FR = [
    {
        'title': 'Tableau de bord',
        'url': '/admin',
        'description': "Vue d'ensemble, statistiques, médias actifs, espace disque",
        'keywords': 'tableau bord dashboard overview statistiques accueil home résumé espace disque',
    },
    {
        'title': 'Médiathèque',
        'url': '/admin/media',
        'description': 'Gestion des médias, activation, désactivation, planification',
        'keywords': 'médiathèque médias images photos vidéos fichiers bibliothèque galerie désactiver planifier gestion',
    },
    {
        'title': 'Nettoyage intelligent',
        'url': '/admin/settings/nettoyage-medias',
        'description': 'Repérer les médias périmés, inutilisés, doublons, lourds ou désactivés',
        'keywords': 'nettoyage médias périmés inutilisés doublons vidéos lourdes désactivés suppression maintenance',
    },
    {
        'title': 'Annonces',
        'url': '/admin/announcements',
        'description': 'Créer des annonces graphiques 16:9 et les exporter en PNG',
        'keywords': 'annonces éditeur affiche poster canvas texte formes images icônes png export médiathèque',
    },
    {
        'title': 'Menus',
        'url': '/admin/menus',
        'description': 'Créer des menus 16:9 avec images suggérées et programmation',
        'keywords': 'menus cantine repas entrée plat dessert semaine jour images suggestions pexels génération file encodage',
    },
    {
        'title': 'Campagnes',
        'url': '/admin/campaigns',
        'description': 'Créer et gérer les campagnes de diffusion temporaires',
        'keywords': 'campagnes campagne diffusion programmation priorité écrans groupes créer modifier gestion',
    },
    {
        'title': 'Plages de diffusion',
        'url': '/admin/programming',
        'description': 'Programmer les plages horaires de diffusion hebdomadaire',
        'keywords': 'plages diffusion programmation horaires planning semaine jours calendrier créneau gestion',
    },
    {
        'title': 'Ajouter des médias',
        'url': '/admin/upload',
        'description': 'Importer de nouveaux fichiers image, vidéo ou PDF',
        'keywords': 'upload ajouter médias importer télécharger fichiers uploader jpg png mp4 pdf glisser déposer',
    },
    {
        'title': "File d'encodage",
        'url': '/admin/upload',
        'description': "File d'attente pour la compression vidéo automatique",
        'keywords': 'file encodage compression vidéo convertir encoder queue attente compress tâches',
    },
    {
        'title': "Journal d'activité",
        'url': '/admin/activity',
        'description': 'Historique de toutes les actions effectuées',
        'keywords': 'activité journal logs historique événements audit actions utilisateurs traçabilité',
    },
    {
        'title': 'Paramètres',
        'url': '/admin/settings',
        'description': "Configuration générale de l'application",
        'keywords': 'paramètres configuration settings application général réglages options',
    },
    {
        'title': 'Logo',
        'url': '/admin/settings/logo',
        'description': 'Changer le logo affiché sur les écrans',
        'keywords': 'logo image marque brand personnalisation changer remplacer',
    },
    {
        'title': 'Thème et apparence',
        'url': '/admin/settings/theme',
        'description': "Choisir le thème de couleur de l'interface",
        'keywords': 'thème couleurs apparence design interface violet bleu vert orange sombre clair',
    },
    {
        'title': 'Langue',
        'url': '/admin/settings/language',
        'description': "Choisir la langue de l'interface",
        'keywords': 'langue language français anglais traduction interface fr en',
    },
    {
        'title': 'Gestion des utilisateurs',
        'url': '/admin/settings/comptes-permissions',
        'description': 'Gérer les comptes administrateurs et leurs droits',
        'keywords': 'gestion utilisateurs comptes administrateurs permissions droits accès mot de passe compte créer supprimer',
    },
    {
        'title': 'Rôles et permissions',
        'url': '/admin/roles',
        'description': 'Créer des rôles et attribuer leurs permissions aux utilisateurs',
        'keywords': 'rôles role permissions droits utilisateurs attribution profil administrateur éditeur lecteur',
    },
    {
        'title': 'Gestion des écrans',
        'url': '/admin/settings/gestion-ecrans',
        'description': 'Ajouter et gérer les écrans connectés',
        'keywords': 'gestion écrans displays moniteurs affichage kiosk téléviseurs ajouter supprimer halo couleur',
    },
    {
        'title': 'Alerte prioritaire',
        'url': '/admin/settings/alerte-prioritaire',
        'description': "Afficher un message d'urgence sur tous les écrans",
        'keywords': 'alerte prioritaire urgence message priorité interrompre diffusion bannière',
    },
    {
        'title': 'Sauvegardes',
        'url': '/admin/settings/sauvegardes',
        'description': 'Créer et restaurer des sauvegardes',
        'keywords': 'sauvegardes backup restaurer restore archive données exporter importer',
    },
    {
        'title': 'Météo et éphéméride',
        'url': '/admin/settings/meteo',
        'description': 'Configuration météo et calendrier des éphémérides',
        'keywords': 'météo éphéméride calendrier événements saison prévisions ville timezone',
    },
    {
        'title': 'Fonctionnalités',
        'url': '/admin/settings/fonctionnalites',
        'description': 'Activer ou désactiver les modules du site',
        'keywords': 'fonctionnalités features activer désactiver modules options upload vidéo compression groupes',
    },
    {
        'title': 'Administration clients',
        'url': '/admin/settings/installation',
        'description': 'Déployer et gérer les clients distants',
        'keywords': 'clients installation déploiement raspberry pi kiosk mise à jour remote gestion',
    },
    {
        'title': 'Changer mon mot de passe',
        'url': '/admin/settings/mot-de-passe',
        'description': 'Modifier le mot de passe du compte actuel',
        'keywords': 'mot de passe password changer modifier sécurité compte',
    },
    {
        'title': 'Documentation / Wiki',
        'url': '/admin/wiki',
        'description': "Aide, guide d'utilisation et documentation",
        'keywords': 'wiki documentation aide guide manuel help tutoriel utilisation',
    },
    {
        'title': 'Version',
        'url': '/admin/version',
        'description': "Comparer la version installée avec la version distante",
        'keywords': 'version commit git distante release vérifier',
    },
    {
        'title': 'À propos',
        'url': '/admin/about',
        'description': "Informations de version, licence et stack technique",
        'keywords': 'à propos about version commit licence auteur stack technique flask postgres docker',
    },
]

_WIKI_FR = [
    {
        'section': 's1',
        'title': "Accéder à l'application",
        'url': '/admin/wiki/s1',
        'description': "URL d'accès au panneau d'administration et à l'affichage public",
        'keywords': 'accès url admin public connexion ip hostname serveur port adresse',
    },
    {
        'section': 's2',
        'title': "L'affichage public",
        'url': '/admin/wiki/s2',
        'description': 'Diaporama, vidéos, carte éphéméride, fonctionnement en temps réel, kiosk',
        'keywords': 'affichage public diaporama slideshow vidéo kiosk raspberry écran fondu transition temps réel',
    },
    {
        'section': 's3',
        'title': "Se connecter à l'administration",
        'url': '/admin/wiki/s3',
        'description': 'Connexion, super-admin, rôles et permissions',
        'keywords': 'connexion login mot de passe super-admin utilisateur rôles droits déconnexion sécurité',
    },
    {
        'section': 's4',
        'title': 'Ajouter des médias',
        'url': '/admin/wiki/s4',
        'description': 'Import de fichiers image, vidéo ou PDF',
        'keywords': 'upload ajouter importer médias fichiers images vidéos pdf glisser déposer formats encodage',
    },
    {
        'section': 's5',
        'title': 'Gérer la médiathèque',
        'url': '/admin/wiki/s5',
        'description': 'Activer, désactiver, réordonner, planifier et supprimer les médias',
        'keywords': 'médiathèque médias gestion désactiver activer réordonner supprimer planifier durée aperçu assigner écran',
    },
    {
        'section': 's6',
        'title': "Planifier l'affichage d'un média",
        'url': '/admin/wiki/s6',
        'description': "Restreindre l'affichage à des plages horaires ou périodes de dates",
        'keywords': 'planifier plage horaire date heure calendrier programmation restriction affichage diffusion créneau',
    },
    {
        'section': 's7',
        'title': 'Gérer plusieurs écrans',
        'url': '/admin/wiki/s7',
        'description': 'Créer et gérer des écrans nommés indépendants, installation client',
        'keywords': 'écrans gestion plusieurs multi-écrans nommés créer supprimer kiosk raspberry installation client distant',
    },
    {
        'section': 's8',
        'title': 'La carte éphéméride',
        'url': '/admin/wiki/s8',
        'description': 'Météo, saint du jour, lever/coucher du soleil et événements datés',
        'keywords': 'éphéméride météo saint soleil lever coucher événements compte à rebours calendrier température vent',
    },
    {
        'section': 's9',
        'title': 'Paramètres personnels',
        'url': '/admin/wiki/s9',
        'description': 'Thème, langue et mot de passe personnel',
        'keywords': 'paramètres thème couleur langue mot de passe personnel réglages violet sombre bleu',
    },
    {
        'section': 's10',
        'title': 'Gestion des utilisateurs',
        'url': '/admin/wiki/s10',
        'description': 'Créer, modifier, supprimer les comptes et attribuer les permissions',
        'keywords': 'gestion utilisateurs comptes créer supprimer permissions droits accès mot de passe réinitialiser administrateurs',
    },
    {
        'section': 's11',
        'title': "File d'encodage vidéo",
        'url': '/admin/wiki/s11',
        'description': 'Compression vidéo automatique nocturne et suivi des tâches',
        'keywords': 'encodage vidéo compression file queue tâches nuit force annuler taille disque',
    },
    {
        'section': 's12',
        'title': 'Permissions disponibles',
        'url': '/admin/wiki/s12',
        'description': 'Liste des permissions assignables aux utilisateurs',
        'keywords': 'permissions droits upload supprimer réordonner activer durée compresser logo éphéméride planifier',
    },
    {
        'section': 's13',
        'title': 'Groupes de médias',
        'url': '/admin/wiki/s13',
        'description': 'Organiser les médias par thème et activer/désactiver un ensemble',
        'keywords': 'groupes tags médias organiser thème activer désactiver ensemble écrans chip',
    },
    {
        'section': 's14',
        'title': 'Alerte prioritaire',
        'url': '/admin/wiki/s14',
        'description': "Diffuser un message d'urgence en bannière sur tous les écrans",
        'keywords': 'alerte prioritaire urgence bannière message diffuser super-admin interruption',
    },
    {
        'section': 's15',
        'title': "Journal d'activité",
        'url': '/admin/wiki/s15',
        'description': "Historique des actions : imports, suppressions, connexions, compressions",
        'keywords': 'journal activité logs historique audit actions connexion import suppression compression configuration',
    },
    {
        'section': 's16',
        'title': 'Sauvegardes et restauration',
        'url': '/admin/wiki/s16',
        'description': 'Créer, télécharger et restaurer des archives complètes',
        'keywords': 'sauvegardes backup restaurer archive données télécharger exporter conservation super-admin',
    },
    {
        'section': 's17',
        'title': 'Campagnes temporaires',
        'url': '/admin/wiki/s17',
        'description': 'Remplacer la rotation normale par un ensemble de médias pendant une période',
        'keywords': 'campagnes temporaires diffusion priorité période médias groupes écrans archiver dupliquer',
    },
    {
        'section': 's18',
        'title': 'Recherche globale',
        'url': '/admin/wiki/s18',
        'description': "Retrouver rapidement tout contenu depuis la barre de recherche",
        'keywords': 'recherche globale chercher trouver médias campagnes pages utilisateurs cmd+k ctrl+k raccourci',
    },
    {
        'section': 's19',
        'title': 'Gestion des rôles (RBAC)',
        'url': '/admin/wiki/s19',
        'description': 'Créer des rôles réutilisables et attribuer leurs permissions aux utilisateurs',
        'keywords': 'rôles rbac permissions droits utilisateurs attribution administrateur éditeur lecteur',
    },
    {
        'section': 's20',
        'title': 'Gestion des fonctionnalités',
        'url': '/admin/wiki/s20',
        'description': "Activer ou désactiver des modules entiers de l'application",
        'keywords': 'fonctionnalités features modules activer désactiver upload vidéos campagnes écrans activité',
    },
    {
        'section': 's21',
        'title': 'Version',
        'url': '/admin/wiki/s21',
        'description': "Vérifier la version installée et la comparer à la version distante",
        'keywords': 'version commit git distante release vérifier',
    },
    {
        'section': 's22',
        'title': 'À propos',
        'url': '/admin/wiki/s22',
        'description': "Identifier la version, la licence et la stack technique de l'instance",
        'keywords': 'à propos about version commit licence auteur stack technique flask postgres docker',
    },
    {
        'section': 's23',
        'title': "Éditeur d'annonces",
        'url': '/admin/wiki/s23',
        'description': 'Créer des annonces 16:9 avec calques, outils graphiques et export PNG',
        'keywords': 'annonces éditeur canvas calques texte formes lignes images icônes png export snap grille lucide tabler',
    },
    {
        'section': 's24',
        'title': 'Menus',
        'url': '/admin/wiki/s24',
        'description': 'Créer des menus 16:9 du jour ou de la semaine',
        'keywords': 'menus cantine repas entrée plat dessert semaine jour images suggestions durée 15 secondes file encodage',
    },
    {
        'section': 's25',
        'title': 'Nettoyage intelligent',
        'url': '/admin/wiki/s25',
        'description': 'Comprendre les médias périmés, inutilisés, doublons, lourds ou désactivés',
        'keywords': 'nettoyage médias périmés inutilisés doublons vidéos lourdes désactivés suppression maintenance',
    },
]

_PAGES_EN = [
    {
        'title': 'Dashboard',
        'url': '/admin',
        'description': 'Overview, statistics, active media, disk space',
        'keywords': 'dashboard overview statistics home summary disk space',
    },
    {
        'title': 'Media Library',
        'url': '/admin/media',
        'description': 'Manage media, scheduling, enable, disable',
        'keywords': 'media library images photos videos files gallery disable schedule manage',
    },
    {
        'title': 'Smart Cleanup',
        'url': '/admin/settings/nettoyage-medias',
        'description': 'Find expired, unused, duplicate, oversized or disabled media',
        'keywords': 'cleanup media expired unused duplicates large videos disabled delete maintenance',
    },
    {
        'title': 'Announcements',
        'url': '/admin/announcements',
        'description': 'Create 16:9 graphic announcements and export them as PNG',
        'keywords': 'announcements editor poster canvas text shapes images icons png export media library',
    },
    {
        'title': 'Menus',
        'url': '/admin/menus',
        'description': 'Create 16:9 menus with suggested images and scheduling',
        'keywords': 'menus cafeteria meal starter main dessert weekly daily images suggestions pexels generation encoding queue',
    },
    {
        'title': 'Campaigns',
        'url': '/admin/campaigns',
        'description': 'Create and manage broadcast campaigns',
        'keywords': 'campaigns broadcast scheduling priority screens groups create edit manage',
    },
    {
        'title': 'Broadcast Slots',
        'url': '/admin/programming',
        'description': 'Schedule weekly broadcast time slots',
        'keywords': 'broadcast slots scheduling hours planning week days calendar',
    },
    {
        'title': 'Add Media',
        'url': '/admin/upload',
        'description': 'Import new image, video or PDF files',
        'keywords': 'upload add media import download files jpg png mp4 pdf drag drop',
    },
    {
        'title': 'Encoding Queue',
        'url': '/admin/upload',
        'description': 'Queue for automatic video compression',
        'keywords': 'encoding compression video convert encode queue waiting tasks',
    },
    {
        'title': 'Activity Log',
        'url': '/admin/activity',
        'description': 'History of all actions performed',
        'keywords': 'activity log history events audit actions users tracking',
    },
    {
        'title': 'Settings',
        'url': '/admin/settings',
        'description': 'General application configuration',
        'keywords': 'settings configuration application general options',
    },
    {
        'title': 'Logo',
        'url': '/admin/settings/logo',
        'description': 'Change the logo displayed on screens',
        'keywords': 'logo image brand customization change replace',
    },
    {
        'title': 'Theme & Appearance',
        'url': '/admin/settings/theme',
        'description': 'Choose the color theme for the interface',
        'keywords': 'theme colors appearance design interface violet blue green orange dark light',
    },
    {
        'title': 'Language',
        'url': '/admin/settings/language',
        'description': 'Choose the interface language',
        'keywords': 'language french english translation interface fr en',
    },
    {
        'title': 'User Management',
        'url': '/admin/settings/comptes-permissions',
        'description': 'Manage administrator accounts and permissions',
        'keywords': 'user management accounts administrators permissions rights access password create delete',
    },
    {
        'title': 'Roles and permissions',
        'url': '/admin/roles',
        'description': 'Create roles and assign their permissions to users',
        'keywords': 'roles permissions rights users assignment profile administrator editor viewer',
    },
    {
        'title': 'Display Screens',
        'url': '/admin/settings/gestion-ecrans',
        'description': 'Add and manage connected screens',
        'keywords': 'screens displays monitors kiosk televisions add delete halo color manage',
    },
    {
        'title': 'Priority Alert',
        'url': '/admin/settings/alerte-prioritaire',
        'description': 'Display an emergency message on all screens',
        'keywords': 'alert priority emergency message interrupt broadcast banner',
    },
    {
        'title': 'Backups',
        'url': '/admin/settings/sauvegardes',
        'description': 'Create and restore backups',
        'keywords': 'backups restore archive data export import',
    },
    {
        'title': 'Weather & Ephemeris',
        'url': '/admin/settings/meteo',
        'description': 'Weather and ephemeris calendar configuration',
        'keywords': 'weather ephemeris calendar events season forecasts city timezone',
    },
    {
        'title': 'Features',
        'url': '/admin/settings/fonctionnalites',
        'description': 'Enable or disable site modules',
        'keywords': 'features enable disable modules options upload video compression groups',
    },
    {
        'title': 'Client Administration',
        'url': '/admin/settings/installation',
        'description': 'Deploy and manage remote clients',
        'keywords': 'clients installation deployment raspberry pi kiosk update remote manage',
    },
    {
        'title': 'Change my Password',
        'url': '/admin/settings/mot-de-passe',
        'description': 'Change the current account password',
        'keywords': 'password change modify security account',
    },
    {
        'title': 'Documentation / Wiki',
        'url': '/admin/wiki',
        'description': 'Help, user guide and documentation',
        'keywords': 'wiki documentation help guide manual tutorial usage',
    },
    {
        'title': 'Version',
        'url': '/admin/version',
        'description': 'Compare the installed version with the remote version',
        'keywords': 'version commit git remote release check',
    },
    {
        'title': 'About',
        'url': '/admin/about',
        'description': 'Version, license and technical stack information',
        'keywords': 'about version commit license author stack technical flask postgres docker',
    },
]

_WIKI_EN = [
    {
        'section': 's1',
        'title': 'Access the application',
        'url': '/admin/wiki/s1',
        'description': 'URLs to access the admin panel and public display',
        'keywords': 'access url admin public login ip hostname server port address',
    },
    {
        'section': 's2',
        'title': 'Public display',
        'url': '/admin/wiki/s2',
        'description': 'Slideshow, videos, ephemeris card, real-time updates, kiosk mode',
        'keywords': 'display public slideshow video kiosk raspberry screen fade transition real-time',
    },
    {
        'section': 's3',
        'title': 'Log in to admin',
        'url': '/admin/wiki/s3',
        'description': 'Login, super-admin, roles and permissions',
        'keywords': 'login password super-admin user roles rights logout security',
    },
    {
        'section': 's4',
        'title': 'Add media',
        'url': '/admin/wiki/s4',
        'description': 'Import image, video or PDF files',
        'keywords': 'upload add import media files images videos pdf drag drop formats encoding',
    },
    {
        'section': 's5',
        'title': 'Manage the media library',
        'url': '/admin/wiki/s5',
        'description': 'Enable, disable, reorder, schedule and delete media',
        'keywords': 'media library manage disable enable reorder delete schedule duration preview assign screen',
    },
    {
        'section': 's6',
        'title': 'Schedule media display',
        'url': '/admin/wiki/s6',
        'description': 'Restrict display to specific time slots or date ranges',
        'keywords': 'schedule time slot date hour calendar programming restriction display broadcast',
    },
    {
        'section': 's7',
        'title': 'Manage multiple screens',
        'url': '/admin/wiki/s7',
        'description': 'Create and manage independent named screens, client installation',
        'keywords': 'screens manage multiple named create delete kiosk raspberry installation client remote',
    },
    {
        'section': 's8',
        'title': 'Ephemeris card',
        'url': '/admin/wiki/s8',
        'description': 'Weather, saint of the day, sunrise/sunset and dated events',
        'keywords': 'ephemeris weather saint sunrise sunset events countdown calendar temperature wind',
    },
    {
        'section': 's9',
        'title': 'Personal settings',
        'url': '/admin/wiki/s9',
        'description': 'Theme, language and personal password',
        'keywords': 'settings theme color language password personal violet dark blue',
    },
    {
        'section': 's10',
        'title': 'User management',
        'url': '/admin/wiki/s10',
        'description': 'Create, edit, delete accounts and assign permissions',
        'keywords': 'user management accounts create delete permissions rights access password reset administrators',
    },
    {
        'section': 's11',
        'title': 'Video encoding queue',
        'url': '/admin/wiki/s11',
        'description': 'Automatic nightly video compression and task tracking',
        'keywords': 'encoding video compression queue tasks night force cancel size disk',
    },
    {
        'section': 's12',
        'title': 'Available permissions',
        'url': '/admin/wiki/s12',
        'description': 'List of permissions assignable to users',
        'keywords': 'permissions rights upload delete reorder enable duration compress logo ephemeris schedule',
    },
    {
        'section': 's13',
        'title': 'Media groups',
        'url': '/admin/wiki/s13',
        'description': 'Organise media by theme and enable/disable a set at once',
        'keywords': 'groups tags media organise theme enable disable set screens chip',
    },
    {
        'section': 's14',
        'title': 'Priority alert',
        'url': '/admin/wiki/s14',
        'description': 'Broadcast an emergency banner message on all screens',
        'keywords': 'alert priority emergency banner message broadcast super-admin',
    },
    {
        'section': 's15',
        'title': 'Activity log',
        'url': '/admin/wiki/s15',
        'description': 'History of actions: uploads, deletions, logins, compressions',
        'keywords': 'activity log history audit actions login upload delete compression configuration',
    },
    {
        'section': 's16',
        'title': 'Backups and restore',
        'url': '/admin/wiki/s16',
        'description': 'Create, download and restore full archives',
        'keywords': 'backups restore archive data download export retention super-admin',
    },
    {
        'section': 's17',
        'title': 'Temporary campaigns',
        'url': '/admin/wiki/s17',
        'description': 'Replace normal rotation with a set of media during a period',
        'keywords': 'campaigns temporary broadcast priority period media groups screens archive duplicate',
    },
    {
        'section': 's18',
        'title': 'Global search',
        'url': '/admin/wiki/s18',
        'description': 'Quickly find any content from the search bar',
        'keywords': 'search global find media campaigns pages users cmd+k ctrl+k shortcut',
    },
    {
        'section': 's19',
        'title': 'Role management (RBAC)',
        'url': '/admin/wiki/s19',
        'description': 'Create reusable roles and assign their permissions to users',
        'keywords': 'roles rbac permissions rights users assignment administrator editor viewer',
    },
    {
        'section': 's20',
        'title': 'Feature management',
        'url': '/admin/wiki/s20',
        'description': 'Enable or disable entire application modules',
        'keywords': 'features modules enable disable upload videos campaigns screens activity',
    },
    {
        'section': 's21',
        'title': 'Version',
        'url': '/admin/wiki/s21',
        'description': 'Check the installed version and compare it with the remote version',
        'keywords': 'version commit git remote release check',
    },
    {
        'section': 's22',
        'title': 'About',
        'url': '/admin/wiki/s22',
        'description': 'Identify the instance version, license and technical stack',
        'keywords': 'about version commit license author stack technical flask postgres docker',
    },
    {
        'section': 's23',
        'title': 'Announcement editor',
        'url': '/admin/wiki/s23',
        'description': 'Create 16:9 announcements with layers, graphic tools and PNG export',
        'keywords': 'announcements editor canvas layers text shapes lines images icons png export snap grid lucide tabler',
    },
    {
        'section': 's24',
        'title': 'Menus',
        'url': '/admin/wiki/s24',
        'description': 'Create daily or weekly 16:9 menus',
        'keywords': 'menus cafeteria meal starter main dessert weekly daily images suggestions duration 15 seconds encoding queue',
    },
    {
        'section': 's25',
        'title': 'Smart cleanup',
        'url': '/admin/wiki/s25',
        'description': 'Understand expired, unused, duplicate, oversized or disabled media',
        'keywords': 'cleanup media expired unused duplicates large videos disabled delete maintenance',
    },
]

_SEED = {
    'fr': {'pages': _PAGES_FR, 'wiki': _WIKI_FR},
    'en': {'pages': _PAGES_EN, 'wiki': _WIKI_EN},
}

_PAGE_TRANSLATION_PREFIXES = {
    '/admin': ('dashboard_', 'nav_dashboard'),
    '/admin/media': ('media_', 'nav_media', 'display_'),
    '/admin/settings/nettoyage-medias': ('cleanup_', 'media_cleanup_', 'nav_media_cleanup'),
    '/admin/announcements': ('announcements_', 'nav_announcements'),
    '/admin/menus': ('menus_', 'menu_', 'nav_menus'),
    '/admin/campaigns': ('campaigns_', 'campaign_', 'nav_campaigns'),
    '/admin/programming': ('programming_', 'schedule_', 'nav_programming'),
    '/admin/upload': ('upload_', 'nav_upload'),
    '/admin/activity': ('activity_', 'nav_activity'),
    '/admin/settings': ('settings_', 'nav_settings'),
    '/admin/settings/logo': ('settings_logo_', 'logo_', 'nav_settings_logo'),
    '/admin/settings/theme': ('settings_theme_', 'theme_', 'nav_settings_theme'),
    '/admin/settings/language': ('settings_language_', 'language_', 'nav_settings_language'),
    '/admin/settings/comptes-permissions': ('settings_accounts_', 'accounts_', 'admins_', 'roles_', 'permissions_', 'nav_settings_accounts'),
    '/admin/roles': ('roles_', 'permissions_', 'nav_roles'),
    '/admin/settings/gestion-ecrans': ('settings_screens_', 'screens_', 'client_', 'install_', 'nav_settings_screens'),
    '/admin/settings/alerte-prioritaire': ('priority_alert_', 'alert_', 'nav_priority_alert'),
    '/admin/settings/sauvegardes': ('backup_', 'backups_', 'nav_backups'),
    '/admin/settings/meteo': ('settings_meteo_', 'meteo_', 'ephemeris_', 'nav_meteo'),
    '/admin/settings/fonctionnalites': ('feature_', 'features_', 'nav_features'),
    '/admin/settings/installation': ('install_', 'client_', 'deploy_', 'nav_installation'),
    '/admin/settings/mot-de-passe': ('password_', 'settings_password_', 'nav_password'),
    '/admin/wiki': ('wiki_hero_', 'help_', 'nav_wiki'),
    '/admin/version': ('version_', 'update_', 'nav_version'),
    '/admin/about': ('about_', 'license_', 'licence_', 'nav_about'),
}

_DYNAMIC_CATEGORIES = ('media', 'campaigns', 'config', 'users', 'activity')
_ACTIVITY_INDEX_LIMIT = 250


def _translation_values(lang):
    values = TRANSLATIONS.get(lang) or TRANSLATIONS.get('fr') or {}
    return values if isinstance(values, dict) else {}


def _translation_text(lang, prefixes):
    values = _translation_values(lang)
    parts = []
    for key, value in values.items():
        if any(key == prefix or key.startswith(prefix) for prefix in prefixes):
            parts.append(str(value))
    return ' '.join(parts)


def _wiki_content(lang, section):
    section_num = str(section).lstrip('s')
    prefixes = (
        f'wiki_s{section_num}_',
        f'wiki_s{section_num}',
        'wiki_col_',
        'wiki_perm_',
        'perm_',
    )
    return _translation_text(lang, prefixes)


def _page_content(lang, page):
    prefixes = _PAGE_TRANSLATION_PREFIXES.get(page.get('url'), ())
    return _translation_text(lang, prefixes)


def _json_meta(value):
    return json.dumps(value or {}, ensure_ascii=False, sort_keys=True)


def _search_row(category, lang, source_id, title, url, description='', keywords='', content='', meta=None):
    return SearchIndex(
        category=category,
        lang=lang,
        source_id=source_id,
        title=title,
        url=url,
        description=description or '',
        keywords=keywords or '',
        content=content or '',
        meta=_json_meta(meta),
    )


def _media_keywords(filename):
    stem = filename.rsplit('.', 1)[0] if '.' in filename else filename
    return ' '.join(re.split(r'[_\-\s\.]+', stem))


def _build_static_rows():
    rows = []
    for lang, content in _SEED.items():
        for page in content['pages']:
            rows.append(_search_row(
                'page',
                lang,
                f"page:{page['url']}",
                page['title'],
                page['url'],
                page.get('description', ''),
                page.get('keywords', ''),
                _page_content(lang, page),
            ))
        for section in content['wiki']:
            rows.append(_search_row(
                'wiki',
                lang,
                f"wiki:{section['section']}",
                section['title'],
                section['url'],
                section.get('description', ''),
                section.get('keywords', ''),
                _wiki_content(lang, section['section']),
            ))
    return rows


def _build_media_rows(cfg):
    from services.media_svc import get_all_media, get_media_groups, is_media_disabled

    rows = []
    for filename in get_all_media(cfg):
        ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
        groups = get_media_groups(filename, cfg)
        content = ' '.join(filter(None, [
            _media_keywords(filename),
            ext,
            ' '.join(groups),
        ]))
        rows.append(_search_row(
            'media',
            'all',
            f'media:{filename}',
            filename,
            '/admin/media',
            ext.upper() if ext else '',
            content,
            content,
            {
                'filename': filename,
                'ext': ext,
                'disabled': is_media_disabled(filename, cfg),
            },
        ))
    return rows


def _build_campaign_rows(cfg):
    from services.campaign_svc import get_campaigns

    rows = []
    for campaign in get_campaigns(cfg):
        campaign_id = str(campaign.get('id', ''))
        name = campaign.get('name', '')
        content = ' '.join(filter(None, [
            campaign.get('created_by', ''),
            campaign.get('start_date', ''),
            campaign.get('end_date', ''),
            ' '.join(campaign.get('screens', [])),
            ' '.join(campaign.get('groups', [])),
            ' '.join(campaign.get('media', [])),
            'archivée' if campaign.get('archived') else '',
            'active' if campaign.get('enabled') else 'inactive',
        ]))
        rows.append(_search_row(
            'campaigns',
            'all',
            f'campaign:{campaign_id}',
            name,
            f'/admin/campaigns?campaign={campaign_id}',
            f"{campaign.get('start_date', '')} {campaign.get('end_date', '')}".strip(),
            content,
            content,
            {
                'id': campaign_id,
                'name': name,
                'enabled': campaign.get('enabled', False),
                'archived': campaign.get('archived', False),
                'start_date': campaign.get('start_date', ''),
                'end_date': campaign.get('end_date', ''),
            },
        ))
    return rows


def _build_config_rows(cfg):
    rows = []
    for screen_name, screen_cfg in cfg.get('screens', {}).items():
        content = ' '.join(filter(None, [
            screen_name,
            'écran display monitor kiosk téléviseur client affichage',
            screen_cfg.get('name', '') if isinstance(screen_cfg, dict) else '',
        ]))
        rows.append(_search_row(
            'config', 'all', f'config:screen:{screen_name}', screen_name,
            '/admin/settings/gestion-ecrans', 'Écran connecté', content, content,
            {'type': 'screen'},
        ))

    groups_seen = set()
    for groups in cfg.get('groups', {}).values():
        for group in (groups if isinstance(groups, list) else []):
            if group and group not in groups_seen:
                groups_seen.add(group)
                rows.append(_search_row(
                    'config', 'all', f'config:group:{group}', group,
                    '/admin/media', 'Groupe de médias', 'groupe tag médias organiser',
                    'groupe tag médias organiser ' + group,
                    {'type': 'group'},
                ))

    app_name = cfg.get('app_name', '')
    if app_name:
        rows.append(_search_row(
            'config', 'all', 'config:app_name', app_name,
            '/admin/settings/application', "Nom de l'application",
            'application nom configuration', app_name,
            {'type': 'app'},
        ))
    return rows


def _build_user_rows():
    from services.users_svc import load_users

    rows = []
    for username, info in load_users().items():
        superadmin = bool(info.get('superadmin'))
        desc = 'super-admin' if superadmin else 'administrateur'
        rows.append(_search_row(
            'users', 'all', f'user:{username}', username,
            '/admin/settings/comptes-permissions', desc,
            'utilisateur compte admin permissions droits rôle role',
            f'{username} {desc} utilisateur compte admin permissions droits rôle role',
            {'username': username, 'superadmin': superadmin},
        ))
    return rows


def _build_activity_rows():
    rows = []
    logs = (
        ActivityLog.query
        .order_by(ActivityLog.timestamp.desc())
        .limit(_ACTIVITY_INDEX_LIMIT)
        .all()
    )
    for log in logs:
        data = log.to_dict()
        content = ' '.join(filter(None, [
            log.action,
            log.username,
            log.filename,
            log.details,
        ]))
        rows.append(_search_row(
            'activity', 'all', f'activity:{log.id}', log.action,
            '/admin/activity', f"{log.username} {log.filename or ''}".strip(),
            log.details or '', content, data,
        ))
    return rows


def _build_dynamic_rows(cfg=None):
    if cfg is None:
        from services.config_svc import load_config
        cfg = load_config()
    return (
        _build_media_rows(cfg)
        + _build_campaign_rows(cfg)
        + _build_config_rows(cfg)
        + _build_user_rows()
        + _build_activity_rows()
    )


def refresh_dynamic_search_index(cfg=None):
    try:
        SearchIndex.query.filter(SearchIndex.category.in_(_DYNAMIC_CATEGORIES)).delete(synchronize_session=False)
        rows = _build_dynamic_rows(cfg)
        if rows:
            db.session.bulk_save_objects(rows)
        db.session.commit()
    except Exception:
        db.session.rollback()
        LOGGER.exception('Failed to refresh dynamic search index')


def reseed_search_index():
    try:
        SearchIndex.query.delete()
        rows = _build_static_rows() + _build_dynamic_rows()
        if rows:
            db.session.bulk_save_objects(rows)
        db.session.commit()
    except Exception:
        db.session.rollback()
        LOGGER.exception('Failed to reseed search index')
