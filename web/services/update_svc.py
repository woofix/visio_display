# Licensed under the GNU General Public License v3.0 (GPL-3.0). Copyright (c) 2026 Eric TOMAS (Woofix). See the LICENSE file for details.

import os
import json
import subprocess
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


SERVICE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_REPO_CWD = os.path.normpath(os.path.join(SERVICE_DIR, "..", ".."))
DEFAULT_VERSION_URL = "https://raw.githubusercontent.com/woofix/visio_display/main/VERSION"
DEFAULT_LATEST_RELEASE_URL = "https://api.github.com/repos/woofix/visio_display/releases/latest"
DEFAULT_TAGS_URL = "https://api.github.com/repos/woofix/visio_display/tags?per_page=100"
DEFAULT_BRANCH_COMMIT_URL = "https://api.github.com/repos/woofix/visio_display/commits/main"


def _run_git(args, cwd, timeout=5):
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError:
        return {"ok": False, "stdout": "", "stderr": "git introuvable", "returncode": 127}
    except subprocess.TimeoutExpired:
        return {"ok": False, "stdout": "", "stderr": "commande git trop longue", "returncode": 124}
    except OSError as exc:
        return {"ok": False, "stdout": "", "stderr": str(exc), "returncode": 1}

    return {
        "ok": result.returncode == 0,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
        "returncode": result.returncode,
    }


def _first_line(value):
    lines = str(value or "").splitlines()
    return lines[0].strip() if lines else ""


def _short_sha(sha):
    return sha[:7] if sha else ""


def _clean_version(version):
    return str(version or "").strip().lstrip("v")


def _version_parts(version):
    parts = []
    for item in _clean_version(version).split("."):
        try:
            parts.append(int(item))
        except ValueError:
            break
    return tuple(parts)


def _compare_versions(local_version, remote_version):
    local_parts = _version_parts(local_version)
    remote_parts = _version_parts(remote_version)
    if not local_parts or not remote_parts:
        return 0
    length = max(len(local_parts), len(remote_parts))
    local_parts = local_parts + (0,) * (length - len(local_parts))
    remote_parts = remote_parts + (0,) * (length - len(remote_parts))
    if remote_parts > local_parts:
        return 1
    if remote_parts < local_parts:
        return -1
    return 0


def _read_local_version():
    env_version = os.environ.get("APP_VERSION", "").strip()
    if env_version:
        return env_version
    version_file = os.path.normpath(os.path.join(DEFAULT_REPO_CWD, "VERSION"))
    try:
        with open(version_file, "r", encoding="utf-8") as handle:
            return handle.read().strip()
    except OSError:
        return ""


def _read_remote_version(timeout=6):
    version_url = os.environ.get("VISIO_UPDATE_VERSION_URL", "").strip() or DEFAULT_VERSION_URL
    try:
        with urlopen(version_url, timeout=timeout) as response:
            return response.read(128).decode("utf-8", errors="replace").strip(), ""
    except HTTPError as exc:
        return "", f"source indisponible ({exc.code})"
    except URLError:
        return "", "source de mise à jour inaccessible"
    except OSError as exc:
        return "", str(exc)


def _read_json_url(url, timeout=6):
    request = Request(url, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": "visio-display-update-check",
    })
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read(8192).decode("utf-8", errors="replace"))


