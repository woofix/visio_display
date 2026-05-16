# Licensed under the GNU General Public License v3.0 (GPL-3.0). Copyright (c) 2026 Eric TOMAS (Woofix). See the LICENSE file for details.

import json
import os
import shlex
import shutil
import subprocess
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass

from services import updater_client
from services.i18n import _t
from services.system_lock_svc import release_lock, update_lock
from services.version_svc import _compare_versions


SERVICE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_REPO_CWD = os.path.normpath(os.path.join(SERVICE_DIR, "..", ".."))
UPDATE_STEPS = [
    ("pull", "version_step_pull"),
    ("stop", "version_step_stop"),
    ("restart", "version_step_restart"),
    ("containers", "version_step_containers"),
    ("app", "version_step_app"),
]


def _running_as_updater():
    return os.environ.get("VISIO_UPDATER_ROLE", "").strip() == "1"


def _delegate_to_updater():
    return updater_client.updater_configured() and not _running_as_updater()


def _step_payload(active_stage, *, failed_stage=None):
    payload = []
    active_index = next((index for index, item in enumerate(UPDATE_STEPS) if item[0] == active_stage), 0)
    failed_index = next((index for index, item in enumerate(UPDATE_STEPS) if item[0] == failed_stage), None)
    for key, label_key in UPDATE_STEPS:
        index = next(index for index, item in enumerate(UPDATE_STEPS) if item[0] == key)
        if failed_index is not None and index == failed_index:
            state = "failed"
        elif failed_index is not None:
            state = "done" if index < failed_index else "pending"
        elif index == active_index:
            state = "active"
        else:
            state = "done" if index < active_index else "pending"
        payload.append({"key": key, "label": _t(label_key), "state": state})
    return payload


def _update_step(lock_token, stage, message, *, progress=None, timeout_seconds=1800, failed=False):
    if not lock_token:
        return
    update_lock(
        lock_token,
        message=message,
        progress=progress,
        timeout_seconds=timeout_seconds,
        stage=stage,
        steps=_step_payload(stage, failed_stage=stage if failed else None),
        error=failed,
    )


@dataclass
class CommandResult:
    ok: bool
    stdout: str = ""
    stderr: str = ""
    returncode: int = 0


def _repo_dir():
    return os.path.normpath(os.environ.get("VISIO_GIT_ROOT", "").strip() or DEFAULT_REPO_CWD)


def _dotenv_values(repo_dir):
    values = {}
    try:
        with open(os.path.join(repo_dir, ".env"), "r", encoding="utf-8") as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip().strip("'\"")
    except OSError:
        return {}
    return values


def _compose_subprocess_env(repo_dir):
    env = os.environ.copy()
    dotenv = _dotenv_values(repo_dir)
    for key in ("VISIO_HOST_ROOT", "MEDIA_DIR", "PRIVATE_DIR", "COMPOSE_PROJECT_NAME"):
        if dotenv.get(key):
            env[key] = dotenv[key]
    return env


def _compose_env_exports(repo_dir):
    dotenv = _dotenv_values(repo_dir)
    lines = []
    for key in ("VISIO_HOST_ROOT", "MEDIA_DIR", "PRIVATE_DIR", "COMPOSE_PROJECT_NAME"):
        if dotenv.get(key):
            lines.append(f"export {key}={shlex.quote(dotenv[key])}")
    return lines


def _update_branch():
    return os.environ.get("VISIO_UPDATE_BRANCH", "main").strip() or "main"


