# Licensed under the GNU General Public License v3.0 (GPL-3.0). Copyright (c) 2026 Eric TOMAS (Woofix). See the LICENSE file for details.

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
        "Python dependencies not found. Run the script with the project virtual environment "
        f"({venv_python}) or install the Python dependencies."
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
        "DATABASE_URL is required. This project now requires PostgreSQL."
    )


def list_superadmins() -> list[str]:
    rows = User.query.filter_by(superadmin=True).order_by(User.username).all()
    return [row.username for row in rows]


def resolve_target(requested_user: str | None, superadmins: list[str]) -> str:
    if not superadmins:
        raise SystemExit("No super-admin account exists in the database.")
    if requested_user:
        if requested_user not in superadmins:
            available = ", ".join(superadmins)
            raise SystemExit(
                f'Account "{requested_user}" is not a known super-admin. '
                f"Available accounts: {available}"
            )
        return requested_user
    if len(superadmins) == 1:
        return superadmins[0]
    available = ", ".join(superadmins)
    raise SystemExit(
        "Multiple super-admin accounts exist. "
        f"Specify --user. Available accounts: {available}"
    )


def read_password_from_prompt() -> str:
    pwd = getpass.getpass("New password: ")
    confirm = getpass.getpass("Confirm password: ")
    if pwd != confirm:
        raise SystemExit("Passwords do not match.")
    return pwd


def read_password_from_stdin() -> str:
    pwd = sys.stdin.read().rstrip("\r\n")
    if not pwd:
        raise SystemExit("No password received on standard input.")
    return pwd


def validate_password(password: str) -> None:
    if len(password) < 10:
        raise SystemExit("Password must be at least 10 characters long.")


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
                print("No super-admin account exists in the database.")
            else:
                print(f"Database: {database_label}")
                print("Super-admin accounts:")
                for username in superadmins:
                    print(f"- {username}")
            return 0

        target_user = resolve_target(args.user, superadmins)
        password = read_password_from_stdin() if args.password_stdin else read_password_from_prompt()
        validate_password(password)

        user = User.query.filter_by(username=target_user, superadmin=True).first()
        if user is None:
            raise SystemExit(f'Account "{target_user}" cannot be modified.')
        get_redis().ping()
        set_user_password(target_user, password)

    print(f'Database: {database_label}')
    print(f'Redis password updated for super-admin "{target_user}".')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
