# Guide utilisateur — Visio-Display

Visio-Display est une application d'**affichage dynamique** (digital signage) qui fait défiler automatiquement des images, vidéos et une carte météo/éphéméride sur un ou plusieurs écrans. Elle se pilote depuis n'importe quel navigateur via une interface d'administration web.

---

## Sommaire

1. [Accéder à l'application](#1-accéder-à-lapplication)
2. [L'affichage public](#2-laffichage-public)
3. [Se connecter à l'administration](#3-se-connecter-à-ladministration)
4. [Ajouter des médias](#4-ajouter-des-médias)
5. [Gérer la médiathèque](#5-gérer-la-médiathèque)
6. [Groupes de médias](#6-groupes-de-médias)
7. [Planifier l'affichage d'un média](#7-planifier-laffichage-dun-média)
8. [Gérer plusieurs écrans](#8-gérer-plusieurs-écrans)
9. [La carte éphéméride](#9-la-carte-éphéméride)
10. [Paramètres personnels](#10-paramètres-personnels)
11. [Gestion des utilisateurs (super-admin)](#11-gestion-des-utilisateurs-super-admin)
12. [File d'encodage vidéo](#12-file-dencodage-vidéo)
13. [Alerte prioritaire (super-admin)](#13-alerte-prioritaire-super-admin)
14. [Permissions disponibles](#14-permissions-disponibles)
15. [Wiki — aide intégrée](#15-wiki--aide-intégrée)

---

## 1. Accéder à l'application

| Usage | Adresse |
|---|---|
| Affichage public (écran par défaut) | `http://<adresse-du-serveur>:8081` |
| Affichage d'un écran nommé | `http://<adresse-du-serveur>:8081?screen=nom-ecran` |
| Interface d'administration | `http://<adresse-du-serveur>:8081/admin` |

Remplacez `<adresse-du-serveur>` par l'adresse IP ou le nom d'hôte de votre serveur (ex. : `192.168.1.50` ou `raspberrypi.local`).

---

## 2. L'affichage public

La page d'affichage est conçue pour fonctionner en plein écran, sans interaction utilisateur.

- Le **diaporama défile automatiquement** : chaque média s'affiche pendant sa durée configurée (15 secondes par défaut), puis une transition en fondu enchaîné amène le suivant.
- Les **vidéos** sont lues intégralement (ou jusqu'à la durée limite configurée).
- La **carte éphéméride** (météo, lever/coucher du soleil, saint du jour, compte à rebours) est automatiquement insérée dans la rotation.
- La liste des médias se **met à jour en temps réel** : tout changement effectué dans l'administration prend effet au prochain changement de diapositive, sans rechargement de la page.

> **Conseil d'utilisation** : Sur un Raspberry Pi, configurez le navigateur en mode kiosk (`chromium-browser --kiosk http://localhost:8081`) pour un affichage plein écran sans barre de navigation.

---

## 3. Se connecter à l'administration

1. Ouvrez `http://<adresse-du-serveur>:8081/admin` dans votre navigateur.
2. Entrez votre **nom d'utilisateur** et votre **mot de passe**.
3. Cliquez sur **Connexion**.

Le tableau de bord affiche un résumé : nombre de médias, espace disque utilisé/disponible, et des accès rapides vers les différentes sections.

Pour vous déconnecter, cliquez sur votre nom en haut à droite puis **Déconnexion**.

---

## 4. Ajouter des médias

> **Permission requise :** `upload`

1. Dans le menu de navigation, allez dans **Importer**.
2. **Glissez-déposez** vos fichiers dans la zone prévue, ou cliquez dessus pour ouvrir le sélecteur de fichiers.
3. Vous pouvez envoyer **plusieurs fichiers en même temps**.

### Formats acceptés

| Type | Extensions |
|---|---|
| Images | `.jpg`, `.jpeg`, `.png` |
| Vidéos | `.mp4`, `.mov`, `.avi`, `.mkv`, `.webm` |
| Documents | `.pdf` (converti automatiquement en image) |

### Encodage vidéo automatique

Les vidéos qui ne sont pas déjà au format H.264/MP4 sont **automatiquement réencodées** en arrière-plan. Pendant ce temps :
- Une barre de progression par fichier indique l'avancement.
- Le média est utilisable dès que l'encodage à la volée est terminé.
- Une compression supplémentaire peut être planifiée la nuit (22h–6h) pour réduire la taille sur le disque.

Une fois l'import terminé, le bouton **Voir les médias** vous redirige vers la médiathèque.

---

## 5. Gérer la médiathèque

> **Permissions requises selon l'action :** `toggle`, `reorder`, `duration`, `delete`

Accédez à **Médias** dans le menu.

### Vue d'ensemble

Chaque média est affiché avec :
- Son **aperçu miniature** (ou icône pour les vidéos)
- Son **nom de fichier**, sa taille, ses dimensions (images)
- Son **statut** : actif ou désactivé
- Sa **durée d'affichage** personnalisée (si définie)
- Ses **règles de planification** (si définies)

### Actions disponibles

| Action | Description |
|---|---|
| **Activer / Désactiver** | Un média désactivé reste dans la bibliothèque mais n'apparaît pas dans le diaporama. |
| **Modifier la durée** | Définissez en secondes le temps d'affichage de ce média. Laissez vide pour utiliser la valeur par défaut (15 s). |
| **Planifier** | Restreignez l'affichage à certaines heures ou dates (voir section 6). |
| **Prévisualiser** | Ouvre le média en plein écran pour vérification. |
| **Supprimer** | Supprime définitivement le fichier. |

### Réordonner

Faites glisser les médias pour modifier l'ordre de passage dans le diaporama. L'ordre est **propre à chaque écran**.

### Assigner un média à un écran

Les médias non assignés apparaissent dans une section séparée en bas de page. Cliquez sur **Ajouter à l'écran** pour les intégrer à l'écran actuellement sélectionné.

---

## 6. Groupes de médias

> **Permission requise :** `toggle`

Les groupes (ou tags) permettent d'organiser les médias par thème et d'activer ou désactiver un ensemble d'un seul clic.

### Attribuer des groupes à un média

1. Dans la médiathèque, ouvrez le menu **Actions** du média souhaité.
2. Saisissez les groupes dans le champ prévu, séparés par des virgules (ex. : `menu`, `infos`, `urgences`).
3. Cliquez sur **Enregistrer les groupes**.

Un média peut appartenir à plusieurs groupes simultanément.

### Activer / désactiver un groupe

La section **Groupes** (barre latérale gauche de la médiathèque) liste tous les groupes définis. Cliquez sur **Activer le groupe** ou **Désactiver le groupe** pour basculer tous ses médias d'un coup.

Un badge **GROUPE DÉSACTIVÉ** s'affiche sur les médias concernés dans la grille.

> **Remarque :** Un média désactivé individuellement reste désactivé même si son groupe est activé.

---

## 7. Planifier l'affichage d'un média

> **Permission requise :** `schedule`

La planification permet d'afficher un média uniquement dans une **plage horaire** ou une **période de dates** définie. Les deux conditions peuvent être combinées.

### Configurer une planification

1. Dans la médiathèque, cliquez sur l'icône de planification du média souhaité.
2. Renseignez les champs souhaités :

| Champ | Format | Exemple |
|---|---|---|
| Heure de début | HH:MM | `11:00` |
| Heure de fin | HH:MM | `13:30` |
| Date de début | AAAA-MM-JJ | `2026-06-02` |
| Date de fin | AAAA-MM-JJ | `2026-06-15` |

3. Cliquez sur **Enregistrer**. La règle prend effet au prochain changement de diapositive.

> **Exemple :** Un menu de cantine visible uniquement de 11h à 13h, du lundi au vendredi — configurez `11:00`–`13:00` en plage horaire. L'affichage s'arrête et reprend automatiquement.

Pour supprimer une planification, videz les champs et enregistrez.

---

## 8. Gérer plusieurs écrans

Visio-Display permet de créer des **écrans nommés indépendants**, chacun avec sa propre liste de médias, son propre ordre et ses propres règles.

### Créer un écran

> **Droit requis :** super-admin

1. Dans la médiathèque, ouvrez le menu de gestion des écrans.
2. Saisissez un nom (lettres minuscules, chiffres, `-` et `_` ; entre 1 et 32 caractères).
3. Cliquez sur **Créer**.

Noms réservés (interdits) : `default`, `admin`, `api`, `static`, `login`, `logout`.

### Accéder à un écran

- **Affichage public :** `http://<serveur>:8081?screen=nom-ecran`
- **Administration :** Sélectionnez l'écran via le sélecteur en haut de la médiathèque.

### Fonctionnement par écran

- Chaque écran gère **indépendamment** l'ordre, l'activation, la durée et la planification de chaque média.
- Un même fichier peut être **assigné à plusieurs écrans simultanément**.
- Les utilisateurs peuvent être **restreints à certains écrans** (voir section 11).

---

## 9. La carte éphéméride

La carte éphéméride est une image générée automatiquement qui s'intègre dans la rotation du diaporama.

### Contenu affiché

- **Saint du jour**
- **Météo actuelle** : température, ressenti, vitesse du vent, précipitations
- **Lever et coucher du soleil**
- **Comptes à rebours** personnalisés (ex. : *Vacances d'été : 42 jours*)

### Mise à jour

- La carte se **régénère toutes les 2 heures** et automatiquement à minuit.
- Un bouton **Forcer la régénération** est disponible dans les paramètres (permission `ephemeris`).

### Gérer les comptes à rebours

> **Permission requise :** `ephemeris`

Dans **Paramètres → Événements** :
1. Cliquez sur **Ajouter un événement**.
2. Entrez un libellé (ex. : `Baccalauréat`) et la date cible (format `AAAA-MM-JJ`).
3. Cliquez sur **Enregistrer**.

Le compte à rebours apparaît sur la carte à la prochaine régénération. Cliquez sur la corbeille pour supprimer un événement.

---

## 10. Paramètres personnels

Accessible depuis **Paramètres** dans le menu.

### Thème de l'interface

Choisissez entre trois thèmes visuels pour votre session :
- **Violet** (par défaut)
- **Sombre**
- **Bleu**

Ce réglage est **personnel** : il ne modifie pas l'affichage des autres utilisateurs.

### Langue de l'interface

Choisissez entre **Français (FR)** et **Anglais (EN)**.

### Localisation météo (super-admin)

Depuis **Paramètres → Météo**, le super-admin peut modifier la localisation utilisée pour la carte éphéméride :

| Champ           | Exemple           | Description                                  |
|-----------------|-------------------|----------------------------------------------|
| Ville           | `Montpellier`     | Nom affiché sur la carte éphéméride          |
| Latitude        | `43.6119`         | Coordonnée GPS (décimale, entre -90 et 90)   |
| Longitude       | `3.8772`          | Coordonnée GPS (décimale, entre -180 et 180) |
| Fuseau horaire  | `Europe/Paris`    | Identifiant IANA                             |
| Zone scolaire   | `A` / `B` / `C`  | Zone de l'Éducation nationale (détection automatique si non renseignée) |

Cliquer sur **Enregistrer** applique la nouvelle localisation et régénère la carte immédiatement.

### Changer son mot de passe

1. Dans **Paramètres → Sécurité**, saisissez votre mot de passe actuel.
2. Entrez le nouveau mot de passe (8 caractères minimum).
3. Confirmez et cliquez sur **Enregistrer**.

---

## 11. Gestion des utilisateurs (super-admin)

Accessible depuis **Administration → Utilisateurs**.

### Créer un compte

1. Cliquez sur **Nouvel utilisateur**.
2. Renseignez le nom d'utilisateur et un mot de passe (8 caractères minimum).
3. Cliquez sur **Créer**.

Le compte est créé **sans aucune permission**. Attribuez ensuite les droits nécessaires.

### Attribuer des permissions

Dans la liste des utilisateurs, cliquez sur un utilisateur pour modifier ses permissions. Cochez ou décochez chaque permission individuellement (voir [section 14](#14-permissions-disponibles)).

### Restreindre l'accès à des écrans

Dans la fiche d'un utilisateur, section **Écrans autorisés** :
- **Aucune case cochée** → l'utilisateur peut gérer tous les écrans.
- **Cases cochées** → l'utilisateur ne voit et ne gère que les écrans sélectionnés.

### Réinitialiser un mot de passe

Cliquez sur **Réinitialiser le mot de passe** dans la fiche de l'utilisateur et saisissez le nouveau mot de passe.

### Supprimer un compte

Cliquez sur **Supprimer** dans la fiche de l'utilisateur. Le compte super-admin ne peut pas être supprimé.

---

## 12. File d'encodage vidéo

Accessible depuis **File d'encodage** dans le menu.

### Fenêtre d'encodage automatique

Par défaut, la compression des vidéos est planifiée la nuit entre **22h et 6h** pour limiter l'impact sur les performances.

### Suivi des tâches

- **Jobs en cours :** liste les compressions actives avec leur pourcentage d'avancement.
- **Jobs récents :** affiche les compressions terminées avec les statistiques (taille avant/après, taux de compression).

### Forcer l'encodage (super-admin)

- **Forcer tout :** lance immédiatement toutes les compressions en attente, hors fenêtre nocturne.
- **Forcer un fichier :** dans la médiathèque, cliquez sur l'icône de compression d'un média spécifique.

### Annuler une tâche

Les utilisateurs avec la permission `compress` peuvent annuler une tâche **en attente** (pas encore démarrée) depuis la file d'encodage.

---

## 13. Alerte prioritaire (super-admin)

> **Droit requis :** super-admin

L'alerte prioritaire permet de diffuser **immédiatement** un message en bannière sur l'écran d'affichage, sans interrompre le diaporama.

### Utilisation

1. Depuis **Administration → Super-Admin**, section **Alerte prioritaire**.
2. Saisissez votre message dans le champ prévu (280 caractères maximum).
3. La bannière est publiée **automatiquement** après chaque frappe — aucun bouton à cliquer.
4. Pour retirer la bannière, cliquez sur **Effacer la bannière**.

> **Attention :** La bannière reste affichée sur **tous les écrans** jusqu'à suppression manuelle, quel que soit le paramètre `?screen=` utilisé.

---

## 14. Permissions disponibles

| Permission | Actions autorisées |
|---|---|
| `upload` | Importer des médias |
| `delete` | Supprimer des médias |
| `reorder` | Modifier l'ordre des médias |
| `toggle` | Activer/désactiver des médias et des groupes, assigner à un écran |
| `duration` | Modifier la durée d'affichage |
| `compress` | Mettre en file d'encodage, annuler une tâche |
| `logo` | Changer ou réinitialiser le logo de l'application |
| `ephemeris` | Régénérer la carte éphéméride, gérer les comptes à rebours |
| `schedule` | Définir des planifications horaires et de dates |

> Le super-admin dispose de **toutes les permissions** et peut en plus : créer/supprimer des comptes, créer/supprimer des écrans, personnaliser le nom de l'application, configurer la localisation météo, publier une alerte prioritaire et forcer l'encodage hors fenêtre nocturne.

---

## 15. Wiki — aide intégrée

Accessible depuis **Wiki** dans le menu de navigation.

La page Wiki est une documentation interactive intégrée directement à l'interface d'administration. Elle couvre l'ensemble des fonctionnalités de Visio-Display : gestion des médias, planification, écrans multiples, encodage vidéo, permissions, etc.

- Disponible à tout moment depuis n'importe quelle page de l'administration.
- Organisée par sections avec une table des matières latérale pour naviguer rapidement.
- Aucune connexion externe requise — le contenu est embarqué dans l'application.

---

*Documentation générée pour Visio-Display — Application d'affichage dynamique.*
