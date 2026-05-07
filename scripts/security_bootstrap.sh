#!/bin/bash
# Licensed under the GNU General Public License v3.0 (GPL-3.0). Copyright (c) 2026 Eric TOMAS (Woofix). See the LICENSE file for details.

set -u

MODE="${1:-}"
INSTALL_DIR="${2:-${VISIO_INSTALL_DIR:-$(pwd)}}"
ENV_FILE="${VISIO_ENV_FILE:-$INSTALL_DIR/.env}"
PLACEHOLDER_SECRET="replace_with_a_random_string"
DEFAULT_MEDIA_DIR="$INSTALL_DIR/media"
DEFAULT_PRIVATE_DIR="$INSTALL_DIR/private"
DEFAULT_HOST_ROOT="$INSTALL_DIR"

OK_COUNT=0
FIXED_COUNT=0
WARNING_COUNT=0
ERROR_COUNT=0

ok() {
    OK_COUNT=$((OK_COUNT + 1))
    echo "OK: $1"
}

fixed() {
    FIXED_COUNT=$((FIXED_COUNT + 1))
    echo "fixed: $1"
}

warning() {
    WARNING_COUNT=$((WARNING_COUNT + 1))
    echo "warning: $1" >&2
}

error() {
    ERROR_COUNT=$((ERROR_COUNT + 1))
    echo "erreur: $1" >&2
}

usage() {
    echo "Usage: $0 install|update|check [install_dir]" >&2
}

if [ "$MODE" != "install" ] && [ "$MODE" != "update" ] && [ "$MODE" != "check" ]; then
    usage
    exit 2
fi

if [ "$MODE" != "check" ]; then
    mkdir -p "$INSTALL_DIR" 2>/dev/null || {
        error "cannot create install directory: $INSTALL_DIR"
        exit 1
    }
fi

ensure_env_file() {
    if [ -f "$ENV_FILE" ]; then
        ok ".env file found: $ENV_FILE"
        return 0
    fi
    if [ "$MODE" = "check" ]; then
        warning ".env file missing: $ENV_FILE"
        return 1
    fi
    : > "$ENV_FILE" 2>/dev/null || {
        error "cannot create $ENV_FILE"
        return 1
    }
    fixed ".env file created: $ENV_FILE"
}

env_value() {
    key="$1"
    [ -f "$ENV_FILE" ] || return 0
    awk -v key="$key" '
        $0 ~ "^[[:space:]]*" key "=" {
            sub("^[[:space:]]*" key "=", "")
            print
            exit
        }
    ' "$ENV_FILE"
}

env_has_key() {
    key="$1"
    [ -f "$ENV_FILE" ] && grep -Eq "^[[:space:]]*${key}=" "$ENV_FILE"
}

set_env_value() {
    key="$1"
    value="$2"
    tmp_file="$(mktemp)"

    if env_has_key "$key"; then
        awk -v key="$key" -v value="$value" '
            BEGIN { updated = 0 }
            $0 ~ "^[[:space:]]*" key "=" && updated == 0 {
                print key "=" value
                updated = 1
                next
            }
            { print }
        ' "$ENV_FILE" > "$tmp_file"
    else
        awk '1' "$ENV_FILE" > "$tmp_file"
        printf '%s=%s\n' "$key" "$value" >> "$tmp_file"
    fi

    if ! cat "$tmp_file" > "$ENV_FILE"; then
        rm -f "$tmp_file"
        return 1
    fi
    rm -f "$tmp_file"
}

generate_secret() {
    if command -v python3 >/dev/null 2>&1; then
        python3 -c 'import secrets; print(secrets.token_urlsafe(48))'
    elif command -v python >/dev/null 2>&1; then
        python -c 'import secrets; print(secrets.token_urlsafe(48))'
    elif command -v openssl >/dev/null 2>&1; then
        openssl rand -base64 48 | tr -d '\n'
        echo
    else
        return 1
    fi
}

is_weak_secret_key() {
    value="${1:-}"
    [ -z "$value" ] && return 0
    [ "$value" = "$PLACEHOLDER_SECRET" ] && return 0
    [ "$value" = "change-me" ] && return 0
    [ "$value" = "changeme" ] && return 0
    [ "$value" = "secret" ] && return 0
    [ "$value" = "test-secret-key" ] && return 0
    return 1
}