def _run(command, *, cwd=None, timeout=12):
    try:
        result = subprocess.run(
            command,
            cwd=cwd or _repo_dir(),
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError as exc:
        return CommandResult(False, stderr=f"Commande introuvable: {command[0]}", returncode=127)
    except subprocess.TimeoutExpired:
        return CommandResult(False, stderr=f"Commande trop longue: {' '.join(command)}", returncode=124)
    except OSError as exc:
        return CommandResult(False, stderr=str(exc), returncode=1)
    return CommandResult(
        result.returncode == 0,
        stdout=(result.stdout or "").strip(),
        stderr=(result.stderr or "").strip(),
        returncode=result.returncode,
    )


def _git(command, *, timeout=12):
    return _run(["git", *command], timeout=timeout)


def _first_line(value):
    return str(value or "").splitlines()[0].strip()


def _read_file_at_ref(ref, path):
    result = _git(["show", f"{ref}:{path}"], timeout=10)
    return result.stdout.strip() if result.ok else ""


def _read_local_version(repo_dir):
    try:
        with open(os.path.join(repo_dir, "VERSION"), "r", encoding="utf-8") as handle:
            return handle.read().strip()
    except OSError:
        return ""


def _update_script_for_branch(repo_dir, branch):
    if branch in {"main", "dev"}:
        return os.path.join(repo_dir, f"{branch}.sh"), f"{branch}.sh"
    return os.path.join(repo_dir, "scripts", "update.sh"), "scripts/update.sh"


def _docker_compose_command():
    docker_path = shutil.which("docker")
    if docker_path:
        result = _run([docker_path, "compose", "version"], cwd=_repo_dir(), timeout=8)
        if result.ok:
            return [docker_path, "compose"], ""
    legacy_path = shutil.which("docker-compose")
    if legacy_path:
        result = _run([legacy_path, "version"], cwd=_repo_dir(), timeout=8)
        if result.ok:
            return [legacy_path], ""
    return [], "Docker Compose est introuvable ou inaccessible depuis le serveur."


def _current_compose_project_name():
    env_project = os.environ.get("COMPOSE_PROJECT_NAME", "").strip()
    if env_project:
        return env_project

    docker_path = shutil.which("docker")
    if not docker_path:
        return ""

    hostname = _run(["hostname"], cwd=_repo_dir(), timeout=4).stdout.strip()
    if not hostname:
        return ""
    result = _run(
        [
            docker_path,
            "inspect",
            "--format",
            '{{ index .Config.Labels "com.docker.compose.project" }}',
            hostname,
        ],
        cwd=_repo_dir(),
        timeout=8,
    )
    return result.stdout.strip() if result.ok else ""


def _with_compose_project(command, project_name):
    if not project_name:
        return command
    if len(command) >= 2 and os.path.basename(command[0]) == "docker" and command[1] == "compose":
        return [command[0], command[1], "--project-name", project_name, *command[2:]]
    return [command[0], "--project-name", project_name, *command[1:]]


def _parse_compose_json_lines(output):
    output = (output or "").strip()
    if not output:
        return []
    try:
        parsed = json.loads(output)
        if isinstance(parsed, list):
            return [item for item in parsed if isinstance(item, dict)]
        if isinstance(parsed, dict):
            return [parsed]
    except (json.JSONDecodeError, TypeError, ValueError):
        pass

    rows = []
    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except (json.JSONDecodeError, TypeError, ValueError):
            continue
        if isinstance(item, dict):
            rows.append(item)
    return rows


def _compose_services(compose_cmd=None, project_name=""):
    compose_cmd = compose_cmd or _docker_compose_command()[0]
    if not compose_cmd:
        return []
    result = _run([*_with_compose_project(compose_cmd, project_name), "config", "--services"], cwd=_repo_dir(), timeout=20)
    if not result.ok:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _compose_containers(compose_cmd=None, project_name=""):
    compose_cmd = compose_cmd or _docker_compose_command()[0]
    if not compose_cmd:
        return [], "Docker Compose indisponible"
    result = _run([*_with_compose_project(compose_cmd, project_name), "ps", "--format", "json"], cwd=_repo_dir(), timeout=20)
    if not result.ok:
        return [], result.stderr or result.stdout or "docker compose ps indisponible"
    return _parse_compose_json_lines(result.stdout), ""


def _container_service_name(container):
    return str(
        container.get("Service")
        or container.get("Name")
        or container.get("Names")
        or ""
    ).strip()


def _container_is_running(container):
    state = str(container.get("State") or "").lower()
    status = str(container.get("Status") or "").lower()
    return state == "running" or status.startswith("up")


def _container_health_ok(container):
    health = str(container.get("Health") or "").lower().strip()
    if not health:
        return True
    return health in {"healthy", "running"}


def _app_health_url():
    explicit = os.environ.get("VISIO_APP_HEALTH_URL", "").strip()
    if explicit:
        return explicit
    token = os.environ.get("DISPLAY_API_TOKEN", "").strip()
    if token:
        return "http://app:8080/?screen_token=" + urllib.parse.quote(token)
    return "http://app:8080/"


def _http_ok(url, *, timeout=6):
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "visio-update-health/1.0"})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return 200 <= int(response.status) < 500, f"HTTP {response.status}"
    except Exception as exc:
        return False, str(exc)


