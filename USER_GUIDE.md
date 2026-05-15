<!-- Licensed under the GNU General Public License v3.0 (GPL-3.0). Copyright (c) 2026 Eric TOMAS (Woofix). See the LICENSE file for details. -->

# Visio-Display — User Guide

[🇺🇸 English](#english) · [🇫🇷 Français](#français)

---

## English

Visio-Display is a **digital signage** application that automatically rotates images, videos, and a weather/almanac card on one or more screens. It is managed from any browser through a web administration interface.

---

## Table of Contents

1. [Accessing the Application](#1-accessing-the-application)
2. [Public Display](#2-public-display)
3. [Signing in to Administration](#3-signing-in-to-administration)
4. [Adding Media](#4-adding-media)
5. [Managing the Media Library](#5-managing-the-media-library)
6. [Media Groups](#6-media-groups)
7. [Scheduling Media Display](#7-scheduling-media-display)
8. [Managing Multiple Screens](#8-managing-multiple-screens)
9. [The Almanac Card](#9-the-almanac-card)
10. [Personal Settings](#10-personal-settings)
11. [User Management (Super Admin)](#11-user-management-super-admin)
12. [Video Encoding Queue](#12-video-encoding-queue)
13. [Priority Alert (Super Admin)](#13-priority-alert-super-admin)
14. [Available Permissions](#14-available-permissions)
15. [Activity Log](#15-activity-log)
16. [Backing Up and Restoring the Server](#16-backing-up-and-restoring-the-server)
17. [Temporary Campaigns](#17-temporary-campaigns)
18. [Global Search](#18-global-search)
19. [Role Management (RBAC)](#19-role-management-rbac)
20. [Feature Management (Super Admin)](#20-feature-management-super-admin)
21. [Server Version (Super Admin)](#21-server-version-super-admin)
22. [About](#22-about)
23. [Built-in Announcement Editor](#23-built-in-announcement-editor)

---

## 1. Accessing the Application

| Use | Address |
|---|---|
| Public display (default screen) | `http://<server-address>:8081?screen_token=<token>` |
| Named screen display | `http://<server-address>:8081?screen=screen-name&screen_token=<token>` |
| Administration interface | `http://<server-address>:8081/admin` |

Replace `<server-address>` with the IP address or hostname of your server, for example `192.168.1.50` or `raspberrypi.local`.

---

## 2. Public Display

The public display page is designed to run full screen without user interaction.

- The **slideshow advances automatically**: each media item stays on screen for its configured duration (15 seconds by default), then fades into the next item.
- **Videos** play through completely, or until the configured maximum duration is reached.
- The **almanac card** (weather, sunrise/sunset, saint of the day, countdowns) is automatically inserted into the rotation.
- The media list **updates in real time**: changes made in administration take effect on the next slide change without reloading the page.
- A **screen selector** appears at the bottom of the page. It is semi-transparent when idle and fully visible on hover. Select a screen to switch directly without retyping the URL.

> **Usage tip:** On a Raspberry Pi, configure the browser in kiosk mode (`chromium-browser --kiosk 'http://localhost:8081?screen_token=<token>'`) for a full-screen display without browser chrome.

If you use the automated client installation from administration, select the screen from the list. Administration sends the client a display URL containing the `screen_token` and only adds the screen name when a named screen is configured.

### Good to Know

- A **disabled** media item or one **outside its broadcast window** does not appear on the public screen, even if it remains visible in administration.
- Each **named screen** has its own media selection, order, and rules.
- Public display changes become visible **without reloading** the page. Wait for the next transition.

---

## 3. Signing in to Administration

1. Open `http://<server-address>:8081/admin` in your browser.
2. Enter your **username** and **password**.
3. Select **Log in**.

The dashboard shows a summary: media count, disk space used/available, and quick links to the main sections.

To sign out, select your name in the upper-right corner, then **Log out**.

### After Sign-In

- The menus shown depend on your **permissions**. Some sections may be hidden if your account does not have access.
- The dashboard is mainly a **quick entry point**. Detailed management is handled in the media library, settings, and broadcast windows.

### Super Admin vs. User

| Profile | What they can do | Limits |
|---|---|---|
| **Super admin** | Access the entire application, all screens, all global settings, account management, backups, client installation, system features, and priority alerts. | The super-admin account cannot be deleted from the interface, and its permissions are protected differently from regular user permissions. |
| **User** | Access only the menus and actions matching permissions granted by the super admin. Users may also be limited to specific screens. | Cannot manage accounts, grant permissions, create/delete screens, restore the server, publish priority alerts, or modify super-admin-only settings. |

---

## 4. Adding Media

> **Required permission:** `upload`

1. In the navigation menu, go to **Upload**.
2. **Drag and drop** files into the upload area, or select the area to open the file picker.
3. You can upload **multiple files at once**.

### Supported Formats

| Type | Extensions |
|---|---|
| Images | `.jpg`, `.jpeg`, `.png` |
| Videos | `.mp4`, `.mov`, `.avi`, `.mkv`, `.webm` |
| Documents | `.pdf` (automatically converted to an image) |

### Automatic Video Encoding

Videos that are not already H.264/MP4 are **automatically re-encoded** in the background. During this process:

- A per-file progress bar shows the current progress.
- The media item becomes usable as soon as on-the-fly encoding is complete.
- Additional compression may be scheduled overnight (8 PM to 6 AM) to reduce disk usage.

After upload completes, the **View media** button takes you to the media library.

### Best Practices

- Use **clear file names**. They are reused in the media library, broadcast windows, and activity log.
- After upload, check the **display duration**, **enabled state**, and **target screen** in the media library.
- **PDFs** are handled as visual content. If rendering is not suitable, preparing an exported image at the correct format is often better.

---

## 5. Managing the Media Library

> **Required permissions depend on the action:** `toggle`, `reorder`, `duration`, `delete`

Open **Media** from the menu.

### Overview

Each media item shows:

- Its **thumbnail preview** or a video icon
- Its **file name**, size, and dimensions for images
- Its **status**: enabled or disabled
- Its custom **display duration**, if set
- Its **scheduling rules**, if set

### Available Actions

| Action | Description |
|---|---|
| **Enable / Disable** | A disabled media item stays in the library but does not appear in the slideshow. |
| **Edit duration** | Set how many seconds this media item should be displayed. Leave empty to use the default value (15 seconds). |
| **Schedule** | Restrict display to specific times or dates. |
| **Preview** | Opens the media item full screen for review. |
| **Delete** | Permanently deletes the file. |

### Reordering

Drag media items to change the slideshow order. The order is **specific to each screen**.

### Assigning Media to a Screen

Unassigned media appears in a separate section at the bottom of the page. Select **Add to screen** to include it on the currently selected screen.

### Reading the Library

- **Search** and **filters** help isolate active media, disabled media, or a specific file type.
- Badges on a card can indicate a disabled media item, saved broadcast window, or disabled group.
- The view depends on the **selected screen**. Always check the screen tab before changing order or assignments.
- On mobile, **Tile** view prioritizes large previews, while **List** view becomes compact with a thumbnail on the left and details/actions on the right.

---

## 6. Media Groups

> **Required permission:** `toggle`

Groups, or tags, organize media by topic and let you enable or disable a set of media items with one action.

### Assigning Groups to Media

1. In the media library, open the **Actions** menu for the media item.
2. Enter group names separated by commas, for example `menu`, `info`, `alerts`.
3. Select **Save groups**.

A media item can belong to multiple groups at the same time.

### Enabling or Disabling a Group

The **Groups** section in the media library sidebar lists all defined groups. Select **Enable group** or **Disable group** to toggle every media item in that group at once.

A **GROUP DISABLED** badge appears on affected media items in the grid.

The **Media Library** menu item does not show a media count.

> **Note:** A media item disabled individually remains disabled even if its group is enabled.

### Linking a Group to Screens

By default, a group is **global**: it appears in the group bar no matter which screen is selected.

You can restrict a group to one or more specific screens:

1. In the **Groups** panel at the top of the media library, find the group.
2. Select the link icon at the end of the chip to open the screen selector.
3. Select the screens this group should be linked to. Active buttons are highlighted. **Default** represents the screen without a `?screen=` parameter.
4. The link is saved immediately. The group will only appear on the selected screens.

> **Note:** If no screen is selected, the group becomes global again and is visible on every screen.

### Random Group Pool

For each group, you can set how many media items from that group should appear during one slideshow cycle.

- `0` or an empty value means **show all media** in the group.
- A positive number limits the group to that many items per cycle.
- This is useful for large groups where you want variety without showing every item every time.

---

## 7. Scheduling Media Display

> **Required permission:** `schedule`

Scheduling displays a media item only during a defined **time window** or **date range**. Both conditions can be combined.

The **Broadcast Windows** page also provides a **weekly calendar**. Day names follow the selected interface language.

### Configuring a Schedule

1. In the media library, select the schedule icon for the media item.
2. Fill in the desired fields:

| Field | Format | Example |
|---|---|---|
| Start time | HH:MM | `11:00` |
| End time | HH:MM | `13:30` |
| Start date | YYYY-MM-DD | `2026-06-02` |
| End date | YYYY-MM-DD | `2026-06-15` |

3. Select **Save**. The rule takes effect on the next slide change.

### How Rules Are Interpreted

- If you only enter **times**, the media item reappears **every day** during that time window, with no end date.
- If you only enter **dates**, the media item remains visible **all day** between those dates, inclusive.
- If you combine **dates and times**, both conditions must be true at the same time.
- If you leave **all fields empty**, the restriction is removed and the media item becomes continuously visible again.
- Scheduling applies to the media item on the **current screen**. The same file can therefore have different rules per screen.

### Reading the Broadcast Windows Page

- The list summarizes each saved rule with its screen, media item, groups, and active range.
- The weekly calendar shows planned windows day by day, making gaps and overlaps easier to spot.
- Day names follow the interface language.

> **Example:** For a cafeteria menu visible only from 11 AM to 1 PM, Monday through Friday, configure `11:00` to `13:00` as the time window. Display stops and resumes automatically.

To delete a schedule, clear the fields and save.

---

## 8. Managing Multiple Screens

Visio-Display can create **independent named screens**, each with its own media list, order, and rules.

### Creating a Screen

> **Required right:** super admin

1. Open **Settings > Screen Management**.
2. Enter a name using lowercase letters, numbers, `-`, and `_` only, from 1 to 32 characters.
3. Select **Create**.

Reserved names that cannot be used: `default`, `admin`, `api`, `static`, `login`, `logout`.

### Accessing a Screen

- **Public display:** `http://<server>:8081?screen=screen-name&screen_token=<token>`. The screen selector at the bottom keeps the token when switching screens.
- **Media library:** select the screen using the tabs at the top. The **Preview** button opens a preview window for the active screen.
- **Dashboard:** the **Preview** card offers one button per screen to open the matching slideshow in a new tab.

### Per-Screen Behavior

- Each screen manages media order, enabled state, duration, and schedule **independently**.
- The same file can be **assigned to multiple screens**.
- Users can be **restricted to specific screens**.
- The super admin can customize the **display name of the default screen** and the **halo color** used around media while playing.

> **Tip:** When installing a display client from administration, use the provided screen selection. The final URL already includes the required display token.

### Broadcasting a Screen List

From the media library, an authorized user can broadcast the current screen list to other accessible screens.

- The broadcast copies media order, enabled/disabled states, disabled groups, durations, and schedules.
- Later changes on the source screen are propagated while the broadcast link remains active.
- Use **Stop broadcast** when the target screens should become independent again.

### Installing a Display Client

From **Settings > Client Installation**:

1. Enter the client host or IP address, SSH port, SSH user, and local user to configure.
2. Enter the remote account **SSH password** (required and needs `sshpass` installed on the server).
3. Enter the **admin / sudo password** if different from the SSH password, or leave it blank to reuse it.
4. Enter the **server base URL** (for example `https://visio.example.com`), not a hard-coded per-screen URL.
5. Enter the **screen name** if the workstation should open a named screen, for example `reception` or `kitchen`.
6. Enter the client machine name.
7. Start the installation.

The script configures auto-login, kiosk mode, Linux hostname, sleep prevention during display, and client heartbeat reporting back to the server.

### Detected Clients

In **Settings > Client Installation**, the **Detected clients** area updates automatically. New installations report their IP address, machine name, and screen about every 30 seconds.

### Remote Client Control

> **Required right:** super admin

From **Settings > Client Installation**, the **Client control** area lets you act directly on a known workstation:

- Choose the host from the detected clients list. This form does not accept a manually typed IP address.
- **Shut down client** sends an immediate shutdown command.
- **Restart client** sends an immediate reboot command.
- **Reinstall client** reruns the workstation installation script.
- **Update Debian** runs the workstation system update.

> **Warning:** Reinstalling the client is not a simple system update. It reruns the display client installation procedure.

### Kiosk Watchdog

The super admin can configure the monitoring policy sent to installed clients:

- the interval between checks;
- the grace period after startup;
- the number of consecutive failures before automatic restart.

This policy helps a kiosk client return to service automatically if the display browser stops working for a sustained period.

---

## 9. The Almanac Card

The almanac card is an automatically generated image that is inserted into the slideshow rotation.

### Displayed Content

- **Saint of the day**
- **Current weather**: temperature, feels-like temperature, wind speed, precipitation
- **Sunrise and sunset**
- Custom **dated events**, for example *Summer break: 42 days*

### Updates

- The card is **regenerated every 2 hours** and automatically at midnight.
- If the almanac file is missing, it is **automatically regenerated** on the next slideshow refresh.
- When the card is created or updated, it appears in the slideshow without reloading the page.

### Managing Dated Events

> **Required access:** super admin

Only **upcoming events** are shown on the card. The label entered in settings is reused as-is.

In **Settings > Events**:

1. Select **Add event**.
2. Enter a label, for example `Final exams`, and the target date in `YYYY-MM-DD` format.
3. Select **Save**.

The countdown appears on the card after the next regeneration. Select the trash icon to delete an event.

---

## 10. Personal Settings

Open **Settings** from the menu.

### Interface Theme

Choose one of three visual themes for your session:

- **Purple** (default)
- **Dark**
- **Blue**

This setting is **personal** and does not change the display for other users.

On mobile, the interface automatically adapts to the theme selected for your session. There is no separate mobile theme to choose.

Navigation also adapts to screen width: on desktop, the sidebar remains visible; on mobile only, a menu button opens or closes navigation.

### Interface Language

Choose between **French (FR)** and **English (EN)**.

The selected language changes the **administration labels** and the **built-in wiki**. It does not affect the media files themselves.

### Weather Location (Super Admin)

From **Settings > Weather**, the super admin can change the location used for the almanac card:

| Field | Example | Description |
|---|---|---|
| City | `Montpellier` | City name displayed on the almanac card |
| Latitude | `43.6119` | GPS coordinate (decimal, between -90 and 90) |
| Longitude | `3.8772` | GPS coordinate (decimal, between -180 and 180) |
| Time zone | `Europe/Paris` | IANA identifier |
| School zone | `A` / `B` / `C` | French national education zone, auto-detected if left empty |

A city-name search field with Open-Meteo autocomplete fills coordinates and time zone automatically. Select **Save** to apply the new location and regenerate the card immediately.

### Changing Your Password

1. In **Settings > Admins**, scroll to **Change password**.
2. Enter your current password, then the new one (minimum 10 characters).
3. Select **Save**.

---

## 11. User Management (Super Admin)

Open **Settings > Users**.

The **Users** menu item does not show an account count.

> **Super admin only:** only the super admin can create accounts, delete user accounts, modify permissions, and limit users to specific screens.

### Creating an Account

1. Select **Add account**.
2. Enter a username and password (minimum 10 characters).
3. Select **Create**.

The account is created **without permissions**. Assign the required rights afterward.

### Assigning Permissions

In the user list, select a user to modify permissions. Check or uncheck each permission individually.

A user **without permissions** can sign in, but only sees the sections allowed by their profile.

### Restricting Screen Access

In a user profile, under **Allowed screens**:

- **No boxes checked** means the user can manage all screens.
- **Boxes checked** means the user only sees and manages selected screens.

### Resetting a Password

Select **Reset password** in the user profile and enter the new password.

The **super-admin** password cannot be reset from the interface. If it is lost, use the local maintenance script from the server. With Docker Compose, run it from the project root with `docker compose exec app python3 /app/tools/reset_superadmin_password.py`. The script only replaces the PostgreSQL hash, forces a password change on next login, and writes an activity log entry.

### Deleting an Account

Select **Delete** in the user profile. The super-admin account cannot be deleted.

---

## 12. Video Encoding Queue

Open **Encoding Queue** from the menu.

### Automatic Encoding Window

By default, video compression is scheduled overnight between **8 PM and 6 AM** to reduce performance impact.

### Task Monitoring

- **Current jobs:** lists active compressions with their progress percentage.
- **Recent jobs:** shows completed compressions with statistics such as before/after size and compression rate.

### Forcing Encoding (Super Admin)

- **Force all:** immediately starts all pending compression jobs outside the overnight window.
- **Force file:** in the media library, select the compression icon for a specific media item.

### Canceling a Task

Users with the `compress` permission can cancel a **pending** task before it starts from the encoding queue.

> **Note:** Encoding mainly improves compatibility and reduces video disk usage. It is usually not useful for an image or PDF.

---

## 13. Priority Alert (Super Admin)

> **Required right:** super admin

The priority alert immediately displays a banner message on the display screen without interrupting the slideshow.

### Usage

1. Open **Settings > Priority Alert**.
2. Enter your message in the field provided (maximum 280 characters).
3. The banner is published **automatically** after each keystroke. No button is required.
4. To remove the banner, select **Clear banner**.

> **Warning:** The banner remains visible on **all screens** until it is manually removed, regardless of the `?screen=` parameter.

---

## 14. Available Permissions

| Permission | Authorized actions |
|---|---|
| `upload` | Upload media |
| `delete` | Delete media |
| `reorder` | Change media order |
| `toggle` | Enable/disable media and groups, assign to a screen |
| `duration` | Change display duration |
| `compress` | Queue encoding, cancel a task |
| `logo` | Change or reset the application logo |
| `schedule` | Define time and date schedules |

### Roles and Limits

| Account type | Can do | Cannot do |
|---|---|---|
| **Super admin** | Everything permissions allow, plus global administration actions: users, screens, backups, weather, client installation, features, priority alert, and forced encoding. | The account and its permissions are protected in the current interface. |
| **User** | Only actions covered by assigned permissions, and only on allowed screens if restrictions are configured. | Create/delete accounts, grant permissions, create/delete screens, restore the server, publish priority alerts, or modify reserved global settings. |

The super admin has **all permissions** and can additionally create/delete accounts, create/delete screens, customize the application name, configure weather location, publish a priority alert, and force encoding outside the overnight window.

Permissions can be **freely combined**. Grant only the rights needed for the user's task.

---

## 15. Activity Log

Open **Activity Log** from the navigation menu.

The log is an **operations history**: it helps quickly verify who did what before assuming a malfunction.

It records actions performed by signed-in users and some automatic system operations.

On mobile, log entries are displayed as stacked cards to avoid horizontal table overflow.

Sensitive administration operations use an authenticated session protected by a secure server-side cookie, CSRF protection on forms and write calls, and sign-out confirmed by a protected `POST` action.

### Recorded Actions

| Action | Description |
|---|---|
| **Upload** | File upload (image, video, or PDF), including user and file |
| **Deletion** | Permanent file deletion |
| **Login** | Session start |
| **Logout** | Session end through a secured action |
| **Activation** | Media or group enable/disable action, including resulting state (`enabled` / `disabled`) and screen |
| **Compression** | Automatic video compression start and result (before/after size, reduction rate), performed by `system` |
| **Configuration** | Administration changes: durations, media order, broadcast windows, groups, screens, logo, theme, language, weather, users, permissions, priority alert, and more |
| **Campaign** | Campaign creation, update, duplication, enable/disable, and archival |

### Available Filters

- **Free search** by file name, user, or details
- **Action type**: Upload, Deletion, Login, Logout, Activation, Compression, Configuration, Campaign
- **User**

### Retention and Disk Space

The log is **automatically purged** to prevent unbounded PostgreSQL growth:

- entries older than the retention period are deleted automatically;
- a maximum row count is enforced even when activity is high;
- retention rules can be applied immediately from administration.

Defaults:

- **retention:** `90` days;
- **maximum size:** `20000` entries;
- **cleanup frequency:** `1` hour.

These values can be adjusted with `ACTIVITY_LOG_RETENTION_DAYS`, `ACTIVITY_LOG_MAX_ROWS`, and `ACTIVITY_LOG_CLEANUP_INTERVAL_SECONDS`. The super admin can also change retention, row limit, purge old entries, or clear the log from **Activity Log**.

> **Note:** Automatic overnight video compressions are recorded under the `system` user. Configuration operations appear with the **Configuration** action, and campaign operations with the **Campaign** action.

---

## 16. Backing Up and Restoring the Server

If you need to recreate the server on another machine or start again with a new Docker stack, use the scripts provided at the project root.

### Creating a Backup

From the project directory:

```bash
scripts/docker_backup.sh
```

The script creates a folder in `backups/` containing:

- `postgres.dump`: the PostgreSQL database
- `media.tar.gz`: uploaded media
- `private.tar.gz`: private application data
- `env.backup`: a copy of `.env`, if present

You can also choose the destination folder:

```bash
scripts/docker_backup.sh /path/to/visio-backup
```

### Restoring an Identical Instance

1. Copy the project and backup folder to the new machine.
2. Move into the project directory.
3. Run:

```bash
scripts/docker_restore.sh backups/visio-backup-YYYYMMDD-HHMMSS
```

The restore:

- temporarily stops the application;
- starts PostgreSQL and Redis;
- restores media and private data;
- restores the PostgreSQL database;
- restarts the full stack.

To also reapply the saved `.env` even if one already exists:

```bash
scripts/docker_restore.sh --force-env backups/visio-backup-YYYYMMDD-HHMMSS
```

> Tip: run backups when no large upload or video processing job is in progress so the snapshot is clean.

### Backup from Administration

The **super admin** can also create backups without using the command line:

1. Open **Settings > Backups**.
2. Select **Create backup**.
3. Wait for the progress animation to finish.
4. Download the archive from the list, or configure an `smb://...` link and use **Copy to SMB** to send it to a Windows server or NAS.

Notes:

- the interface archives the application database, media, and private data;
- a copy of `.env` is included in the archive when available;
- only the **5 most recent backups** are kept automatically. Older backups are deleted when a new one is created.

To restore to another already-running instance:

1. Sign in as super admin.
2. Open **Settings > Backups**.
3. Select the backup file.
4. Select **Restore now**.

> Restore reinjects application data, media, and private data. The saved `.env` remains included as a reference copy, but the interface does not automatically rewrite it.

---

## 17. Temporary Campaigns

Open **Temporary Campaigns** from the menu.

Campaigns temporarily take over the normal rotation for an event, time period, or prepared emergency.

> **Required permission:** `schedule` or `toggle`

### Creating a Campaign

1. Select **New campaign**.
2. Enter a name, optional start/end period, priority, and target screens.
3. Select at least one group or media item in the embedded media library.
4. Enable the campaign and save.

### Priority and Broadcast

- If multiple campaigns are active on the same screen, the one with the highest priority takes over.
- A campaign can target groups, individual media items, or both.
- Campaigns respect the signed-in user's screen restrictions.
- An archived campaign cannot be enabled until it is restored.
- On mobile, target screens are displayed as full-width rows with the full screen name, and target media uses larger thumbnails.

### Campaign Ownership

Only the **campaign creator** or a super admin can modify, enable/disable, archive, or delete a campaign. The **Duplicate** button remains available to all users with the required permissions.

### Available Actions

| Action | Description | Who can act |
|---|---|---|
| **Edit** | Updates dates, priority, screens, and targeted content. | Owner or super admin |
| **Enable / Disable** | Quickly toggles a non-archived campaign. | Owner or super admin |
| **Duplicate** | Creates a reusable copy for a new event. | Any authorized user |
| **Archive / Restore** | Removes a campaign from daily operation without losing its configuration. | Owner or super admin |
| **Delete** | Permanently deletes the campaign. | Owner or super admin |

Campaign actions are recorded in the **Activity Log** under **Campaign**.

---

## 18. Global Search

The search bar at the top of the interface helps quickly find administration content.

### Quick Access

- Select the search bar in the topbar, or press **Cmd+K** (Mac) / **Ctrl+K** (Windows/Linux) from any page.
- Type at least 2 characters. Results appear in real time in a dropdown menu.
- Use **↑ ↓** to move through results and **Enter** to open the selected item. **Esc** closes the menu.
- On mobile, search remains available in the topbar as a full-width field below the title.

### Search Scope

| Category | What is searched |
|---|---|
| **Pages** | Direct access to administration sections |
| **Media** | File names in the media library |
| **Campaigns** | Campaign names |
| **Configuration** | Settings sections |
| **Users** | Account names (super admin only) |
| **Activity Log** | Recent matching entries |

### Full Results Page

The **All results →** link at the bottom of the dropdown, or pressing Enter without a selection, opens `/admin/search` with all results grouped by category.

---

## 19. Role Management (RBAC)

Open **Administration > Roles** from the menu.

> **Super admin only.**

Roles group permissions under a reusable name and can then be assigned to one or more users. A user's effective permissions are the **union** of all assigned role permissions.

### Predefined Roles

Three roles are created automatically on first startup:

| Role | Included permissions |
|---|---|
| **Administrator** | All available permissions |
| **Editor** | `upload`, `delete`, `reorder`, `toggle`, `duration` |
| **Reader** | None (dashboard access only) |

The **Administrator** role is a *system* role and cannot be deleted.

### Creating a Role

1. On the **Roles** page, enter an identifier using lowercase letters, numbers, `-`, and `_` (2 to 64 characters), a display name, and an optional description.
2. Check the permissions to include.
3. Select **Create role**.

### Editing a Role

Select **Edit** to change the display name and description. Permissions are modified separately using the dedicated form on the same page.

### Deleting a Role

Select **Delete**. A system role cannot be deleted. Deleting a role automatically removes it from all affected users.

### Assigning Roles to a User

In **Role assignment**, check the desired roles for each user and save. Changes take effect on the user's next action.

> **Note:** Direct permissions assigned account by account and permissions inherited from roles are cumulative.

---

## 20. Feature Management (Super Admin)

Open **Settings > Features** from the navigation menu.

> **Super admin only.**

This page enables or disables whole application modules. A disabled module hides its menus, buttons, and API endpoints for **all users**, including the super admin.

### Available Modules

| Module | What it controls |
|---|---|
| **Media upload** | Uploading image and PDF files, and videos when the Videos module is active |
| **Videos** | Video upload, previews, display, and encoding. Disabling it hides all existing videos |
| **Media deletion** | Permanent deletion of files from the media library |
| **Video compression** | Encoding queue and compression of videos limited to 1080p |
| **Almanac** | Generation and display of the daily almanac card |
| **Campaigns** | Creation and management of temporary campaigns |
| **Broadcast windows** | Time and date schedule configuration per media item |
| **Media groups** | Media organization into groups and collective enable/disable |
| **Multi-screen** | Creation and management of independent named screens |
| **Priority alert** | Real-time critical alert banner on all screens |
| **Activity log** | Recording and viewing user action history |

### Enabling or Disabling a Module

Select the toggle next to the module. The change is immediate and does not require a restart.

> **Tip:** Disable a module only when you are sure it is not needed. Re-enabling restores access to the module as it was before being disabled.

---

## 21. Server Version (Super Admin)

Open **Settings > Version** from the navigation menu.

> **Super admin only.**

This page compares the installed version with the remote version published on GitHub and can apply a server update when the local installation is compatible.

### Checking Version Status

1. Open **Settings > Version**.
2. Select **Check** to query the remote repository.
3. Review the displayed status:
   - **Up to date:** the installed version matches the known remote version.
   - **Update available:** a newer version was detected.
   - **Restart required:** the update was applied and Docker must be restarted.
   - **Incompatible installation:** a prerequisite is missing or the local state prevents the action.
   - **Check unavailable:** the remote source could not be reached or versions could not be compared.

### Displayed Information

| Area | Description |
|---|---|
| **Installed version** | Version read from the `VERSION` file or `APP_VERSION` environment variable |
| **Remote version** | Published version read from GitHub |
| **Current / target branch** | Local Git branch and branch used for the update |
| **Git state** | Must be clean to apply an update |
| **Commits** | Short IDs of local and remote commits |

### Applying an Update

When the status is **Update available**, select **Apply**, confirm the action, and follow the log displayed on the page.

The update:

- uses the already-installed Git repository without recloning the application;
- refuses to continue if local changes are present;
- checks the remote, target branch, `scripts/update.sh`, and Docker Compose;
- switches to or pulls the configured target branch, then prepares the application code.

After applying the update, select **Restart Docker** to relaunch the stack with the new version.

During an update or restart, administration displays a **blocking overlay**. It prevents clicks, forms, and shortcuts until the operation finishes. If the server restarts and responds more slowly for a moment, the page shows automatic reconnection.

### Best Practices

- Run a backup before a major update.
- Avoid updating during a large upload or restore.
- If the check fails, verify the server's network access, local Git state, and Docker Compose availability.

---

## 22. About

Open **About** from the navigation menu. It is available to all signed-in users.

The **About** page displays technical information for the running instance:

- application **version**, read from the `VERSION` file or `APP_VERSION` environment variable;
- deployment **Git commit**, when available;
- **technical stack**: backend, database, deployment;
- **license** link to the project's `LICENSE` file.

This information is useful when identifying the installed version for support or updates.

---

## 23. Built-in Announcement Editor

Open **Announcements** from the navigation menu, then create or edit an announcement.

The integrated editor creates 16:9 graphic announcements directly in Visio-Display. The canvas sits at the center of the workspace, with a grouped creation toolbar on the left and a contextual properties panel on the right.

### Creation Tools

- **Text** adds editable typography layers.
- **Shapes** and **lines** add simple graphic structure.
- **Image** opens the **Background** panel directly, showing image upload, media library, external bank and background color without extra clicks.
- **Icons** insert pictograms from Lucide Icons, Tabler Icons and local SVG files.

### Positioning and Layers

Use the visual grid and snap mode to align objects. The layer system lets you select, reorder, hide and delete objects, while the compact layer list keeps the canvas area readable.

The right panel changes with the current context:

- no selection: document settings, export and background controls;
- text selected: typography options;
- image selected: image controls;
- any selected object: position, size and layer order.

### Export and Broadcast

Use **Export PNG** to render the announcement as a 16:9 image and add it to the media library. Then configure its target screens and display duration like any other media item.

### Icon Sources

The editor uses Lucide Icons, Tabler Icons and local SVG assets:

```text
web/static/assets/lucide/
web/static/assets/tabler/outline/
web/static/assets/tabler/filled/
```

---

*Documentation generated for Visio-Display — Digital signage application.*

---

## Français

### Guide utilisateur — Visio-Display

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
16. [Sauvegarder et restaurer le serveur](#16-sauvegarder-et-restaurer-le-serveur)
17. [Campagnes temporaires](#17-campagnes-temporaires)
18. [Recherche globale](#18-recherche-globale)
19. [Gestion des rôles (RBAC)](#19-gestion-des-rôles-rbac)
20. [Gestion des fonctionnalités (super-admin)](#20-gestion-des-fonctionnalités-super-admin)
21. [Version (super-admin)](#21-version-super-admin)
22. [À propos](#22-à-propos)
23. [Éditeur d'annonces intégré](#23-éditeur-dannonces-intégré)

---

## 1. Accéder à l'application

| Usage | Adresse |
|---|---|
| Affichage public (écran par défaut) | `http://<adresse-du-serveur>:8081?screen_token=<jeton>` |
| Affichage d'un écran nommé | `http://<adresse-du-serveur>:8081?screen=nom-ecran&screen_token=<jeton>` |
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

> **Conseil d'utilisation** : Sur un Raspberry Pi, configurez le navigateur en mode kiosk (`chromium-browser --kiosk 'http://localhost:8081?screen_token=<jeton>'`) pour un affichage plein écran sans barre de navigation.

Si vous utilisez l'installation client automatique depuis l'administration, choisissez l'écran dans la liste. L'administration transmet au client une URL d'affichage contenant le jeton `screen_token` et ajoute le nom d'écran uniquement quand un écran nommé est configuré.

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
- Sur cellulaire, la vue **Vignettes** privilégie les grands aperçus, tandis que la vue **Liste** devient compacte avec miniature à gauche, informations et actions à droite.

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

### Tirage aléatoire par groupe

Pour chaque groupe, vous pouvez définir combien de médias de ce groupe apparaissent pendant un passage du diaporama.

- `0` ou une valeur vide signifie **afficher tous les médias** du groupe.
- Une valeur positive limite le groupe à ce nombre de médias par passage.
- C'est utile pour les grands groupes, quand on veut varier les contenus sans tout afficher à chaque cycle.

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

1. Ouvrez **Paramètres > Gestion des écrans**.
2. Saisissez un nom (lettres minuscules, chiffres, `-` et `_` ; entre 1 et 32 caractères).
3. Cliquez sur **Créer**.

Noms réservés (interdits) : `default`, `admin`, `api`, `static`, `login`, `logout`.

### Accéder à un écran

- **Affichage public :** `http://<serveur>:8081?screen=nom-ecran&screen_token=<jeton>` — le sélecteur d'écran en bas de la page conserve aussi le jeton en basculant d'un écran à l'autre.
- **Médiathèque :** sélectionnez l'écran via les onglets en haut ; le bouton **Prévisualiser** (à droite de la barre) ouvre une fenêtre d'aperçu de l'écran actif.
- **Tableau de bord :** la carte **Prévisualiser** propose un bouton par écran pour ouvrir le diaporama correspondant dans un nouvel onglet.

### Fonctionnement par écran

- Chaque écran gère **indépendamment** l'ordre, l'activation, la durée et la planification de chaque média.
- Un même fichier peut être **assigné à plusieurs écrans simultanément**.
- Les utilisateurs peuvent être **restreints à certains écrans** (voir section 11).
- Le super-admin peut personnaliser le **nom affiché de l'écran par défaut** et la **couleur de halo** utilisée autour des médias pendant la lecture.

> **Conseil :** lors de l'installation d'un client d'affichage depuis l'administration, utilisez la sélection d'écran proposée : l'URL finale contient déjà le jeton d'affichage requis.

### Diffuser une liste d'écran

Depuis la médiathèque, un utilisateur autorisé peut diffuser la liste de l'écran courant vers d'autres écrans accessibles.

- La diffusion copie l'ordre des médias, les activations/désactivations, les groupes désactivés, les durées et les planifications.
- Les changements ultérieurs sur l'écran source sont propagés tant que le lien de diffusion reste actif.
- Utilisez **Arrêter la diffusion** quand les écrans cibles doivent redevenir indépendants.

### Installer un client d'affichage

Depuis **Paramètres > Installation client** :

1. Renseignez l'hôte ou l'IP du poste client, le port SSH, l'utilisateur SSH et l'utilisateur local à configurer.
2. Saisissez le **mot de passe SSH** du compte distant (obligatoire — nécessite `sshpass` installé sur le serveur).
3. Saisissez le **mot de passe admin / sudo** si différent du mot de passe SSH (laissez vide pour le réutiliser).
4. Saisissez l'**URL de base du serveur** (ex. `https://visio.example.com`), pas une URL écrite en dur par écran.
5. Renseignez le **nom d'écran** si le poste doit ouvrir un écran nommé (ex. `reception`, `cuisine`).
6. Renseignez le **nom de la machine** cliente.
7. Lancez l'installation.

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

> **Accès requis :** super-admin

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

Sur cellulaire, l'interface s'adapte automatiquement au thème choisi pour votre session : Violet, Sombre ou Bleu. Il n'y a pas de thème mobile séparé à sélectionner.

La navigation s'adapte aussi à la largeur d'écran : sur ordinateur, le menu latéral reste affiché directement ; sur cellulaire seulement, un bouton de menu permet d'ouvrir ou fermer la navigation.

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

Le mot de passe du **super-admin** ne se réinitialise pas depuis l'interface. En cas de perte, utilisez le script local de maintenance depuis le serveur (voir le `README.md` pour la procédure). Avec Docker Compose, lancez-le depuis la racine du projet avec `docker compose exec app python3 /app/tools/reset_superadmin_password.py`. Le script remplace uniquement le hash PostgreSQL, force le changement du mot de passe au prochain login et écrit une trace dans le journal d'activité.

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

1. Ouvrez **Paramètres > Alerte prioritaire**.
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

Sur cellulaire, les entrées du journal sont affichées sous forme de cartes verticales afin d'éviter le débordement horizontal des tableaux.

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

Le journal est **purgé automatiquement** pour éviter une croissance infinie de la base PostgreSQL :

- les entrées trop anciennes sont supprimées automatiquement ;
- un plafond de lignes est appliqué même si l'activité est très importante ;
- les règles de rétention peuvent être appliquées immédiatement depuis l'administration.

Par défaut :

- **conservation** : `90` jours ;
- **taille maximale** : `20000` entrées ;
- **fréquence de purge** : `1` heure ;

Ces valeurs peuvent être ajustées via les variables d'environnement `ACTIVITY_LOG_RETENTION_DAYS`, `ACTIVITY_LOG_MAX_ROWS` et `ACTIVITY_LOG_CLEANUP_INTERVAL_SECONDS`.
Le super-admin peut aussi modifier la conservation, le plafond de lignes, purger les entrées anciennes ou vider le journal depuis la page **Journal d'activité**.

> **Note :** Les compressions vidéo automatiques (planifiées la nuit) sont enregistrées sous l'utilisateur `system`. Les opérations de configuration apparaissent avec l'action **Configuration** et les opérations de campagnes avec l'action **Campagne**.

---

## 16. Sauvegarder et restaurer le serveur

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

## 17. Campagnes temporaires

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
- Sur cellulaire, les écrans ciblés sont affichés en lignes pleine largeur avec le nom complet de l'écran, et les médias ciblés utilisent des vignettes agrandies.

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

## 18. Recherche globale

La barre de recherche en haut de l'interface permet de retrouver rapidement n'importe quel contenu de l'administration.

### Accès rapide

- Cliquez sur la barre de recherche dans la topbar, ou appuyez sur **Cmd+K** (Mac) / **Ctrl+K** (Windows/Linux) depuis n'importe quelle page.
- Tapez au moins 2 caractères — les résultats apparaissent en temps réel dans un menu déroulant.
- Utilisez **↑ ↓** pour naviguer dans les résultats et **Entrée** pour ouvrir la sélection. **Échap** ferme le menu.
- Sur cellulaire, la recherche reste accessible dans la topbar sous forme de champ pleine largeur sous le titre.

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

## 19. Gestion des rôles (RBAC)

Accessible depuis **Administration → Rôles** dans le menu.

> **Réservé au super-admin.**

Les rôles permettent de regrouper un ensemble de permissions sous un nom réutilisable, puis d'attribuer ce rôle à un ou plusieurs utilisateurs. Les permissions effectives d'un utilisateur sont l'**union** des permissions de tous ses rôles.

### Rôles prédéfinis

Trois rôles sont créés automatiquement au premier démarrage :

| Rôle | Permissions incluses |
|---|---|
| **Administrateur** | Toutes les permissions disponibles |
| **Éditeur** | `upload`, `delete`, `reorder`, `toggle`, `duration` |
| **Lecteur** | Aucune (accès tableau de bord uniquement) |

Le rôle **Administrateur** est un rôle *système* : il ne peut pas être supprimé.

### Créer un rôle

1. Dans la page **Rôles**, renseignez un identifiant (lettres minuscules, chiffres, `-` et `_`, 2–64 caractères), un nom affiché et une description facultative.
2. Cochez les permissions à inclure.
3. Cliquez sur **Créer le rôle**.

### Modifier un rôle

Cliquez sur **Modifier** pour changer le nom affiché et la description. Les permissions se modifient séparément via le formulaire dédié sur la même page.

### Supprimer un rôle

Cliquez sur **Supprimer**. Un rôle système ne peut pas être supprimé. Supprimer un rôle retire automatiquement son attribution à tous les utilisateurs concernés.

### Attribuer des rôles à un utilisateur

Dans la section **Attribution des rôles** de la page, cochez les rôles souhaités pour chaque utilisateur et enregistrez. Les modifications prennent effet immédiatement à la prochaine action de l'utilisateur.

> **Remarque :** les permissions directes (attribuées compte par compte dans la section Utilisateurs) et les permissions issues des rôles se cumulent.

---

## 20. Gestion des fonctionnalités (super-admin)

Accessible depuis **Paramètres → Fonctionnalités** dans le menu de navigation.

> **Réservé au super-admin.**

Cette page permet d'activer ou de désactiver des modules entiers de l'application. Un module désactivé masque entièrement ses menus, ses boutons et ses points d'API pour **tous les utilisateurs**, y compris le super-admin.

### Modules disponibles

| Module | Ce qu'il contrôle |
|---|---|
| **Importation de médias** | Upload de fichiers images et PDF (et vidéos si le module Vidéos est actif) |
| **Vidéos** | Upload, aperçus, affichage et encodage de vidéos — désactiver masque toutes les vidéos existantes |
| **Suppression de médias** | Suppression définitive de fichiers de la médiathèque |
| **Compression vidéo** | File d'encodage et compression des vidéos limitées au 1080p |
| **Éphéméride** | Génération et affichage de la carte éphéméride quotidienne |
| **Campagnes** | Création et gestion des campagnes temporaires |
| **Plage de diffusion** | Configuration des plages horaires et dates de diffusion par média |
| **Groupes de médias** | Organisation des médias en groupes et activation/désactivation collective |
| **Multi-écrans** | Création et gestion d'écrans nommés indépendants |
| **Alerte prioritaire** | Bannière d'alerte critique sur tous les écrans en temps réel |
| **Journal d'activité** | Enregistrement et consultation du journal des actions utilisateurs |

### Activer / désactiver un module

Cliquez sur le bouton bascule en regard du module concerné. Le changement est immédiat et ne nécessite pas de redémarrage.

> **Conseil :** désactivez un module uniquement si vous êtes sûr de ne pas en avoir besoin. La réactivation restaure l'accès au module tel qu'il était avant la désactivation.

---

## 21. Version (super-admin)

Accessible depuis **Paramètres → Version** dans le menu de navigation.

> **Réservé au super-admin.**

Cette page compare la version installée avec la version distante publiée sur GitHub et permet d'appliquer une mise à jour serveur quand l'installation locale est compatible.

### Vérifier l'état de version

1. Ouvrez **Paramètres → Version**.
2. Cliquez sur **Vérifier** pour interroger le dépôt distant.
3. Consultez le statut affiché :
   - **À jour** : la version installée correspond à la version distante connue.
   - **Mise à jour disponible** : une version plus récente est détectée.
   - **Redémarrage requis** : la mise à jour a été appliquée et Docker doit être relancé.
   - **Installation incompatible** : un prérequis manque ou l'état local empêche l'action.
   - **Vérification impossible** : la source distante n'a pas pu être contactée ou les versions ne peuvent pas être comparées.

### Informations affichées

| Zone | Description |
|---|---|
| **Version installée** | Version lue depuis le fichier `VERSION` ou la variable d'environnement `APP_VERSION`. |
| **Version distante** | Version publiée lue depuis GitHub. |
| **Branche courante / cible** | Branche Git locale et branche utilisée pour la mise à jour. |
| **État Git** | Doit être propre pour appliquer une mise à jour. |
| **Commits** | Identifiants courts des commits local et distant. |

### Appliquer une mise à jour

Quand le statut indique **Mise à jour disponible**, cliquez sur **Appliquer**, confirmez l'action, puis suivez le journal affiché sur la page.

La mise à jour :

- utilise le dépôt Git déjà installé, sans recloner l'application ;
- refuse de continuer si des changements locaux sont présents ;
- vérifie le remote, la branche cible, le script `scripts/update.sh` et Docker Compose ;
- bascule ou tire la branche cible configurée, puis prépare le code applicatif.

Après application, cliquez sur **Redémarrer Docker** pour relancer la stack avec la nouvelle version.

Pendant une mise à jour ou un redémarrage, l'administration affiche un **overlay bloquant**. Il empêche les clics, formulaires et raccourcis jusqu'à la fin de l'opération. Si le serveur redémarre et répond temporairement moins vite, la page affiche une reconnexion automatique.

### Bonnes pratiques

- Lancez une sauvegarde avant une mise à jour importante.
- Évitez d'appliquer une mise à jour pendant un import massif ou une restauration.
- Si la vérification échoue, contrôlez l'accès réseau du serveur, l'état Git local et la disponibilité de Docker Compose.

---

## 22. À propos

Accessible depuis **À propos** dans le menu de navigation (tous les utilisateurs connectés).

La page **À propos** affiche les informations techniques de l'instance en cours d'exécution :

- **Version** de l'application (lue depuis le fichier `VERSION` ou la variable d'environnement `APP_VERSION`)
- **Commit git** associé au déploiement (si disponible)
- **Stack technique** : backend, base de données, déploiement
- **Licence** : lien vers le fichier `LICENSE` du projet

Ces informations sont utiles pour identifier la version installée lors d'un signalement de problème ou d'une mise à jour.

---

## 23. Éditeur d'annonces intégré

Accessible depuis **Annonces** dans le menu de navigation, puis via la création ou la modification d'une annonce.

L'éditeur intégré permet de créer des annonces graphiques 16:9 directement dans Visio-Display. Le canvas est placé au centre du workspace, avec une barre d'outils groupée à gauche et un panneau de propriétés contextuel à droite.

### Outils de création

- **Texte** ajoute des calques typographiques éditables.
- **Formes** et **lignes** ajoutent une structure graphique simple.
- **Image** ouvre directement le panneau **Fond** avec l'upload image, la médiathèque, la banque externe et la couleur de fond, sans clic supplémentaire.
- **Icônes** insère des pictogrammes issus de Lucide Icons, Tabler Icons et des SVG locaux.

### Positionnement et calques

Utilisez la grille visuelle et le snap pour aligner les objets. Le système de calques permet de sélectionner, réordonner, masquer et supprimer les objets, tandis que la liste compacte garde la zone canvas lisible.

Le panneau droit s'adapte au contexte :

- aucune sélection : réglages du document, export et fond ;
- texte sélectionné : options typographiques ;
- image sélectionnée : options image ;
- objet sélectionné : position, dimensions et ordre de calque.

### Export et diffusion

Utilisez **Export PNG** pour rendre l'annonce en image 16:9 et l'ajouter à la médiathèque. Configurez ensuite les écrans ciblés et la durée d'affichage comme pour un média classique.

### Sources des icônes

L'éditeur utilise Lucide Icons, Tabler Icons et les assets SVG locaux :

```text
web/static/assets/lucide/
web/static/assets/tabler/outline/
web/static/assets/tabler/filled/
```

---

*Documentation générée pour Visio-Display — Application d'affichage dynamique.*
