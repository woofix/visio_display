# Security hardening notes

## Docker production overlay

Use the optional production overlay when host volume ownership allows the app to
run as a non-root user:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

The overlay adds `cap_drop: [ALL]`, `no-new-privileges:true`, read-only
application code mounts for `app` and `worker`, and `read_only` root filesystems
where practical. Set `VISIO_RUNTIME_UID_GID` when the default `1000:1000` cannot
write to `MEDIA_DIR` and `PRIVATE_DIR`.

The `updater` service deliberately keeps `/var/run/docker.sock` and a writable
repository mount. This is required for the self-hosted update workflow: the
updater applies repository changes and restarts Docker services from inside the
stack. Treat updater access as host-level privileged access.

## Dependency audit

`web/requirements.lock.txt` records the installed Python versions observed in
the local project virtualenv. Refresh it after dependency changes:

```bash
.venv/bin/python -m pip freeze > web/requirements.lock.txt
```

Run a Python dependency vulnerability audit from the project root:

```bash
.venv/bin/python -m pip install -r web/requirements-dev.txt
.venv/bin/pip-audit -r web/requirements.txt
```

For container images or OS packages, use an image scanner such as `osv-scanner`
or Trivy in CI against the built image.