def runtime_readiness_status(*, compose_cmd=None, project_name="", app_url=None):
    if _delegate_to_updater() and compose_cmd is None and not project_name and app_url is None:
        return updater_client.get_json("/runtime-status").get("runtime", {})

    compose_cmd = compose_cmd or _docker_compose_command()[0]
    project_name = project_name if project_name is not None else _current_compose_project_name()
    checks = []

    services = _compose_services(compose_cmd, project_name)
    containers, compose_error = _compose_containers(compose_cmd, project_name)
    by_service = {_container_service_name(item): item for item in containers if _container_service_name(item)}

    if compose_error:
        checks.append({"key": "containers", "label": _t("version_runtime_containers"), "ok": False, "detail": compose_error})
    else:
        expected_services = services or ["app", "worker", "postgres", "redis"]
        missing = [service for service in expected_services if service not in by_service]
        stopped = [service for service in expected_services if service in by_service and not _container_is_running(by_service[service])]
        if missing or stopped:
            detail_parts = []
            if missing:
                detail_parts.append(_t("version_runtime_missing", services=", ".join(missing)))
            if stopped:
                detail_parts.append(_t("version_runtime_stopped", services=", ".join(stopped)))
            checks.append({"key": "containers", "label": _t("version_runtime_containers_running"), "ok": False, "detail": "; ".join(detail_parts)})
        else:
            checks.append({"key": "containers", "label": _t("version_runtime_containers_running"), "ok": True, "detail": ", ".join(expected_services)})

        unhealthy = [
            service for service in expected_services
            if service in by_service and service != "app" and not _container_health_ok(by_service[service])
        ]
        if unhealthy:
            checks.append({"key": "healthchecks", "label": _t("version_runtime_healthchecks"), "ok": False, "detail": ", ".join(unhealthy)})
        else:
            checks.append({"key": "healthchecks", "label": _t("version_runtime_healthchecks"), "ok": True, "detail": "OK"})

    http_url = app_url or _app_health_url()
    http_ready, http_detail = _http_ok(http_url)
    checks.append({
        "key": "http",
        "label": _t("version_runtime_http"),
        "ok": http_ready,
        "detail": http_detail,
    })

    ready = all(item["ok"] for item in checks)
    return {"ready": ready, "checks": checks, "checked_at": time.time()}


def wait_for_runtime_ready(*, lock_token=None, timeout_seconds=420, interval_seconds=3, project_name=None):
    deadline = time.time() + max(30, int(timeout_seconds))
    compose_cmd, compose_error = _docker_compose_command()
    project_name = (
        project_name
        if project_name is not None
        else os.environ.get("VISIO_COMPOSE_PROJECT_NAME", "").strip() or _current_compose_project_name()
    )
    if not compose_cmd:
        _update_step(lock_token, "containers", compose_error, progress=85, failed=True)
        raise RuntimeError(compose_error)

    last_detail = _t("version_runtime_wait_containers")
    while time.time() < deadline:
        status = runtime_readiness_status(compose_cmd=compose_cmd, project_name=project_name)
        failing = [item for item in status["checks"] if not item["ok"]]
        if not failing:
            _update_step(lock_token, "app", _t("version_app_available"), progress=100)
            return status

        first = failing[0]
        stage = "app" if first["key"] == "http" else "containers"
        last_detail = f"{first['label']}: {first.get('detail') or 'en attente'}"
        _update_step(lock_token, stage, last_detail, progress=88 if stage == "containers" else 94)
        time.sleep(max(1, int(interval_seconds)))

    _update_step(lock_token, "app", _t("version_runtime_timeout_step", detail=last_detail), progress=100, failed=True)
    raise RuntimeError(_t("version_runtime_timeout_error", detail=last_detail))


def _shell_join(command):
    return " ".join(shlex.quote(str(part)) for part in command)


def _current_container_image():
    docker_path = shutil.which("docker")
    if not docker_path:
        return ""
    hostname = _run(["hostname"], cwd=_repo_dir(), timeout=4).stdout.strip()
    if not hostname:
        return ""
    result = _run([docker_path, "inspect", "--format", "{{.Config.Image}}", hostname], cwd=_repo_dir(), timeout=8)
    return result.stdout.strip() if result.ok else ""


