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
- The bootstrap creates missing `SECRET_KEY`, `POSTGRES_PASSWORD` and `CLIENT_HEARTBEAT_TOKEN`, applies `chmod 600` to `.env`, creates `PRIVATE_DIR/backups`, and applies `chmod 700` to private data and backup directories.
- Use HTTPS and `SESSION_COOKIE_SECURE=1` when deploying behind a reverse proxy.
- Restrict `TRUSTED_HOSTS` to the expected hostnames in production.
- Set `CLIENT_HEARTBEAT_TOKEN` on managed deployments when client heartbeat submissions should require a shared token.
- Backups can include media, private application data and a copy of `.env`; store them accordingly.
