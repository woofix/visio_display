# MIT License - Copyright (c) 2026 Woofix
# See LICENSE file for details

#!/usr/bin/env python3
"""Reset the password of an existing super-admin account."""

from __future__ import annotations

import argparse
import getpass
import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

try:
    from app import create_app
    from db import User
    from services.queue_svc import get_redis
    from services.users_svc import set_user_password
except ModuleNotFoundError:
    venv_python = ROOT_DIR / ".venv" / "bin" / "python"
    if venv_python.exists() and os.environ.get("VISIO_RESET_BOOTSTRAPPED") != "1":
        env = os.environ.copy()
        env["VISIO_RESET_BOOTSTRAPPED"] = "1"
        os.execve(str(venv_python), [str(venv_python), __file__, *sys.argv[1:]], env)
    raise SystemExit(
        "Les dépendances Python sont introuvables. Lancez le script avec l'environnement virtuel du projet "
        f"({venv_python}) ou installez les dépendances Python."
    )

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
        "--database-url",
        help=(
            "Full SQLAlchemy database URL override. "
            "Useful for PostgreSQL deployments in Docker."
        ),
    )
    return parser


def configure_database_env(database_url: str | None) -> str:
    if database_url:
        os.environ["DATABASE_URL"] = database_url
        return database_url

    current = os.environ.get("DATABASE_URL", "").strip()
    if current:
        return current

    raise SystemExit(
        "DATABASE_URL est obligatoire. Ce projet fonctionne maintenant uniquement avec PostgreSQL."
    )


def list_superadmins() -> list[str]:
    rows = User.query.filter_by(superadmin=True).order_by(User.username).all()
    return [row.username for row in rows]


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
    database_label = configure_database_env(args.database_url)
    app = create_app(start_scheduler=False)
    with app.app_context():
        superadmins = list_superadmins()
        if args.list:
            if not superadmins:
                print("Aucun compte super-admin n'existe dans la base.")
            else:
                print(f"Base : {database_label}")
                print("Comptes super-admin :")
                for username in superadmins:
                    print(f"- {username}")
            return 0

        target_user = resolve_target(args.user, superadmins)
        password = read_password_from_stdin() if args.password_stdin else read_password_from_prompt()
        validate_password(password)

        user = User.query.filter_by(username=target_user, superadmin=True).first()
        if user is None:
            raise SystemExit(f'Le compte "{target_user}" ne peut pas être modifié.')
        get_redis().ping()
        set_user_password(target_user, password)

    print(f'Base : {database_label}')
    print(f'Mot de passe Redis mis à jour pour le super-admin "{target_user}".')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
