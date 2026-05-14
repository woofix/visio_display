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

from services.system_lock_svc import update_lock
from services.version_svc import _compare_versions


SERVICE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_REPO_CWD = os.path.normpath(os.path.join(SERVICE_DIR, "..", ".."))
UPDATE_STEPS = [
    ("pull", "Téléchargement / pull"),
    ("stop", "Arrêt des services"),
    ("restart", "Redémarrage Docker"),
    ("containers", "Vérification des conteneurs"),
    ("app", "Vérification de l'application"),
]


def _step_payload(active_stage, *, failed_stage=None):
    payload = []
    active_index = next((index for index, item in enumerate(UPDATE_STEPS) if item[0] == active_stage), 0)
    failed_index = next((index for index, item in enumerate(UPDATE_STEPS) if item[0] == failed_stage), None)
    for key, label in UPDATE_STEPS:
        index = next(index for index, item in enumerate(UPDATE_STEPS) if item[0] == key)
        if failed_index is not None and index == failed_index:
            state = "failed"
        elif failed_index is not None:
            state = "done" if index < failed_index else "pending"
        elif index == active_index:
            state = "active"
        else:
            state = "done" if index < active_index else "pending"
        payload.append({"key": key, "label": label, "state": state})
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
    compose_cmd = compose_cmd or _docker_compose_command()[0]
    project_name = project_name if project_name is not None else _current_compose_project_name()
    checks = []

    services = _compose_services(compose_cmd, project_name)
    containers, compose_error = _compose_containers(compose_cmd, project_name)
    by_service = {_container_service_name(item): item for item in containers if _container_service_name(item)}

    if compose_error:
        checks.append({"key": "containers", "label": "Conteneurs Docker", "ok": False, "detail": compose_error})
    else:
        expected_services = services or ["app", "worker", "postgres", "redis"]
        missing = [service for service in expected_services if service not in by_service]
        stopped = [service for service in expected_services if service in by_service and not _container_is_running(by_service[service])]
        if missing or stopped:
            detail_parts = []
            if missing:
                detail_parts.append("manquants: " + ", ".join(missing))
            if stopped:
                detail_parts.append("arrêtés: " + ", ".join(stopped))
            checks.append({"key": "containers", "label": "Conteneurs running", "ok": False, "detail": "; ".join(detail_parts)})
        else:
            checks.append({"key": "containers", "label": "Conteneurs running", "ok": True, "detail": ", ".join(expected_services)})

        unhealthy = [
            service for service in expected_services
            if service in by_service and not _container_health_ok(by_service[service])
        ]
        if unhealthy:
            checks.append({"key": "healthchecks", "label": "Healthchecks Docker", "ok": False, "detail": ", ".join(unhealthy)})
        else:
            checks.append({"key": "healthchecks", "label": "Healthchecks Docker", "ok": True, "detail": "OK"})

    http_url = app_url or _app_health_url()
    http_ready, http_detail = _http_ok(http_url)
    checks.append({
        "key": "http",
        "label": "Réponse HTTP de l'application",
        "ok": http_ready,
        "detail": http_detail,
    })

    ready = all(item["ok"] for item in checks)
    return {"ready": ready, "checks": checks, "checked_at": time.time()}


def wait_for_runtime_ready(*, lock_token=None, timeout_seconds=420, interval_seconds=3):
    deadline = time.time() + max(30, int(timeout_seconds))
    compose_cmd, compose_error = _docker_compose_command()
    project_name = _current_compose_project_name()
    if not compose_cmd:
        _update_step(lock_token, "containers", compose_error, progress=85, failed=True)
        raise RuntimeError(compose_error)

    last_detail = "En attente des conteneurs..."
    while time.time() < deadline:
        status = runtime_readiness_status(compose_cmd=compose_cmd, project_name=project_name)
        failing = [item for item in status["checks"] if not item["ok"]]
        if not failing:
            _update_step(lock_token, "app", "Application disponible.", progress=100)
            return status

        first = failing[0]
        stage = "app" if first["key"] == "http" else "containers"
        last_detail = f"{first['label']}: {first.get('detail') or 'en attente'}"
        _update_step(lock_token, stage, last_detail, progress=88 if stage == "containers" else 94)
        time.sleep(max(1, int(interval_seconds)))

    _update_step(lock_token, "app", f"Timeout de redémarrage: {last_detail}", progress=100, failed=True)
    raise RuntimeError(f"Le redémarrage prend trop longtemps. Dernier état: {last_detail}")


def _shell_join(command):
    return " ".join(shlex.quote(str(part)) for part in command)