def _read_remote_release_info(timeout=6):
    release_url = (
        os.environ.get("VISIO_UPDATE_LATEST_RELEASE_URL", "").strip()
        or DEFAULT_LATEST_RELEASE_URL
    )
    release_tag_name = ""
    try:
        release = _read_json_url(release_url, timeout=timeout)
        release_tag_name = str(release.get("tag_name", "") or "")
    except HTTPError as exc:
        if exc.code not in {404, 403}:
            return None, f"source indisponible ({exc.code})"
    except (URLError, OSError):
        pass
    except (ValueError, TypeError):
        pass

    tags_url = os.environ.get("VISIO_UPDATE_TAGS_URL", "").strip() or DEFAULT_TAGS_URL
    try:
        tags = _read_json_url(tags_url, timeout=timeout)
        latest_tag = {}
        if isinstance(tags, list) and tags:
            latest_tag = tags[0]
            for tag in tags:
                if release_tag_name and tag.get("name") == release_tag_name:
                    latest_tag = tag
                    break
        tag_name = latest_tag.get("name", "")
        commit = latest_tag.get("commit") if isinstance(latest_tag.get("commit"), dict) else {}
        sha = str(commit.get("sha", "") or "")
        if release_tag_name or tag_name:
            return {
                "version": _clean_version(release_tag_name or tag_name),
                "sha": sha,
                "short_sha": _short_sha(sha),
                "source": "release" if release_tag_name else "tag",
            }, ""
    except HTTPError as exc:
        if exc.code not in {404, 403}:
            return None, f"source indisponible ({exc.code})"
    except (URLError, OSError):
        pass
    except (ValueError, TypeError):
        pass

    if release_tag_name:
        return {
            "version": _clean_version(release_tag_name),
            "sha": "",
            "short_sha": "",
            "source": "release",
        }, ""

    commit_url = (
        os.environ.get("VISIO_UPDATE_BRANCH_COMMIT_URL", "").strip()
        or DEFAULT_BRANCH_COMMIT_URL
    )
    try:
        commit = _read_json_url(commit_url, timeout=timeout)
        sha = str(commit.get("sha", "") or "")
    except (HTTPError, URLError, OSError, ValueError, TypeError):
        sha = ""

    remote_version, error = _read_remote_version(timeout=timeout)
    if error or not remote_version:
        return ({"version": "", "sha": sha, "short_sha": _short_sha(sha), "source": ""}, error)
    return {
        "version": _clean_version(remote_version),
        "sha": sha,
        "short_sha": _short_sha(sha),
        "source": "version_file",
    }, ""


def _version_status(fetch=False, base_info=None):
    info = {
        "status": "unknown",
        "status_label": "Vérification impossible",
        "status_tone": "warning",
        "repo_path": DEFAULT_REPO_CWD,
        "fetch_requested": fetch,
        "fetch_ok": None,
        "fetch_error": "",
        "branch": "",
        "local_sha": "",
        "local_short_sha": "",
        "local_commit_date": "",
        "local_commit_subject": "",
        "tracking_ref": "",
        "remote_sha": "",
        "remote_short_sha": "",
        "ahead": 0,
        "behind": 0,
        "has_local_changes": False,
        "local_version": _read_local_version(),
        "remote_version": "",
        "check_mode": "version",
    }
    if base_info:
        info.update(base_info)

    if not fetch:
        info.update({
            "status": "not_checked",
            "status_label": "Vérification disponible",
            "status_tone": "info",
        })
        return info

    remote_info, error = _read_remote_release_info()
    remote_version = (remote_info or {}).get("version", "")
    info["remote_version"] = remote_version
    info["remote_sha"] = (remote_info or {}).get("sha", "") or info.get("remote_sha", "")
    info["remote_short_sha"] = (
        (remote_info or {}).get("short_sha", "")
        or _short_sha(info.get("remote_sha", ""))
    )
    info["remote_source"] = (remote_info or {}).get("source", "")
    if error or not remote_version:
        info.update({
            "status": "check_failed",
            "status_label": "Vérification impossible",
            "status_tone": "warning",
            "fetch_ok": False,
            "fetch_error": error or "version distante introuvable",
        })
        return info

    info["fetch_ok"] = True
    comparison = _compare_versions(info["local_version"], remote_version)
    if comparison > 0:
        info.update({
            "status": "update_available",
            "status_label": "Mise à jour disponible",
            "status_tone": "success",
            "behind": 1,
        })
    elif comparison < 0:
        info.update({
            "status": "local_ahead",
            "status_label": "Version installée plus récente",
            "status_tone": "info",
        })
    else:
        info.update({
            "status": "up_to_date",
            "status_label": "Visio est à jour",
            "status_tone": "success",
        })
    return info


