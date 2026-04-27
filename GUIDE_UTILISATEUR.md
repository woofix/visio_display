<!-- Licensed under the GNU General Public License v3.0 (GPL-3.0). Copyright (c) 2026 Eric TOMAS (Woofix). See the LICENSE file for details. -->

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
15. [Journal d'activité](#15-journal-dactivité)
16. [Wiki — aide intégrée](#16-wiki--aide-intégrée)
17. [Sauvegarder et restaurer le serveur](#17-sauvegarder-et-restaurer-le-serveur)
18. [Campagnes temporaires](#18-campagnes-temporaires)
19. [Recherche globale](#19-recherche-globale)

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
- Un **sélecteur d'écran** est affiché en bas de la page — semi-transparent au repos, pleinement visible au survol. Cliquez sur un écran pour y basculer directement sans retaper l'URL.

> **Conseil d'utilisation** : Sur un Raspberry Pi, configurez le navigateur en mode kiosk (`chromium-browser --kiosk http://localhost:8081`) pour un affichage plein écran sans barre de navigation.

Si vous utilisez l'installation client automatique depuis l'administration, saisissez l'**URL de base du serveur** (par exemple `https://cargot.tomas66.net`) puis, si besoin, le **nom d'écran**. Le client reconstruit lui-même l'URL finale d'affichage et ajoute `?screen=<nom>` uniquement quand un écran nommé est configuré.

### À savoir

- Un média **désactivé** ou **hors plage de diffusion** n'apparaît pas sur l'écran public, même s'il reste visible dans l'administration.
- Chaque **écran nommé** possède sa propre sélection de médias, son propre ordre et ses propres règles.
- Les changements deviennent visibles **sans recharger** la page publique : il suffit d'attendre la prochaine transition.

---

## 3. Se connecter à l'administration

1. Ouvrez `http://<adresse-du-serveur>:8081/admin` dans votre navigateur.
2. Entrez votre **nom d'utilisateur** et votre **mot de passe**.
3. Cliquez sur **Connexion**.

Le tableau de bord affiche un résumé : nombre de médias, espace disque utilisé/disponible, et des accès rapides vers les différentes sections.

Pour vous déconnecter, cliquez sur votre nom en haut à droite puis **Déconnexion**.

### Après connexion

- Les menus affichés dépendent de vos **permissions** : certaines sections peuvent être absentes si votre compte n'y a pas accès.
- Le tableau de bord sert surtout de **point d'entrée rapide** ; la gestion détaillée se fait ensuite dans la médiathèque, les paramètres et les plages de diffusion.

### Différence entre super-admin et utilisateur

| Profil | Ce qu'il peut faire | Limites |
|---|---|---|
| **Super-admin** | Accède à toute l'application, tous les écrans, tous les réglages globaux, la gestion des comptes, les sauvegardes, l'installation client, les fonctionnalités système et l'alerte prioritaire. | Son compte ne peut pas être supprimé depuis l'interface et ses permissions ne se retirent pas comme celles d'un utilisateur. |
| **Utilisateur** | Accède uniquement aux menus et actions correspondant aux permissions attribuées par le super-admin. Il peut aussi être limité à certains écrans. | Ne peut pas gérer les comptes, accorder des permissions, créer/supprimer des écrans, restaurer le serveur, publier l'alerte prioritaire ou modifier les réglages réservés au super-admin. |

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
- Une compression supplémentaire peut être planifiée la nuit (20h–6h) pour réduire la taille sur le disque.

Une fois l'import terminé, le bouton **Voir les médias** vous redirige vers la médiathèque.

### Bonnes pratiques

- Utilisez des **noms de fichiers explicites** : ils seront réutilisés dans la médiathèque, les plages de diffusion et le journal d'activité.
- Après import, vérifiez la **durée d'affichage**, l'**activation** et l'**écran cible** dans la médiathèque.
- Les **PDF** sont intégrés comme contenus visuels ; si le rendu ne convient pas, il vaut souvent mieux préparer une image exportée au bon format.

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

### Lire la médiathèque

- La **recherche** et les **filtres** permettent d'isoler rapidement les médias actifs, désactivés ou d'un type précis.
- Les **badges** visibles sur une carte signalent notamment un média désactivé, une plage enregistrée ou un groupe désactivé.
- La vue dépend de **l'écran sélectionné** : vérifiez toujours l'onglet d'écran avant de modifier l'ordre ou les affectations.

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

L'entrée **Médiathèque** du menu n'affiche pas de compteur du nombre de médias.

> **Remarque :** Un média désactivé individuellement reste désactivé même si son groupe est activé.

### Lier un groupe à des écrans

Par défaut, un groupe est **global** : il apparaît dans la barre de groupes quel que soit l'écran sélectionné.

Vous pouvez restreindre un groupe à un ou plusieurs écrans spécifiques :

1. Dans le panneau **Groupes** en haut de la médiathèque, repérez le groupe souhaité.
2. Cliquez sur l'icône **🔗** en bout de chip pour ouvrir le sélecteur d'écrans.
3. Cliquez sur les écrans auxquels ce groupe doit être lié — les boutons actifs s'affichent en violet (l'entrée **Défaut** correspond à l'écran sans paramètre `?screen=`).
4. La liaison est enregistrée immédiatement. Le groupe n'apparaîtra plus que sur les écrans sélectionnés.

> **Remarque :** Si aucun écran n'est sélectionné, le groupe redevient global (visible sur tous les écrans).

---

## 7. Planifier l'affichage d'un média

> **Permission requise :** `schedule`

La planification permet d'afficher un média uniquement dans une **plage horaire** ou une **période de dates** définie. Les deux conditions peuvent être combinées.

La page **Plages de diffusion** propose également un **calendrier hebdomadaire**. Les noms des jours y suivent la langue choisie dans l'interface : en français, ils s'affichent en français.

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

### Comment la règle est interprétée

- Si vous renseignez uniquement les **heures**, le média réapparaît **chaque jour** dans cette plage horaire, sans date de fin.
- Si vous renseignez uniquement les **dates**, le média reste visible **toute la journée** entre ces deux dates, incluses.
- Si vous combinez **dates et heures**, les deux conditions doivent être vraies en même temps : le média n'est affiché que pendant les heures choisies et seulement entre les dates définies.
- Si vous laissez **tous les champs vides**, vous supprimez la restriction : le média redevient visible en continu.
- La planification s'applique au média sur **l'écran concerné**. Un même fichier peut donc avoir des règles différentes selon l'écran.

### Lire la page Plages de diffusion

- La liste récapitule chaque règle enregistrée avec l'écran, le média, les groupes et la plage active.
- Le calendrier hebdomadaire montre les plages prévues jour par jour pour repérer rapidement les trous ou les chevauchements.
- Les noms des jours suivent la langue de l'interface.

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

- **Affichage public :** `http://<serveur>:8081?screen=nom-ecran` — le sélecteur d'écran en bas de la page permet aussi de basculer directement.
- **Médiathèque :** sélectionnez l'écran via les onglets en haut ; le bouton **Prévisualiser** (à droite de la barre) ouvre une fenêtre d'aperçu de l'écran actif.
- **Tableau de bord :** la carte **Prévisualiser** propose un bouton par écran pour ouvrir le diaporama correspondant dans un nouvel onglet.

### Fonctionnement par écran

- Chaque écran gère **indépendamment** l'ordre, l'activation, la durée et la planification de chaque média.
- Un même fichier peut être **assigné à plusieurs écrans simultanément**.
- Les utilisateurs peuvent être **restreints à certains écrans** (voir section 11).
- Le super-admin peut personnaliser le **nom affiché de l'écran par défaut** et la **couleur de halo** utilisée autour des médias pendant la lecture.

> **Conseil :** lors de l'installation d'un client d'affichage, indiquez l'URL de base du serveur puis, si nécessaire, le nom d'écran. Le poste client construit lui-même l'URL finale à ouvrir.

### Installer un client d'affichage

Depuis **Paramètres > Installation client** :

1. Renseignez l'hôte ou l'IP du poste client, le port SSH, l'utilisateur SSH et l'utilisateur local à configurer.
2. Saisissez l'**URL de base du serveur** (ex. `https://cargot.tomas66.net`), pas une URL écrite en dur par écran.
3. Renseignez le **nom d'écran** si le poste doit ouvrir un écran nommé (ex. `reception`, `cuisine`).
4. Renseignez le **nom de la machine** cliente.
5. Lancez l'installation.

Le script configure automatiquement l'autologin, le mode kiosque, le nom d'hôte Linux, la veille désactivée pendant l'affichage et la remontée d'état du client vers le serveur.

### Clients détectés

Dans l'onglet **Paramètres > Installation client**, la zone **Clients détectés** se met à jour automatiquement. Les nouvelles installations remontent leur IP, leur nom de machine et leur écran environ toutes les 30 secondes.

### Contrôle client distant

> **Droit requis :** super-admin

Depuis **Paramètres > Installation client**, la zone **Contrôle client** permet d’agir directement sur un poste déjà connu :

- l’hôte se choisit dans la liste des clients détectés ; ce formulaire n’accepte pas de saisie libre d’IP ;
- **Arrêter le client** envoie une commande d’arrêt immédiate ;
- **Redémarrer le client** envoie une commande de redémarrage immédiate ;
- **Réinstaller le client** relance le script d’installation du poste ;
- **Mettre à jour Debian** lance la mise à jour système du poste.

> **Attention :** la réinstallation du client n’est pas une simple mise à jour système ; elle relance bien la procédure d’installation du client d’affichage.

### Watchdog kiosque

Le super-admin peut configurer la politique de surveillance envoyée aux clients installés :

- l'intervalle entre deux vérifications ;
- le délai de grâce après le démarrage ;
- le nombre d'échecs consécutifs avant redémarrage automatique.

Cette politique aide un client kiosque à revenir tout seul en service si le navigateur d'affichage cesse durablement de fonctionner.

---

## 9. La carte éphéméride

La carte éphéméride est une image générée automatiquement qui s'intègre dans la rotation du diaporama.

### Contenu affiché

- **Saint du jour**
- **Météo actuelle** : température, ressenti, vitesse du vent, précipitations
- **Lever et coucher du soleil**
- **Événements datés** personnalisés (ex. : *Vacances d'été : 42 jours*)

### Mise à jour

- La carte se **régénère toutes les 2 heures** et automatiquement à minuit.
- Si le fichier de l'éphéméride est absent, il est **régénéré automatiquement** au prochain rafraîchissement du diaporama.
- Quand l'éphéméride est recréée ou mise à jour, elle s'affiche automatiquement dans le diaporama sans recharger la page.

### Gérer les événements datés

> **Permission requise :** `ephemeris`

Seuls les **prochains événements à venir** sont affichés sur la carte. Le libellé saisi dans les paramètres est repris tel quel.

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

La langue choisie modifie les **libellés de l'administration** et du **wiki intégré**. Elle n'a pas d'effet sur les médias eux-mêmes.

### Localisation météo (super-admin)

Depuis **Paramètres → Météo** (entrée directe dans le menu gauche), le super-admin peut modifier la localisation utilisée pour la carte éphéméride :

| Champ           | Exemple           | Description                                  |
|-----------------|-------------------|----------------------------------------------|
| Ville           | `Montpellier`     | Nom affiché sur la carte éphéméride          |
| Latitude        | `43.6119`         | Coordonnée GPS (décimale, entre -90 et 90)   |
| Longitude       | `3.8772`          | Coordonnée GPS (décimale, entre -180 et 180) |
| Fuseau horaire  | `Europe/Paris`    | Identifiant IANA                             |
| Zone scolaire   | `A` / `B` / `C`  | Zone de l'Éducation nationale (détection automatique si non renseignée) |

Un champ de recherche par nom de ville (autocomplétion via Open-Meteo) remplit automatiquement les coordonnées et le fuseau horaire. Cliquer sur **Enregistrer** applique la nouvelle localisation et régénère la carte immédiatement.

### Changer son mot de passe

1. Dans **Paramètres → Admins**, descendez jusqu'à la section **Changer le mot de passe**.
2. Saisissez votre mot de passe actuel, puis le nouveau (10 caractères minimum).
3. Cliquez sur **Enregistrer**.

---

## 11. Gestion des utilisateurs (super-admin)

Accessible depuis **Paramètres → Utilisateurs**.

L'entrée **Utilisateurs** du menu n'affiche pas de compteur du nombre de comptes.

> **Réservé au super-admin :** seul le super-admin peut créer des comptes, supprimer des comptes utilisateurs, modifier les permissions et limiter les utilisateurs à certains écrans.

### Créer un compte

1. Cliquez sur **Ajouter un compte**.
2. Renseignez le nom d'utilisateur et un mot de passe (10 caractères minimum).
3. Cliquez sur **Créer**.

Le compte est créé **sans aucune permission**. Attribuez ensuite les droits nécessaires.

### Attribuer des permissions

Dans la liste des utilisateurs, cliquez sur un utilisateur pour modifier ses permissions. Cochez ou décochez chaque permission individuellement (voir [section 14](#14-permissions-disponibles)).

Un utilisateur **sans permission** peut se connecter, mais ne verra que les sections autorisées par son profil.

### Restreindre l'accès à des écrans

Dans la fiche d'un utilisateur, section **Écrans autorisés** :
- **Aucune case cochée** → l'utilisateur peut gérer tous les écrans.
- **Cases cochées** → l'utilisateur ne voit et ne gère que les écrans sélectionnés.

### Réinitialiser un mot de passe

Cliquez sur **Réinitialiser le mot de passe** dans la fiche de l'utilisateur et saisissez le nouveau mot de passe.

Le mot de passe du **super-admin** ne se réinitialise pas depuis l'interface. En cas de perte, utilisez le script de maintenance `web/tools/reset_superadmin_password.py` depuis le serveur (voir le `README.md` pour la procédure).

### Supprimer un compte

Cliquez sur **Supprimer** dans la fiche de l'utilisateur. Le compte super-admin ne peut pas être supprimé.

---

## 12. File d'encodage vidéo

Accessible depuis **File d'encodage** dans le menu.

### Fenêtre d'encodage automatique

Par défaut, la compression des vidéos est planifiée la nuit entre **20h et 6h** pour limiter l'impact sur les performances.

### Suivi des tâches

- **Jobs en cours :** liste les compressions actives avec leur pourcentage d'avancement.
- **Jobs récents :** affiche les compressions terminées avec les statistiques (taille avant/après, taux de compression).

### Forcer l'encodage (super-admin)

- **Forcer tout :** lance immédiatement toutes les compressions en attente, hors fenêtre nocturne.
- **Forcer un fichier :** dans la médiathèque, cliquez sur l'icône de compression d'un média spécifique.

### Annuler une tâche

Les utilisateurs avec la permission `compress` peuvent annuler une tâche **en attente** (pas encore démarrée) depuis la file d'encodage.

> **Remarque :** l'encodage améliore surtout la compatibilité et réduit la taille disque des vidéos. Il n'est généralement pas utile pour une image ou un PDF.

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
| `ephemeris` | Régénérer la carte éphéméride, gérer les événements datés |
| `schedule` | Définir des planifications horaires et de dates |

### Rôles et limites

| Type de compte | Peut faire | Ne peut pas faire |
|---|---|---|
| **Super-admin** | Tout ce que permettent les permissions, plus les actions d'administration globale : utilisateurs, écrans, sauvegardes, météo, installation client, fonctionnalités, alerte prioritaire et encodage forcé. | Son compte et ses permissions sont protégés dans l'interface courante. |
| **Utilisateur** | Uniquement les actions couvertes par ses permissions, et seulement sur les écrans autorisés si une restriction est définie. | Créer ou supprimer des comptes, accorder des permissions, créer ou supprimer des écrans, restaurer le serveur, publier l'alerte prioritaire ou modifier les réglages globaux réservés. |

> Le super-admin dispose de **toutes les permissions** et peut en plus : créer/supprimer des comptes, créer/supprimer des écrans, personnaliser le nom de l'application, configurer la localisation météo, publier une alerte prioritaire et forcer l'encodage hors fenêtre nocturne.

Les permissions peuvent être **combinées librement**. Donnez seulement les droits nécessaires à la tâche de l'utilisateur.

---

## 15. Journal d'activité

Accessible depuis **Journal d'activité** dans le menu de navigation.

Le journal sert d'**historique d'exploitation** : il permet de vérifier rapidement qui a fait quoi avant de conclure à un dysfonctionnement.

Le journal retrace les actions effectuées sur l'application par les utilisateurs connectés, ainsi que certaines opérations système automatiques.

Les opérations sensibles d'administration utilisent une session authentifiée protégée par cookie sécurisé côté serveur, contrôle CSRF sur les formulaires et appels d'écriture, et déconnexion confirmée par action `POST`.

### Actions enregistrées

| Action | Description |
|---|---|
| **Upload** | Import d'un fichier (image, vidéo ou PDF) — utilisateur et fichier indiqués |
| **Suppression** | Suppression définitive d'un fichier |
| **Connexion** | Ouverture de session |
| **Déconnexion** | Fermeture de session via action sécurisée |
| **Activation** | Activation ou désactivation d'un média ou d'un groupe — l'état résultant (`enabled` / `disabled`) et l'écran concerné sont précisés |
| **Compression** | Démarrage et résultat d'une compression vidéo automatique (taille avant/après, taux de réduction) — effectuée par `system` |
| **Configuration** | Modifications d'administration : durées, ordre des médias, plages de diffusion, groupes, écrans, logo, thème, langue, météo, utilisateurs, permissions, alerte prioritaire, etc. |
| **Campagne** | Création, mise à jour, duplication, activation/désactivation et archivage des campagnes |

### Filtres disponibles

- **Recherche libre** : par nom de fichier, utilisateur ou détails
- **Par type d'action** : Upload, Suppression, Connexion, Déconnexion, Activation, Compression, Configuration, Campagne
- **Par utilisateur**

### Rétention et espace disque

Le journal est **purgé automatiquement** pour éviter une croissance infinie de la base SQLite :

- les entrées trop anciennes sont supprimées automatiquement ;
- un plafond de lignes est appliqué même si l'activité est très importante ;
- un compactage SQLite (`VACUUM`) est lancé périodiquement après purge pour récupérer l'espace disque devenu inutile.

Par défaut :

- **conservation** : `90` jours ;
- **taille maximale** : `20000` entrées ;
- **fréquence de purge** : `1` heure ;
- **fréquence minimale de compactage** : `24` heures.

Ces valeurs peuvent être ajustées via les variables d'environnement `ACTIVITY_LOG_RETENTION_DAYS`, `ACTIVITY_LOG_MAX_ROWS`, `ACTIVITY_LOG_CLEANUP_INTERVAL_SECONDS` et `ACTIVITY_LOG_VACUUM_INTERVAL_SECONDS`.

> **Note :** Les compressions vidéo automatiques (planifiées la nuit) sont enregistrées sous l'utilisateur `system`. Les opérations de configuration apparaissent avec l'action **Configuration** et les opérations de campagnes avec l'action **Campagne**.

---

## 16. Wiki — aide intégrée

Accessible depuis **Wiki** dans le menu de navigation.

La page Wiki est une documentation interactive intégrée directement à l'interface d'administration. Elle couvre l'ensemble des fonctionnalités de Visio-Display : gestion des médias, planification, écrans multiples, encodage vidéo, permissions, etc.

Elle reflète aussi les règles de sécurité de l'interface : session administrateur, formulaires protégés par jeton CSRF et déconnexion via bouton sécurisé.

- Disponible à tout moment depuis n'importe quelle page de l'administration.
- Organisée par sections avec une table des matières latérale pour naviguer rapidement.
- Aucune connexion externe requise — le contenu est embarqué dans l'application.

## 17. Sauvegarder et restaurer le serveur

Si vous devez recréer le serveur sur une autre machine ou repartir sur une nouvelle stack Docker, utilisez les scripts fournis à la racine du projet.

### Créer une sauvegarde

Depuis le dossier du projet :

```bash
scripts/docker_backup.sh
```

Le script crée un dossier dans `backups/` contenant :

- `postgres.dump` : la base PostgreSQL
- `media.tar.gz` : les médias importés
- `private.tar.gz` : les données privées de l’application
- `env.backup` : une copie du `.env` si présent

Vous pouvez aussi choisir le dossier de destination :

```bash
scripts/docker_backup.sh /chemin/vers/sauvegarde-visio
```

### Restaurer à l’identique

1. recopiez le projet et votre dossier de sauvegarde sur la nouvelle machine ;
2. placez-vous dans le dossier du projet ;
3. lancez :

```bash
scripts/docker_restore.sh backups/visio-backup-YYYYMMDD-HHMMSS
```

La restauration :

- arrête temporairement l’application ;
- démarre PostgreSQL et Redis ;
- remet les médias et les données privées ;
- restaure la base PostgreSQL ;
- relance la stack complète.

Si vous souhaitez aussi réappliquer le `.env` sauvegardé même si un `.env` existe déjà :

```bash
scripts/docker_restore.sh --force-env backups/visio-backup-YYYYMMDD-HHMMSS
```

> Conseil : effectuez la sauvegarde quand aucun import massif ou traitement vidéo n’est en cours, pour figer un état propre.

### Sauvegarde depuis l'administration

Le **super-admin** peut aussi faire la sauvegarde sans ligne de commande :

1. ouvrez **Paramètres > Sauvegardes** ;
2. cliquez sur **Créer une sauvegarde** ;
3. attendez la fin de l’animation de progression affichée pendant la préparation ;
4. téléchargez ensuite l’archive depuis la liste, ou configurez un lien `smb://...` puis utilisez **Copier vers SMB** pour l’envoyer vers un serveur Windows ou un NAS.

À savoir :

- l’interface archive la base applicative, les médias et les données privées ;
- une copie du `.env` est ajoutée à l’archive si elle est disponible ;
- seules les **5 sauvegardes les plus récentes** sont conservées automatiquement ; les plus anciennes sont supprimées lors d’une nouvelle création.

Pour restaurer sur une autre instance déjà démarrée :

1. connectez-vous en super-admin ;
2. ouvrez **Paramètres > Sauvegardes** ;
3. sélectionnez le fichier de sauvegarde ;
4. cliquez sur **Restaurer maintenant**.

> La restauration réinjecte les données de l'application, les médias et les données privées. Le fichier `.env` sauvegardé reste fourni comme copie de référence, mais n'est pas réécrit automatiquement par l'interface.

---

## 18. Campagnes temporaires

Accessible depuis **Campagnes temporaires** dans le menu.

Les campagnes permettent de prendre temporairement la main sur la rotation normale pour un événement, une période ou une urgence préparée à l'avance.

> **Permission requise :** `schedule` ou `toggle`

### Créer une campagne

1. Cliquez sur **Nouvelle campagne**.
2. Renseignez un nom, une période de début/fin si nécessaire, une priorité et les écrans ciblés.
3. Sélectionnez au moins un groupe ou un média dans la médiathèque intégrée.
4. Activez la campagne puis enregistrez.

### Priorité et diffusion

- Si plusieurs campagnes sont actives sur le même écran, celle avec la priorité la plus élevée prend le dessus.
- Une campagne peut cibler des groupes, des médias isolés, ou les deux.
- Les campagnes respectent les restrictions d'écrans de l'utilisateur connecté.
- Une campagne archivée ne peut pas être activée tant qu'elle n'est pas restaurée.

### Propriété des campagnes

Seul le **créateur de la campagne** (ou un super-admin) peut la modifier, l'activer/désactiver, l'archiver ou la supprimer. Le bouton **Dupliquer** reste accessible à tous les utilisateurs disposant des permissions requises.

### Actions disponibles

| Action | Description | Qui peut agir |
|---|---|---|
| **Modifier** | Met à jour les dates, la priorité, les écrans et les contenus ciblés. | Propriétaire ou super-admin |
| **Activer / Désactiver** | Bascule rapidement une campagne non archivée. | Propriétaire ou super-admin |
| **Dupliquer** | Crée une copie réutilisable pour un nouvel événement. | Tout utilisateur autorisé |
| **Archiver / Restaurer** | Retire une campagne de l'exploitation courante sans perdre sa configuration. | Propriétaire ou super-admin |
| **Supprimer** | Supprime définitivement la campagne. | Propriétaire ou super-admin |

Les actions de campagne sont enregistrées dans le **Journal d'activité** sous le type **Campagne**.

---

## 19. Recherche globale

La barre de recherche en haut de l'interface permet de retrouver rapidement n'importe quel contenu de l'administration.

### Accès rapide

- Cliquez sur la barre de recherche dans la topbar, ou appuyez sur **Cmd+K** (Mac) / **Ctrl+K** (Windows/Linux) depuis n'importe quelle page.
- Tapez au moins 2 caractères — les résultats apparaissent en temps réel dans un menu déroulant.
- Utilisez **↑ ↓** pour naviguer dans les résultats et **Entrée** pour ouvrir la sélection. **Échap** ferme le menu.

### Périmètre de la recherche

| Catégorie | Ce qui est recherché |
|---|---|
| **Pages** | Accès direct aux sections de l'administration |
| **Médias** | Nom de fichier dans la médiathèque |
| **Campagnes** | Nom de campagne |
| **Configuration** | Sections de paramétrage |
| **Utilisateurs** | Nom de compte (super-admin uniquement) |
| **Journal d'activité** | Dernières entrées correspondantes |

### Page de résultats complète

Le lien **Tous les résultats →** en bas du menu déroulant, ou la touche Entrée sans sélection, ouvre la page `/admin/search` avec l'ensemble des résultats groupés par catégorie.

---

*Documentation générée pour Visio-Display — Application d'affichage dynamique.*