def _start_restart_helper(command, *, repo_dir, compose_cmd, project_name, progress_callback=None, lock_token=None, verify_runtime=False):
    helper_name = f"visio-display-restart-{int(time.time())}"
    restart_command = _shell_join(command)
    helper_pythonpath = f"{repo_dir}/web:/app"
    helper_lines = [
        "sleep 2",
        f"cd {shlex.quote(repo_dir)}",
        f"{restart_command}",
        "status=$?",
    ]
    if verify_runtime:
        wait_code = (
            "from services.update_svc import wait_for_runtime_ready; "
            f"wait_for_runtime_ready(lock_token={lock_token!r})"
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
            "from services.system_lock_svc import update_lock; "
            "from services.update_svc import _step_payload; "
            f"update_lock({lock_token!r}, message='Le redemarrage Docker a echoue ou a expire.', "
            "progress=100, stage='restart', steps=_step_payload('restart', failed_stage='restart'), "
            "error=True, timeout_seconds=1800)"
        )
        helper_lines.extend([
            f"cd {shlex.quote(repo_dir)}",
            "if [ \"$status\" -eq 0 ]; then",
            f"  PYTHONPATH={shlex.quote(helper_pythonpath)} python -c {shlex.quote(success_cleanup)} || true",
            "else",
            f"  PYTHONPATH={shlex.quote(helper_pythonpath)} python -c {shlex.quote(failure_cleanup)} || true",
            "fi",
            "exit $status",
        ])
    helper_script = "\n".join(helper_lines)
    helper_command = [
        *_with_compose_project(compose_cmd, project_name),
        "run",
        "-d",
        "--rm",
        "--name",
        helper_name,
        "--no-deps",
        "app",
        "sh",
        "-lc",
        helper_script,
    ]
    if progress_callback:
        progress_callback(f"$ {' '.join(helper_command[:8])} ...")
    result = _run(helper_command, cwd=repo_dir, timeout=20)
    if not result.ok:
        raise RuntimeError(result.stderr or result.stdout or "Impossible de lancer le conteneur de redémarrage.")
    if progress_callback:
        progress_callback(f"Redémarrage Docker lancé via helper {helper_name}.")


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
        "status_label": "Installation incompatible",
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