def _start_updater_restart_helper(helper_name, helper_script, *, repo_dir, project_name, progress_callback=None):
    docker_path = shutil.which("docker")
    if not docker_path:
        raise RuntimeError("Docker CLI est introuvable dans le service updater.")
    image = _current_container_image()
    if not image:
        raise RuntimeError("Image du service updater introuvable.")

    host_repo_dir = os.environ.get("VISIO_HOST_ROOT", "").strip() or repo_dir
    host_private_dir = os.environ.get("VISIO_HOST_PRIVATE_DIR", "").strip()
    env_file = os.path.join(host_repo_dir, ".env")
    helper_command = [
        docker_path,
        "run",
        "-d",
        "--rm",
        "--name",
        helper_name,
        "--network",
        f"{project_name or 'visio_display'}_default",
        "-v",
        "/var/run/docker.sock:/var/run/docker.sock",
        "-v",
        f"{host_repo_dir}:{repo_dir}",
    ]
    if host_private_dir:
        helper_command.extend(["-v", f"{host_private_dir}:/app/data"])
    helper_command.extend([
        "-w",
        repo_dir,
    ])
    if os.path.isfile(env_file):
        helper_command.extend(["--env-file", env_file])
    helper_command.extend([
        "-e",
        "PRIVATE_DIR=/app/data",
        "-e",
        "MEDIA_DIR=/app/static/data",
        "-e",
        f"DISPLAY_API_TOKEN={os.environ.get('DISPLAY_API_TOKEN', '')}",
        "-e",
        f"VISIO_GIT_ROOT={repo_dir}",
        "-e",
        "VISIO_UPDATER_ROLE=1",
        "-e",
        "VISIO_RESTART_HELPER_SERVICE=updater",
    ])
    if project_name:
        helper_command.extend([
            "-e",
            f"COMPOSE_PROJECT_NAME={project_name}",
            "-e",
            f"VISIO_COMPOSE_PROJECT_NAME={project_name}",
        ])
    helper_command.extend([image, "sh", "-lc", helper_script])
    if progress_callback:
        progress_callback(f"$ {' '.join(helper_command[:10])} ...")
    result = _run(helper_command, cwd=repo_dir, timeout=20)
    if not result.ok:
        raise RuntimeError(result.stderr or result.stdout or _t("version_restart_helper_failed"))
    if progress_callback:
        progress_callback(_t("version_restart_helper_started", name=helper_name))


def _start_restart_helper(
    command,
    *,
    repo_dir,
    compose_cmd,
    project_name,
    progress_callback=None,
    lock_token=None,
    verify_runtime=False,
    post_success_command=None,
):
    helper_name = f"visio-display-restart-{int(time.time())}"
    helper_service = os.environ.get("VISIO_RESTART_HELPER_SERVICE", "").strip()
    if not helper_service:
        helper_service = "updater" if _running_as_updater() else "app"
    restart_command = _shell_join(command)
    helper_pythonpath = f"{repo_dir}/web:/app"
    helper_lines = [
        "sleep 2",
        f"cd {shlex.quote(repo_dir)}",
        *_compose_env_exports(repo_dir),
        f"{restart_command}",
        "status=$?",
    ]
    if verify_runtime:
        wait_code = (
            "from services.update_svc import wait_for_runtime_ready; "
            f"wait_for_runtime_ready(lock_token={lock_token!r}, project_name={project_name!r})"
        )
        helper_lines.extend([
            "if [ \"$status\" -eq 0 ]; then",
            f"  PYTHONPATH={shlex.quote(helper_pythonpath)} python -c {shlex.quote(wait_code)}",
            "  status=$?",
            "fi",
        ])
    if lock_token:
        success_cleanup = (
            "from services.system_lock_svc import release_lock; "
            f"release_lock({lock_token!r})"
        )
        failure_cleanup = (
            "from services.system_lock_svc import _read_lock_raw, update_lock; "
            "from services.i18n import _t; "
            "from services.update_svc import _step_payload; "
            "lock = _read_lock_raw(); "
            "already_detailed = bool(lock and lock.get('error')); "
            f"None if already_detailed else update_lock({lock_token!r}, message=_t('version_restart_timeout_log'), "
            "progress=100, stage='restart', steps=_step_payload('restart', failed_stage='restart'), "
            "error=True, timeout_seconds=1800)"
        )
        helper_lines.extend([
            f"cd {shlex.quote(repo_dir)}",
            "if [ \"$status\" -eq 0 ]; then",
            f"  PYTHONPATH={shlex.quote(helper_pythonpath)} python -c {shlex.quote(success_cleanup)} || true",
            *([f"  {_shell_join(post_success_command)} || true"] if post_success_command else []),
            "else",
            f"  PYTHONPATH={shlex.quote(helper_pythonpath)} python -c {shlex.quote(failure_cleanup)} || true",
            "fi",
            "exit $status",
        ])
    helper_script = "\n".join(helper_lines)
    if _running_as_updater():
        return _start_updater_restart_helper(
            helper_name,
            helper_script,
            repo_dir=repo_dir,
            project_name=project_name,
            progress_callback=progress_callback,
        )

    helper_command = [
        *_with_compose_project(compose_cmd, project_name),
        "run",
        "-d",
        "--rm",
        "--name",
        helper_name,
        "--no-deps",
        helper_service,
        "sh",
        "-lc",
        helper_script,
    ]
    if progress_callback:
        progress_callback(f"$ {' '.join(helper_command[:8])} ...")
    result = _run(helper_command, cwd=repo_dir, timeout=20)
    if not result.ok:
        raise RuntimeError(result.stderr or result.stdout or _t("version_restart_helper_failed"))
    if progress_callback:
        progress_callback(_t("version_restart_helper_started", name=helper_name))


