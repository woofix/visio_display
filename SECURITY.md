<!-- MIT License - Copyright (c) 2026 Woofix - See LICENSE file for details -->

# Security Policy

If you find a security flaw, please do **not** create a public issue.

Contact the maintainers privately through GitHub with:

- a short description of the issue;
- the affected version or commit;
- reproduction steps when possible;
- any relevant logs or screenshots with secrets removed.

## Operational Notes

- Keep `SECRET_KEY`, `POSTGRES_PASSWORD`, SSH passwords and SMB credentials out of Git.
- Use HTTPS and `SESSION_COOKIE_SECURE=1` when deploying behind a reverse proxy.
- Restrict `TRUSTED_HOSTS` to the expected hostnames in production.
- Backups can include media, private application data and a copy of `.env`; store them accordingly.
