<!-- Licensed under the GNU General Public License v3.0 (GPL-3.0). Copyright (c) 2026 Eric TOMAS (Woofix). See the LICENSE file for details. -->

# Security Policy

If you find a security flaw, please do **not** create a public issue.

Contact the maintainers privately through GitHub with:

- a short description of the issue;
- the affected version or commit;
- reproduction steps when possible;
- any relevant logs or screenshots with secrets removed.

## Operational Notes

- Keep `SECRET_KEY`, `POSTGRES_PASSWORD`, SSH passwords and SMB credentials out of Git.
- Run `scripts/security_bootstrap.sh install .` on new server installs, then `scripts/security_bootstrap.sh update .` after updates. Update mode only adds missing keys and never replaces existing `SECRET_KEY` or `POSTGRES_PASSWORD`.
- The bootstrap creates missing `SECRET_KEY`, `POSTGRES_PASSWORD`, `DISPLAY_API_TOKEN`, `CLIENT_HEARTBEAT_TOKEN` and `VISIO_HOST_ROOT`, applies `chmod 600` to `.env`, creates `PRIVATE_DIR/backups`, and applies `chmod 700` to private data and backup directories.
- Use HTTPS and `SESSION_COOKIE_SECURE=1` when deploying behind a reverse proxy.
- Restrict `TRUSTED_HOSTS` to the expected hostnames in production.
- Keep `CLIENT_HEARTBEAT_TOKEN` defined and shared only with managed kiosk clients; heartbeat submissions are rejected without it.
- Keep `DISPLAY_API_TOKEN` defined. The app and Docker stack refuse to start without it, and `/` plus public display endpoints require `X-Screen-Token` or `?screen_token=` on `/api/images`, `/api/durations`, `/api/pools`, `/api/screens`, `/api/halo` and `/api/priority-alert`.
- Backups can include media, private application data and a copy of `.env`; treat backup archives as secrets and store them accordingly.
- Remote client operations still support password-based SSH for convenience, but prefer SSH keys where possible. When password mode is used, the app passes the password to `sshpass` through a temporary `0600` file instead of command-line arguments.
- Server update and Docker restart actions are restricted to the super-admin, require CSRF-protected `POST` requests, and use a persistent system lock stored under `PRIVATE_DIR` to block concurrent admin actions while the operation is running.
- The admin update workflow uses the existing Git checkout only. It refuses to run on a dirty worktree or when the configured remote/branch cannot be verified; set `VISIO_UPDATE_REMOTE`, `VISIO_UPDATE_BRANCH` and `VISIO_HOST_ROOT` deliberately for production deployments.
- The Docker socket is mounted into the app container so the super-admin can restart the stack after an update. Treat super-admin access and host-level Docker access as sensitive operational privileges.
