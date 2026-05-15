<!-- Licensed under the GNU General Public License v3.0 (GPL-3.0). Copyright (c) 2026 Eric TOMAS (Woofix). See the LICENSE file for details. -->

# Contributing

Contributions are welcome.

## How to contribute

1. Fork the repo
2. Create a branch
3. Commit your changes
4. Open a Pull Request

## Before submitting

- Keep changes scoped and consistent with the existing Flask/Jinja structure.
- Update `README.md`, `USER_GUIDE.md` and the built-in wiki when behavior changes.
- Run the available smoke tests or, at minimum, compile touched Python files.
- Avoid committing generated media, backups, private data or local environment files.

## Project structure

`web/` is the only runtime application tree. The root paths `services`, `templates`, `translations.py`, and `tools` are controlled symlinks to `web/` for development compatibility only.

## Git commit versioning

Enable the repository hook once on the machine where commits are created:

```bash
./scripts/install_git_hooks.sh
```

After that, each `git commit` automatically bumps `VERSION` and stages it into the commit.

The bump is detected from the staged files:

- regular change: patch (`1.0.0` -> `1.0.1`)
- sensitive change (`web/db.py`, `Dockerfile`, `docker-compose.yml`, dependencies) or deleted file: major (`1.0.0` -> `2.0.0`)

Override the bump for one commit when needed:

```bash
VISIO_VERSION_BUMP=minor git commit -m "..."
VISIO_VERSION_BUMP=major git commit -m "..."
VISIO_VERSION_BUMP=none git commit -m "..."
```

## Rules

- Keep code clean
- Follow the project structure
- Test before submitting