def _current_ref():
    branch = _git(["rev-parse", "--abbrev-ref", "HEAD"])
    if not branch.ok:
        return "", "", "branche ou tag courant illisible"
    branch_name = branch.stdout.strip()
    if branch_name and branch_name != "HEAD":
        return "branch", branch_name, ""

    tag = _git(["describe", "--tags", "--exact-match", "HEAD"])
    if tag.ok and tag.stdout.strip():
        return "tag", tag.stdout.strip(), ""

    commit = _git(["rev-parse", "--short", "HEAD"])
    if commit.ok and commit.stdout.strip():
        return "detached", commit.stdout.strip(), ""
    return "", "", "branche ou tag courant illisible"


def _remote_ref_for_branch(remote_name, branch):
    remote_branch = f"{remote_name}/{branch}"
    exists = _git(["rev-parse", "--verify", "--quiet", remote_branch])
    return remote_branch if exists.ok else ""


def _commit_is_ancestor(ancestor, descendant):
    if not ancestor or not descendant:
        return False
    result = _git(["merge-base", "--is-ancestor", ancestor, descendant])
    return result.returncode == 0


def _latest_tag():
    result = _git(["for-each-ref", "--sort=-creatordate", "--format=%(refname:short)", "refs/tags"], timeout=10)
    if not result.ok:
        return ""
    return _first_line(result.stdout)


def _build_incompatible(reason, checks, extra=None):
    payload = {
        "status": "incompatible",
        "status_label": _t("version_status_incompatible"),
        "status_tone": "danger",
        "compatible": False,
        "can_apply": False,
        "can_restart": False,
        "reason": reason,
        "checks": checks,
        "repo_dir": _repo_dir(),
        "local_version": "",
        "remote_version": "",
        "branch": "",
        "target_branch": "",
        "current_ref": "",
        "current_ref_type": "",
        "git_state": "unknown",
        "local_commit": "",
        "remote_commit": "",
        "remote": "",
        "remote_ref": "",
        "target": "",
    }
    if extra:
        payload.update(extra)
    return payload