def get_update_status(fetch=False):
    repo_cwd = os.environ.get("VISIO_GIT_ROOT", "").strip() or DEFAULT_REPO_CWD
    root_result = _run_git(["rev-parse", "--show-toplevel"], repo_cwd, timeout=2)
    if not root_result["ok"]:
        return _version_status(fetch=fetch, base_info={
            "repo_path": repo_cwd,
            "git_unavailable": True,
            "git_error": _first_line(root_result["stderr"]),
        })

    repo_path = root_result["stdout"]
    info = {
        "status": "unknown",
        "status_label": "Vérification impossible",
        "status_tone": "warning",
        "repo_path": repo_path,
        "fetch_requested": fetch,
        "fetch_ok": None,
        "fetch_error": "",
    }

    branch_result = _run_git(["rev-parse", "--abbrev-ref", "HEAD"], repo_path, timeout=2)
    local_sha_result = _run_git(["rev-parse", "HEAD"], repo_path, timeout=2)
    commit_date_result = _run_git(["log", "-1", "--format=%cI"], repo_path, timeout=2)
    commit_subject_result = _run_git(["log", "-1", "--format=%s"], repo_path, timeout=2)
    remotes_result = _run_git(["remote"], repo_path, timeout=2)

    branch = branch_result["stdout"] if branch_result["ok"] else ""
    local_sha = local_sha_result["stdout"] if local_sha_result["ok"] else ""
    remotes = remotes_result["stdout"].splitlines() if remotes_result["ok"] else []
    info.update({
        "branch": branch,
        "local_sha": local_sha,
        "local_short_sha": _short_sha(local_sha),
        "local_commit_date": commit_date_result["stdout"] if commit_date_result["ok"] else "",
        "local_commit_subject": commit_subject_result["stdout"] if commit_subject_result["ok"] else "",
        "remotes": remotes,
        "local_version": _read_local_version(),
        "remote_version": "",
        "check_mode": "git",
    })

    if fetch:
        if remotes:
            fetch_result = _run_git(["fetch", "--prune"], repo_path, timeout=20)
            info["fetch_ok"] = fetch_result["ok"]
            if not fetch_result["ok"]:
                info["fetch_error"] = _first_line(fetch_result["stderr"]) or "git fetch a échoué"
        else:
            return _version_status(fetch=True, base_info={
                **info,
                "check_mode": "version",
                "git_unavailable": False,
                "git_error": "aucun dépôt distant configuré",
            })

    dirty_result = _run_git(["status", "--porcelain"], repo_path, timeout=3)
    info["has_local_changes"] = bool(dirty_result["stdout"]) if dirty_result["ok"] else False

    tracking_result = _run_git(
        ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"],
        repo_path,
        timeout=2,
    )
    tracking_ref = tracking_result["stdout"] if tracking_result["ok"] else ""
    if not tracking_ref and branch and branch != "HEAD" and "origin" in remotes:
        candidate = f"origin/{branch}"
        candidate_result = _run_git(["rev-parse", "--verify", candidate], repo_path, timeout=2)
        if candidate_result["ok"]:
            tracking_ref = candidate

    info["tracking_ref"] = tracking_ref
    if not tracking_ref:
        return _version_status(fetch=fetch, base_info={
            **info,
            "check_mode": "version",
            "git_unavailable": False,
            "git_error": "branche distante non configurée",
        })

    remote_sha_result = _run_git(["rev-parse", tracking_ref], repo_path, timeout=2)
    remote_sha = remote_sha_result["stdout"] if remote_sha_result["ok"] else ""
    remote_version_result = _run_git(["show", f"{tracking_ref}:VERSION"], repo_path, timeout=2)
    info.update({
        "remote_sha": remote_sha,
        "remote_short_sha": _short_sha(remote_sha),
        "remote_version": _clean_version(remote_version_result["stdout"]) if remote_version_result["ok"] else "",
        "remote_source": "git",
    })

    counts_result = _run_git(["rev-list", "--left-right", "--count", f"HEAD...{tracking_ref}"], repo_path, timeout=3)
    ahead = 0
    behind = 0
    if counts_result["ok"]:
        parts = counts_result["stdout"].split()
        if len(parts) == 2:
            ahead = int(parts[0])
            behind = int(parts[1])
    info.update({"ahead": ahead, "behind": behind})

    if info["has_local_changes"]:
        info.update({
            "status": "local_modified",
            "status_label": "Modifications locales détectées",
            "status_tone": "warning",
        })
    elif ahead and behind:
        info.update({
            "status": "diverged",
            "status_label": "Versions divergentes",
            "status_tone": "warning",
        })
    elif ahead:
        info.update({
            "status": "local_ahead",
            "status_label": "Version locale en avance",
            "status_tone": "info",
        })
    elif behind:
        info.update({
            "status": "update_available",
            "status_label": "Mise à jour disponible",
            "status_tone": "success",
        })
    else:
        info.update({
            "status": "up_to_date",
            "status_label": "Visio est à jour",
            "status_tone": "success",
        })

    if fetch and info["fetch_ok"] is False and info["status"] in {"unknown", "up_to_date"}:
        info.update({
            "status": "check_failed",
            "status_label": "Vérification impossible",
            "status_tone": "warning",
        })

    return info
