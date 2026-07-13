<!-- Licensed under the GNU General Public License v3.0 (GPL-3.0). Copyright (c) 2026 Eric TOMAS (Woofix). See the LICENSE file for details. -->

# Security Policy

If you find a security flaw, please do **not** create a public issue.

Contact the maintainers privately through GitHub with:

- a short description of the issue;
- the affected version or commit;
- reproduction steps when possible;
- any relevant logs or screenshots with secrets removed.

## Operational Notes

- Keep `SECRET_KEY`, `POSTGRES_PASSWORD`, `UPDATER_API_TOKEN`, SSH passwords and SMB credentials out of Git.
- Run `scripts/security_bootstrap.sh install .` on new server installs, then `scripts/security_bootstrap.sh update .` after updates. Update mode only adds missing keys and never replaces existing `SECRET_KEY` or `POSTGRES_PASSWORD`.
- The bootstrap creates missing `SECRET_KEY`, `POSTGRES_PASSWORD`, `DISPLAY_API_TOKEN`, `UPDATER_API_TOKEN`, `CLIENT_HEARTBEAT_TOKEN` and `VISIO_HOST_ROOT`, applies `chmod 600` to `.env`, creates `PRIVATE_DIR/backups`, and applies `chmod 700` to private data and backup directories.
- Use HTTPS and `SESSION_COOKIE_SECURE=1` when deploying behind a reverse proxy.
- Restrict `TRUSTED_HOSTS` to the expected hostnames in production.
- Keep `CLIENT_HEARTBEAT_TOKEN` defined and shared only with managed kiosk clients; heartbeat submissions are rejected without it.
- Keep `DISPLAY_API_TOKEN` defined. The app and Docker stack refuse to start without it, and `/` plus public display endpoints require `X-Screen-Token` or `?screen_token=` on `/api/images`, `/api/durations`, `/api/pools`, `/api/screens`, `/api/halo` and `/api/priority-alert`.
- Backups can include media, private application data and a copy of `.env`; treat backup archives as secrets and store them accordingly.
- Remote client operations still support password-based SSH for convenience, but prefer SSH keys where possible. When password mode is used, the app passes the password to `sshpass` through a temporary `0600` file instead of command-line arguments.
- Server update and Docker restart actions are restricted to the super-admin, require CSRF-protected `POST` requests, and use a persistent system lock stored under `PRIVATE_DIR` to block concurrent admin actions while the operation is running.
- The admin update workflow uses the existing Git checkout only. It refuses to run on a dirty worktree or when the configured remote/branch cannot be verified; set `VISIO_UPDATE_REMOTE`, `VISIO_UPDATE_BRANCH` and `VISIO_HOST_ROOT` deliberately for production deployments.
- The app container must not mount `/var/run/docker.sock`. Docker access is isolated in the internal `updater` service, authenticated with `UPDATER_API_TOKEN` and not publicly exposed (no host port mapping; reachable only from other containers on the compose network).
- **This isolation is network-level only, not privilege-level.** The `Dockerfile` has no `USER` directive, so `app`, `worker` and `updater` all run as root by default. `updater` additionally mounts `/var/run/docker.sock`, and its restart flow (`update_svc._start_updater_restart_helper`) shells out to `docker run` with the host repository directory bind-mounted into a freshly spawned container. Root on the Docker socket plus the ability to bind-mount arbitrary host paths is equivalent to root on the Docker host itself. The `UPDATER_API_TOKEN` check and the fixed operation allowlist (`status`, `runtime-status`, `apply-update`, `restart-stack`, `apply-update-and-restart` in `updater_server.py`) restrict which *HTTP endpoints* can be called, not what those endpoints do once called — each write operation ends in host-root-equivalent Docker actions. Treat compromise of the updater token, or of the updater process itself, as equivalent to a full root compromise of the host, not just of the container.
- `docker-compose.prod.yml` is an optional hardening overlay (`docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d`; **not** applied by `docker compose up -d` alone) that drops Linux capabilities and runs `app`/`worker` under an unprivileged UID/GID. It deliberately leaves `updater` running as root with `docker.sock` mounted, because the restart/self-update flow requires it — enabling the overlay does not remove the risk described above. Until the updater's privileged operations are redesigned to run outside the container (e.g. a host-side agent invoked by signal rather than a container holding the socket), restrict the host running this stack to trusted administrators only, and do not deploy it on shared or multi-tenant infrastructure.
