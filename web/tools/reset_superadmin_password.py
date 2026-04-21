#!/usr/bin/env python3
"""Reset the password of an existing super-admin account."""

from __future__ import annotations

import argparse
import getpass
import os
import sqlite3
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

try:
    from werkzeug.security import generate_password_hash
except ModuleNotFoundError:
    venv_python = ROOT_DIR / ".venv" / "bin" / "python"
    if venv_python.exists() and os.environ.get("VISIO_RESET_BOOTSTRAPPED") != "1":
        env = os.environ.copy()
        env["VISIO_RESET_BOOTSTRAPPED"] = "1"
        os.execve(str(venv_python), [str(venv_python), __file__, *sys.argv[1:]], env)
    raise SystemExit(
        "Werkzeug est introuvable. Lancez le script avec l'environnement virtuel du projet "
        f"({venv_python}) ou installez les dépendances Python."
    )

from constants import DB_FILE, LEGACY_DB_FILE  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Reset the password of an existing super-admin account.",
    )
    parser.add_argument(
        "--user",
        help=(
            "Super-admin username to update. If omitted and there is only one "
            "super-admin, it is selected automatically."
        ),
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List super-admin accounts and exit.",
    )
    parser.add_argument(
        "--password-stdin",
        action="store_true",
        help="Read the new password from standard input instead of prompting interactively.",
    )
    parser.add_argument(
        "--db",
        help="Path to the SQLite database file. Defaults to the project database.",
    )
    return parser


def resolve_db_path(explicit_path: str | None) -> Path:
    if explicit_path:
        db_path = Path(explicit_path).expanduser()
        if not db_path.is_absolute():
            db_path = Path.cwd() / db_path
        return db_path

    candidates = [
        ROOT_DIR / DB_FILE,
        ROOT_DIR / LEGACY_DB_FILE,
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def connect_db(db_path: Path) -> sqlite3.Connection:
    if not db_path.exists():
        raise SystemExit(f"Base de données introuvable : {db_path}")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def list_superadmins(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        "select username from users where superadmin = 1 order by username"
    ).fetchall()
    return [row["username"] for row in rows]


def resolve_target(requested_user: str | None, superadmins: list[str]) -> str:
    if not superadmins:
        raise SystemExit("Aucun compte super-admin n'existe dans la base.")
    if requested_user:
        if requested_user not in superadmins:
            available = ", ".join(superadmins)
            raise SystemExit(
                f'Le compte "{requested_user}" n\'est pas un super-admin connu. '
                f"Comptes disponibles : {available}"
            )
        return requested_user
    if len(superadmins) == 1:
        return superadmins[0]
    available = ", ".join(superadmins)
    raise SystemExit(
        "Plusieurs comptes super-admin existent. "
        f"Précisez --user. Comptes disponibles : {available}"
    )


def read_password_from_prompt() -> str:
    pwd = getpass.getpass("Nouveau mot de passe : ")
    confirm = getpass.getpass("Confirmer le mot de passe : ")
    if pwd != confirm:
        raise SystemExit("Les mots de passe saisis ne correspondent pas.")
    return pwd


def read_password_from_stdin() -> str:
    pwd = sys.stdin.read().rstrip("\r\n")
    if not pwd:
        raise SystemExit("Aucun mot de passe reçu sur l'entrée standard.")
    return pwd


def validate_password(password: str) -> None:
    if len(password) < 10:
        raise SystemExit("Le mot de passe doit contenir au moins 10 caractères.")


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    os.chdir(ROOT_DIR)
    db_path = resolve_db_path(args.db)
    with connect_db(db_path) as conn:
        superadmins = list_superadmins(conn)
        if args.list:
            if not superadmins:
                print("Aucun compte super-admin n'existe dans la base.")
            else:
                print(f"Base : {db_path}")
                print("Comptes super-admin :")
                for username in superadmins:
                    print(f"- {username}")
            return 0

        target_user = resolve_target(args.user, superadmins)
        password = read_password_from_stdin() if args.password_stdin else read_password_from_prompt()
        validate_password(password)

        updated = conn.execute(
            "update users set password_hash = ? where username = ? and superadmin = 1",
            (generate_password_hash(password), target_user),
        )
        if updated.rowcount != 1:
            raise SystemExit(f'Le compte "{target_user}" ne peut pas être modifié.')
        conn.commit()

    print(f'Base : {db_path}')
    print(f'Mot de passe mis à jour pour le super-admin "{target_user}".')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