def get_update_status(*, fetch_remote=False):
    repo_dir = _repo_dir()
    checks = []

    def add_check(key, label, ok, detail=""):
        checks.append({"key": key, "label": label, "ok": bool(ok), "detail": detail})

    if not os.path.isdir(repo_dir):
        add_check("repo_dir", "Dossier d'installation", False, repo_dir)
        return _build_incompatible("Le dossier d'installation est introuvable.", checks)
    add_check("repo_dir", "Dossier d'installation", True, repo_dir)

    if not os.path.isdir(os.path.join(repo_dir, ".git")):
        add_check("git_dir", "Dépôt Git", False, ".git introuvable")
        return _build_incompatible("Le dossier Git est introuvable. La mise à jour ne peut pas recloner le dépôt.", checks)
    add_check("git_dir", "Dépôt Git", True)

    remote_name = os.environ.get("VISIO_UPDATE_REMOTE", "origin").strip() or "origin"
    target_branch = _update_branch()
    remote_url = _git(["remote", "get-url", remote_name])
    if not remote_url.ok or not remote_url.stdout.strip():
        add_check("remote", "Remote Git", False, remote_url.stderr or f"remote {remote_name} introuvable")
        return _build_incompatible("Aucun remote Git utilisable n'est configuré.", checks)
    add_check("remote", "Remote Git", True, f"{remote_name}: {remote_url.stdout.strip()}")

    ref_type, ref_name, ref_error = _current_ref()
    if ref_error:
        add_check("current_ref", "Branche ou tag courant", False, ref_error)
        return _build_incompatible(ref_error, checks)
    add_check("current_ref", "Branche ou tag courant", True, f"{ref_type}: {ref_name}")
    add_check("target_branch", "Branche cible de mise à jour", True, target_branch)
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
        add_check("git_clean", "État Git propre", False, status.stderr or "état Git illisible")
        return _build_incompatible("L'état Git est illisible.", checks, status_context)
    git_state = "dirty" if status.stdout.strip() else "clean"
    if git_state != "clean":
        add_check("git_clean", "État Git propre", False, status.stdout)
        return _build_incompatible(
            "Des changements locaux sont présents. Rien ne sera écrasé sans confirmation explicite.",
            checks,
            {**status_context, "git_state": git_state, "git_status": status.stdout},
        )
    add_check("git_clean", "État Git propre", True, "aucun changement local")

    update_script = os.path.join(repo_dir, "scripts", "update.sh")
    if not os.path.isfile(update_script):
        add_check("update_script", "Script de mise à jour", False, "scripts/update.sh introuvable")
        return _build_incompatible("Le script scripts/update.sh est introuvable.", checks, status_context)
    add_check("update_script", "Script de mise à jour", True, "scripts/update.sh")

    compose_cmd, compose_error = _docker_compose_command()
    if not compose_cmd:
        add_check("docker_compose", "Docker Compose", False, compose_error)
        return _build_incompatible(compose_error, checks, status_context)
    add_check("docker_compose", "Docker Compose", True, " ".join(os.path.basename(part) for part in compose_cmd))

    if fetch_remote:
        fetch = _git(["fetch", remote_name, "--tags", "--prune"], timeout=60)
        if not fetch.ok:
            add_check("git_fetch", "Récupération distante", False, fetch.stderr or fetch.stdout)
            return _build_incompatible(
                "Impossible de récupérer les informations distantes du dépôt.",
                checks,
                status_context,
            )
        add_check("git_fetch", "Récupération distante", True, fetch.stdout or "références mises à jour")

    remote_ref = ""
    remote_commit = ""
    remote_version = ""
    target = ""

    if ref_type == "branch":
        remote_ref = _remote_ref_for_branch(remote_name, target_branch)
        if not remote_ref:
            return _build_incompatible(
                "La branche cible de mise à jour n'a pas de branche distante lisible.",
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
        status_label = "Mise à jour disponible"
        status_tone = "warning"
        can_apply = True
        reason = ""
    elif version_comparison < 0:
        status_name = "local_ahead"
        status_label = "Version locale en avance"
        status_tone = "info"
        can_apply = False
        reason = "La version distante de la branche cible est plus ancienne que la version locale."
    else:
        if not remote_commit or not local_commit or remote_commit == local_commit:
            if branch_switch_required:
                status_name = "branch_switch_required"
                status_label = "Changement de branche requis"
                status_tone = "warning"
                can_apply = True
                reason = f"La branche courante est {ref_name}, mais la branche cible est {target_branch}."
            else:
                status_name = "up_to_date"
                status_label = "À jour"
                status_tone = "success"
                can_apply = False
                reason = ""
        elif _commit_is_ancestor(local_commit, remote_commit):
            status_name = "update_available"
            status_label = "Mise à jour disponible"
            status_tone = "warning"
            can_apply = True
            reason = ""
        elif _commit_is_ancestor(remote_commit, local_commit):
            status_name = "local_ahead"
            status_label = "Version locale en avance"
            status_tone = "info"
            can_apply = False
            reason = "La version est identique, mais le commit local contient déjà le commit distant."
        else:
            status_name = "diverged"
            status_label = "Historique Git divergent"
            status_tone = "info"
            can_apply = False
            reason = "La version est identique, mais les commits local et distant ne sont pas sur le même historique."

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
        raise RuntimeError(f"La commande a échoué avec le code {returncode}.")


def apply_update(*, progress_callback=None, lock_token=None):
    status = get_update_status(fetch_remote=True)
    if not status.get("compatible"):
        raise RuntimeError(status.get("reason") or "Installation incompatible.")
    if not status.get("can_apply"):
        raise RuntimeError("Aucune mise à jour n'est disponible.")

    repo_dir = status["repo_dir"]
    _update_step(lock_token, "pull", "Téléchargement et application depuis le dépôt Git...", progress=20)
    env = os.environ.copy()
    if status.get("target_branch"):
        env["VISIO_UPDATE_BRANCH"] = status["target_branch"]
    command = ["bash", os.path.join(repo_dir, "scripts", "update.sh")]
    if status.get("current_ref_type") == "tag" and status.get("target"):
        command.append(status["target"])
    _stream_command(command, cwd=repo_dir, env=env, progress_callback=progress_callback)
    if lock_token:
        _update_step(lock_token, "stop", "Mise à jour appliquée. Préparation du redémarrage Docker...", progress=58)
    refreshed = get_update_status(fetch_remote=False)
    refreshed["status"] = "restart_required"
    refreshed["status_label"] = "Redémarrage requis"
    refreshed["status_tone"] = "warning"
    refreshed["can_restart"] = True
    return refreshed


def restart_stack(*, progress_callback=None, lock_token=None):
    status = get_update_status(fetch_remote=False)
    if not status.get("compatible"):
        raise RuntimeError(status.get("reason") or "Installation incompatible.")
    compose_cmd, compose_error = _docker_compose_command()
    if not compose_cmd:
        raise RuntimeError(compose_error)
    project_name = _current_compose_project_name()
    command = [*_with_compose_project(compose_cmd, project_name), "up", "-d", "--build"]
    _update_step(lock_token, "restart", "Redémarrage Docker en cours...", progress=72, timeout_seconds=900)
    if progress_callback:
        progress_callback("Le redémarrage va continuer en arrière-plan.")
        progress_callback(f"$ {' '.join(command)}")
    if lock_token:
        update_lock(lock_token, message="Redémarrage Docker en arrière-plan...", progress=60)
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
        update_lock(lock_token, message="Redémarrage Docker lancé. Connexion au serveur...", progress=85)
    status["status"] = "restart_scheduled"
    status["status_label"] = "Redémarrage lancé"
    status["status_tone"] = "success"
    status["can_apply"] = False
    status["can_restart"] = False
    status["reason"] = "La stack Docker redémarre en arrière-plan. Rechargez la page dans quelques secondes."
    return status


def apply_update_and_restart(*, progress_callback=None, lock_token=None):
    apply_update(progress_callback=progress_callback, lock_token=lock_token)
    return restart_stack(progress_callback=progress_callback, lock_token=lock_token)