def get_update_status(*, fetch_remote=False, allow_dirty=False):
    if _delegate_to_updater():
        payload = updater_client.get_json("/status", params={"fetch": "1" if fetch_remote else "0"}, timeout=80 if fetch_remote else 20)
        status = payload.get("status") or {}
        return status

    repo_dir = _repo_dir()
    checks = []

    def add_check(key, label, ok, detail=""):
        checks.append({"key": key, "label": label, "ok": bool(ok), "detail": detail})

    if not os.path.isdir(repo_dir):
        add_check("repo_dir", _t("version_check_repo_dir"), False, repo_dir)
        return _build_incompatible(_t("version_reason_no_repo_dir"), checks)
    add_check("repo_dir", _t("version_check_repo_dir"), True, repo_dir)

    if not os.path.isdir(os.path.join(repo_dir, ".git")):
        add_check("git_dir", _t("version_check_git_dir"), False, ".git introuvable")
        return _build_incompatible(_t("version_reason_no_git_dir"), checks)
    add_check("git_dir", _t("version_check_git_dir"), True)

    remote_name = os.environ.get("VISIO_UPDATE_REMOTE", "origin").strip() or "origin"
    target_branch = _update_branch()
    remote_url = _git(["remote", "get-url", remote_name])
    if not remote_url.ok or not remote_url.stdout.strip():
        add_check("remote", _t("version_check_remote"), False, remote_url.stderr or f"remote {remote_name} introuvable")
        return _build_incompatible(_t("version_reason_no_remote"), checks)
    add_check("remote", _t("version_check_remote"), True, f"{remote_name}: {remote_url.stdout.strip()}")

    ref_type, ref_name, ref_error = _current_ref()
    if ref_error:
        add_check("current_ref", _t("version_check_current_ref"), False, ref_error)
        return _build_incompatible(ref_error, checks)
    add_check("current_ref", _t("version_check_current_ref"), True, f"{ref_type}: {ref_name}")
    add_check("target_branch", _t("version_check_target_branch"), True, target_branch)
    local_commit = _git(["rev-parse", "HEAD"]).stdout.strip()
    local_version = _read_local_version(repo_dir)
    status_context = {
        "local_version": local_version,
        "branch": ref_name if ref_type == "branch" else "",
        "target_branch": target_branch,
        "current_ref": ref_name,
        "current_ref_type": ref_type,
        "local_commit": local_commit[:12],
        "remote": remote_url.stdout.strip(),
    }

    status = _git(["status", "--porcelain"])
    if not status.ok:
        add_check("git_clean", _t("version_check_git_clean"), False, status.stderr or _t("version_reason_git_state_unreadable"))
        return _build_incompatible(_t("version_reason_git_state_unreadable"), checks, status_context)
    git_state = "dirty" if status.stdout.strip() else "clean"
    if git_state != "clean" and not allow_dirty:
        add_check("git_clean", _t("version_check_git_clean"), False, status.stdout)
        return _build_incompatible(
            _t("version_reason_dirty"),
            checks,
            {**status_context, "git_state": git_state, "git_status": status.stdout},
        )
    add_check(
        "git_clean",
        _t("version_check_git_clean"),
        git_state == "clean",
        _t("version_check_no_local_changes") if git_state == "clean" else status.stdout,
    )

    update_script, update_script_label = _update_script_for_branch(repo_dir, ref_name if ref_type == "branch" else "")
    if not os.path.isfile(update_script):
        add_check("update_script", _t("version_check_update_script"), False, f"{update_script_label} introuvable")
        return _build_incompatible(_t("version_reason_no_update_script"), checks, status_context)
    add_check("update_script", _t("version_check_update_script"), True, update_script_label)

    compose_cmd, compose_error = _docker_compose_command()
    if not compose_cmd:
        add_check("docker_compose", _t("version_check_docker_compose"), False, compose_error)
        return _build_incompatible(compose_error, checks, status_context)
    add_check("docker_compose", _t("version_check_docker_compose"), True, " ".join(os.path.basename(part) for part in compose_cmd))

    if fetch_remote:
        fetch = _git(["fetch", remote_name, "--tags", "--prune"], timeout=60)
        if not fetch.ok:
            add_check("git_fetch", _t("version_check_git_fetch"), False, fetch.stderr or fetch.stdout)
            return _build_incompatible(
                _t("version_reason_fetch_failed"),
                checks,
                status_context,
            )
        add_check("git_fetch", _t("version_check_git_fetch"), True, fetch.stdout or _t("version_check_refs_updated"))

    remote_ref = ""
    remote_commit = ""
    remote_version = ""
    target = ""

    if ref_type == "branch":
        remote_ref = _remote_ref_for_branch(remote_name, target_branch)
        if not remote_ref:
            return _build_incompatible(
                _t("version_reason_no_remote_branch"),
                checks,
                {**status_context, "git_state": git_state},
            )
        remote_commit = _git(["rev-parse", remote_ref]).stdout.strip()
        remote_version = _read_file_at_ref(remote_ref, "VERSION")
        target = target_branch
    else:
        latest_tag = _latest_tag()
        if latest_tag:
            remote_ref = f"refs/tags/{latest_tag}"
            remote_commit = _git(["rev-list", "-n", "1", latest_tag]).stdout.strip()
            remote_version = _read_file_at_ref(latest_tag, "VERSION")
            target = latest_tag

    version_comparison = _compare_versions(local_version, remote_version)
    branch_switch_required = (
        ref_type == "branch"
        and bool(ref_name)
        and bool(target_branch)
        and ref_name != target_branch
    )
    if version_comparison > 0:
        status_name = "update_available"
        status_label = _t("version_status_update_available")
        status_tone = "warning"
        can_apply = True
        reason = ""
    elif version_comparison < 0:
        status_name = "local_ahead"
        status_label = _t("version_status_local_ahead")
        status_tone = "info"
        can_apply = False
        reason = _t("version_reason_remote_older")
    else:
        if not remote_commit or not local_commit or remote_commit == local_commit:
            if branch_switch_required:
                status_name = "branch_switch_required"
                status_label = _t("version_status_branch_switch_required")
                status_tone = "warning"
                can_apply = True
                reason = _t("version_reason_branch_switch", current=ref_name, target=target_branch)
            else:
                status_name = "up_to_date"
                status_label = _t("version_status_up_to_date")
                status_tone = "success"
                can_apply = False
                reason = ""
        elif _commit_is_ancestor(local_commit, remote_commit):
            status_name = "update_available"
            status_label = _t("version_status_update_available")
            status_tone = "warning"
            can_apply = True
            reason = ""
        elif _commit_is_ancestor(remote_commit, local_commit):
            status_name = "local_ahead"
            status_label = _t("version_status_local_ahead")
            status_tone = "info"
            can_apply = False
            reason = _t("version_reason_local_contains_remote")
        else:
            status_name = "diverged"
            status_label = _t("version_status_diverged")
            status_tone = "info"
            can_apply = False
            reason = _t("version_reason_diverged")

    return {
        "status": status_name,
        "status_label": status_label,
        "status_tone": status_tone,
        "compatible": True,
        "can_apply": can_apply,
        "can_restart": True,
        "reason": reason,
        "checks": checks,
        "repo_dir": repo_dir,
        "local_version": local_version,
        "remote_version": remote_version,
        "branch": ref_name if ref_type == "branch" else "",
        "target_branch": target_branch,
        "current_ref": ref_name,
        "current_ref_type": ref_type,
        "git_state": git_state,
        "git_status": "",
        "local_commit": local_commit[:12],
        "remote_commit": remote_commit[:12],
        "remote": remote_url.stdout.strip(),
        "remote_ref": remote_ref,
        "target": target,
        "compose_command": " ".join(compose_cmd),
        "update_script": update_script_label,
    }