is_weak_postgres_password() {
    value="${1:-}"
    [ -z "$value" ] && return 0
    [ "$value" = "visio" ] && return 0
    [ "$value" = "postgres" ] && return 0
    [ "$value" = "password" ] && return 0
    [ ${#value} -lt 10 ] && return 0
    return 1
}

ensure_secret_key() {
    key="$1"
    label="$2"
    value="$(env_value "$key")"

    if env_has_key "$key"; then
        if [ -n "$value" ]; then
            ok "$label present"
        else
            warning "$label present but empty; existing value kept"
        fi
        return 0
    fi
    if [ "$MODE" = "check" ]; then
        warning "$label missing"
        return 0
    fi

    generated_value="$(generate_secret)" || {
        error "cannot generate $label"
        return 1
    }
    set_env_value "$key" "$generated_value" || {
        error "cannot write $label to $ENV_FILE"
        return 1
    }
    fixed "$label generated"
}

ensure_optional_generated_key() {
    key="$1"
    label="$2"
    value="$(env_value "$key")"

    if env_has_key "$key"; then
        ok "$label present"
        return 0
    fi
    if [ "$MODE" = "check" ]; then
        warning "$label missing"
        return 0
    fi

    generated_value="$(generate_secret)" || {
        error "cannot generate $label"
        return 1
    }
    set_env_value "$key" "$generated_value" || {
        error "cannot write $label to $ENV_FILE"
        return 1
    }
    fixed "$label generated"
}

ensure_required_path() {
    key="$1"
    label="$2"
    default_value="$3"
    value="$(env_value "$key")"

    if env_has_key "$key" && [ -n "$value" ]; then
        ok "$label present: $value"
        return 0
    fi
    if [ "$MODE" = "check" ]; then
        error "$label missing; renseignez $key dans $ENV_FILE"
        return 1
    fi

    set_env_value "$key" "$default_value" || {
        error "cannot write $label to $ENV_FILE"
        return 1
    }
    fixed "$label added: $default_value"
}

ensure_host_root() {
    value="$(env_value VISIO_HOST_ROOT)"

    if env_has_key "VISIO_HOST_ROOT" && [ -n "$value" ]; then
        ok "VISIO_HOST_ROOT present: $value"
        return 0
    fi
    if [ "$MODE" = "check" ]; then
        warning "VISIO_HOST_ROOT missing; Docker restart from the admin may fail"
        return 0
    fi

    set_env_value "VISIO_HOST_ROOT" "$DEFAULT_HOST_ROOT" || {
        error "cannot write VISIO_HOST_ROOT to $ENV_FILE"
        return 1
    }
    fixed "VISIO_HOST_ROOT added: $DEFAULT_HOST_ROOT"
}

ensure_permissions() {
    if [ -f "$ENV_FILE" ]; then
        if chmod 600 "$ENV_FILE" 2>/dev/null; then
            ok ".env permissions set to 600"
        else
            warning "cannot apply chmod 600 to $ENV_FILE"
        fi
    fi

    media_dir="$(env_value MEDIA_DIR)"
    private_dir="$(env_value PRIVATE_DIR)"

    if [ -z "$media_dir" ]; then
        if [ "$MODE" = "check" ]; then
            error "MEDIA_DIR missing; cannot prepare media directory"
        else
            media_dir="$DEFAULT_MEDIA_DIR"
        fi
    fi
    if [ -z "$private_dir" ]; then
        if [ "$MODE" = "check" ]; then
            error "PRIVATE_DIR missing; cannot prepare private directory"
            return 1
        else
            private_dir="$DEFAULT_PRIVATE_DIR"
        fi
    fi

    if [ -n "$media_dir" ]; then
        if [ -d "$media_dir" ]; then
            ok "MEDIA_DIR exists: $media_dir"
        elif mkdir -p "$media_dir" 2>/dev/null; then
            fixed "MEDIA_DIR created: $media_dir"
        else
            if [ "$MODE" = "check" ]; then
                warning "cannot create $media_dir"
            else
                error "cannot create $media_dir"
            fi
        fi
    fi

    backups_dir="${private_dir%/}/backups"

    if [ -d "$backups_dir" ]; then
        ok "backups directory exists: $backups_dir"
    elif mkdir -p "$backups_dir" 2>/dev/null; then
        fixed "backups directory created: $backups_dir"
    else
        if [ "$MODE" = "check" ]; then
            warning "cannot create $backups_dir"
        else
            error "cannot create $backups_dir"
        fi
    fi

    if [ -d "$private_dir" ]; then
        if chmod 700 "$private_dir" 2>/dev/null; then
            ok "PRIVATE_DIR permissions set to 700"
        else
            warning "cannot apply chmod 700 to $private_dir"
        fi
    fi

    if [ -d "$backups_dir" ]; then
        if chmod 700 "$backups_dir" 2>/dev/null; then
            ok "backups permissions set to 700"
        else
            warning "cannot apply chmod 700 to $backups_dir"
        fi
    fi
}

ensure_env_file || true

if [ -f "$ENV_FILE" ]; then
    ensure_secret_key "SECRET_KEY" "SECRET_KEY"
    ensure_secret_key "POSTGRES_PASSWORD" "POSTGRES_PASSWORD"
    ensure_secret_key "DISPLAY_API_TOKEN" "DISPLAY_API_TOKEN"
    ensure_optional_generated_key "CLIENT_HEARTBEAT_TOKEN" "CLIENT_HEARTBEAT_TOKEN"
    ensure_host_root
    ensure_required_path "MEDIA_DIR" "MEDIA_DIR" "$DEFAULT_MEDIA_DIR"
    ensure_required_path "PRIVATE_DIR" "PRIVATE_DIR" "$DEFAULT_PRIVATE_DIR"

    secret_key="$(env_value SECRET_KEY)"
    postgres_password="$(env_value POSTGRES_PASSWORD)"
    display_api_token="$(env_value DISPLAY_API_TOKEN)"

    if is_weak_secret_key "$secret_key"; then
        if [ "$MODE" = "install" ]; then
            error "SECRET_KEY is empty or uses a placeholder value"
        else
            warning "SECRET_KEY is empty or uses a placeholder value; existing value kept"
        fi
    else
        ok "SECRET_KEY is strong"
    fi

    if is_weak_postgres_password "$postgres_password"; then
        if [ "$MODE" = "install" ]; then
            error "POSTGRES_PASSWORD is missing, too short, or uses a weak value"
        else
            warning "POSTGRES_PASSWORD is missing, too short, or uses a weak value; existing value kept"
        fi
    else
        ok "POSTGRES_PASSWORD is strong"
    fi

    if [ -z "$display_api_token" ]; then
        error "DISPLAY_API_TOKEN is mandatory and cannot be empty"
    else
        ok "DISPLAY_API_TOKEN is present"
    fi
fi

ensure_permissions

echo "Security report: OK=$OK_COUNT fixed=$FIXED_COUNT warning=$WARNING_COUNT error=$ERROR_COUNT"

if [ "$ERROR_COUNT" -gt 0 ]; then
    exit 1
fi

exit 0