def _stream_command(command, *, cwd, env=None, progress_callback=None):
    if progress_callback:
        progress_callback(f"$ {' '.join(command)}")
    try:
        process = subprocess.Popen(
            command,
            cwd=cwd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(f"Commande introuvable: {command[0]}") from exc
    except OSError as exc:
        raise RuntimeError(str(exc)) from exc

    assert process.stdout is not None
    for line in process.stdout:
        if progress_callback:
            progress_callback(line.rstrip())
    returncode = process.wait()
    if returncode != 0:
        raise RuntimeError(_t("version_command_failed", code=returncode))


def apply_update(*, progress_callback=None, lock_token=None):
    if _delegate_to_updater():
        _update_step(lock_token, "pull", _t("version_pull_progress"), progress=20)
        return updater_client.stream_operation(
            "/apply-update",
            progress_callback=progress_callback,
            payload={"lock_token": lock_token} if lock_token else None,
        )

    status = get_update_status(fetch_remote=True)
    if not status.get("compatible"):
        raise RuntimeError(status.get("reason") or "Installation incompatible.")
    if not status.get("can_apply"):
        raise RuntimeError(_t("version_no_update_available"))

    repo_dir = status["repo_dir"]
    _update_step(lock_token, "pull", _t("version_pull_progress"), progress=20)
    env = os.environ.copy()
    if status.get("target_branch"):
        env["VISIO_UPDATE_BRANCH"] = status["target_branch"]
    update_script, _update_script_label = _update_script_for_branch(repo_dir, status.get("branch", ""))
    command = ["bash", update_script]
    if status.get("current_ref_type") == "tag" and status.get("target") and update_script.endswith("scripts/update.sh"):
        command.append(status["target"])
    _stream_command(command, cwd=repo_dir, env=env, progress_callback=progress_callback)
    if lock_token:
        _update_step(lock_token, "app", _t("version_restart_connecting"), progress=85, timeout_seconds=900)
    refreshed = get_update_status(fetch_remote=False)
    refreshed["status"] = "restart_scheduled"
    refreshed["status_label"] = _t("version_status_restart_scheduled")
    refreshed["status_tone"] = "success"
    refreshed["can_apply"] = False
    refreshed["can_restart"] = False
    refreshed["reason"] = _t("version_reason_restart_scheduled")
    return refreshed


def restart_stack(*, progress_callback=None, lock_token=None):
    if _delegate_to_updater():
        _update_step(lock_token, "restart", _t("version_restart_progress"), progress=72, timeout_seconds=900)
        result = updater_client.stream_operation(
            "/restart-stack",
            progress_callback=progress_callback,
            payload={"lock_token": lock_token} if lock_token else None,
        )
        if lock_token:
            update_lock(lock_token, message=_t("version_restart_connecting"), progress=85)
        return result

    status = get_update_status(fetch_remote=False, allow_dirty=True)
    if not status.get("compatible"):
        raise RuntimeError(status.get("reason") or "Installation incompatible.")
    compose_cmd, compose_error = _docker_compose_command()
    if not compose_cmd:
        raise RuntimeError(compose_error)
    project_name = _current_compose_project_name()
    compose_project_cmd = _with_compose_project(compose_cmd, project_name)
    command = [*compose_project_cmd, "up", "-d", "--build"]
    if _running_as_updater():
        services = _compose_services(compose_cmd, project_name)
        primary_services = [
            service for service in ("app", "worker")
            if not services or service in services
        ] or [service for service in services if service != "updater"] or ["app", "worker"]
        command = [*compose_project_cmd, "up", "-d", "--build", "--no-deps", *primary_services]
        _update_step(lock_token, "restart", _t("version_restart_progress"), progress=72, timeout_seconds=900)
        if progress_callback:
            progress_callback(_t("version_restart_background"))
            progress_callback(f"$ {' '.join(command)}")
        if lock_token:
            update_lock(lock_token, message=_t("version_restart_background_lock"), progress=60)
        _stream_command(
            command,
            cwd=status["repo_dir"],
            env=_compose_subprocess_env(status["repo_dir"]),
            progress_callback=progress_callback,
        )
        wait_for_runtime_ready(lock_token=lock_token, project_name=project_name)
        if lock_token:
            release_lock(lock_token)
        status["status"] = "restart_scheduled"
        status["status_label"] = _t("version_status_restart_scheduled")
        status["status_tone"] = "success"
        status["can_apply"] = False
        status["can_restart"] = False
        status["reason"] = _t("version_reason_restart_scheduled")
        return status
    _update_step(lock_token, "restart", _t("version_restart_progress"), progress=72, timeout_seconds=900)
    if progress_callback:
        progress_callback(_t("version_restart_background"))
        progress_callback(f"$ {' '.join(command)}")
    if lock_token:
        update_lock(lock_token, message=_t("version_restart_background_lock"), progress=60)
    _start_restart_helper(
        command,
        repo_dir=status["repo_dir"],
        compose_cmd=compose_cmd,
        project_name=project_name,
        progress_callback=progress_callback,
        lock_token=lock_token,
        verify_runtime=True,
    )
    if lock_token:
        update_lock(lock_token, message=_t("version_restart_connecting"), progress=85)
    status["status"] = "restart_scheduled"
    status["status_label"] = _t("version_status_restart_scheduled")
    status["status_tone"] = "success"
    status["can_apply"] = False
    status["can_restart"] = False
    status["reason"] = _t("version_reason_restart_scheduled")
    return status


def apply_update_and_restart(*, progress_callback=None, lock_token=None):
    return apply_update(progress_callback=progress_callback, lock_token=lock_token)
