#!/usr/bin/env bash
# Native deployment only. Run explicitly with sudo bash deploy/manage.sh ACTION.
set -euo pipefail
umask 077

fail() { printf '%s\n' "$*" >&2; exit 1; }
[[ $(id -u) == 0 ]] || fail 'Run with sudo.'
[[ $(uname -s) == Linux ]] || fail 'Linux is required.'
action=${1:-}
case "$action" in install|upgrade|backup|rollback|uninstall) ;; *) fail 'Use install, upgrade, backup, rollback BACKUP_DIRECTORY, or uninstall.' ;; esac
app=/opt/pitboss-admin
config=/etc/pitboss-admin
state=/var/lib/pitboss-admin
backups=/var/backups/pitboss-admin
unit=/etc/systemd/system/pitboss-admin.service
for directory in "$app" "$app/releases" "$config" "$state" "$backups"; do
    [[ ! -L "$directory" ]] || fail "Refusing symlink directory: $directory"
done
for file in "$state/state.sqlite3" "$config/config.yaml" "$config/environment" "$unit"; do
    [[ ! -L "$file" ]] || fail "Refusing symlink managed file: $file"
done
if [[ -e "$app/current" && ! -L "$app/current" ]]; then
    fail 'current must be a managed release symlink.'
fi
for program in python3 systemctl runuser bluetoothctl flock; do
    command -v "$program" >/dev/null || fail "Missing prerequisite: $program"
done
exec 9>/run/lock/pitboss-admin-deploy.lock
flock -n 9 || fail 'Another deployment operation is running.'

validate_release() {
    local resolved
    resolved=$(realpath -e "$1")
    [[ "$resolved" == "$app/releases/"* && -x "$resolved/venv/bin/pitboss-api" ]] || fail 'Invalid managed release.'
    printf '%s' "$resolved"
}

backup() {
    local current
    current=$(validate_release "$app/current")
    install -d -m 0700 "$backups"
    backup_dir=$(mktemp -d "$backups/backup-XXXXXXXX")
    "$current/venv/bin/pitboss-state" backup "$state/state.sqlite3" "$backup_dir/state.sqlite3"
    cp -a "$config" "$backup_dir/config"
    cp "$unit" "$backup_dir/pitboss-admin.service"
    printf '%s\n' "$current" > "$backup_dir/release"
    printf 'Protected backup: %s\n' "$backup_dir"
}

restore() {
    local source=$1 previous
    source=$(realpath -e "$source")
    [[ "$source" == "$backups/backup-"* && -f "$source/state.sqlite3" && -f "$source/release" ]] || fail 'Invalid backup directory.'
    previous=$(validate_release "$(< "$source/release")")
    # Verify before replacing any live file. The service must already be stopped.
    "$previous/venv/bin/python" -c 'import sqlite3,sys; c=sqlite3.connect("file:"+sys.argv[1]+"?mode=ro",uri=True); assert c.execute("pragma integrity_check").fetchone()==("ok",); c.close()' "$source/state.sqlite3"
    install -o pitboss-admin -g pitboss-admin -m 0600 "$source/state.sqlite3" "$state/state.sqlite3"
    install -o root -g pitboss-admin -m 0640 "$source/config/config.yaml" "$config/config.yaml"
    install -o root -g pitboss-admin -m 0640 "$source/config/environment" "$config/environment"
    install -o root -g root -m 0644 "$source/pitboss-admin.service" "$unit"
    ln -sfn "$previous" "$app/current"
    systemctl daemon-reload
}

case "$action" in
    backup)
        # SQLite snapshot is consistent while running. Avoid simultaneous config changes.
        backup
        exit 0
        ;;
    uninstall)
        systemctl disable --now pitboss-admin.service
        if [[ -f "$unit" ]]; then
            mv "$unit" "$app/pitboss-admin.service.disabled.$(date -u +%Y%m%dT%H%M%SZ)"
        fi
        systemctl daemon-reload
        printf 'Service uninstalled. Account, releases, configuration, state and backups preserved.\n'
        exit 0
        ;;
    rollback)
        [[ -n ${2:-} ]] || fail 'Supply the exact protected backup directory.'
        # Validate the requested target before stopping service.
        target=$(realpath -e "$2")
        [[ "$target" == "$backups/backup-"* && -f "$target/release" ]] || fail 'Invalid backup directory.'
        validate_release "$(< "$target/release")" >/dev/null
        systemctl stop pitboss-admin.service
        backup
        restore "$target"
        systemctl start pitboss-admin.service
        printf 'Rollback started. Verify health, authentication and physical readings.\n'
        exit 0
        ;;
esac

source_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)
[[ -f "$source_dir/pyproject.toml" ]] || fail 'Run from the unpacked source release.'
if [[ "$action" == install ]]; then
    [[ ! -e "$app/current" && ! -L "$app/current" && ! -e "$state/state.sqlite3" && ! -e "$unit" ]] || fail 'Existing deployment detected; use upgrade or restore it explicitly.'
    [[ -t 1 ]] || fail 'Installation requires a terminal for one-time token display.'
else
    validate_release "$app/current" >/dev/null
fi
getent group bluetooth >/dev/null || fail 'Install BlueZ and its bluetooth group first.'
if ! id pitboss-admin >/dev/null 2>&1; then
    useradd --system --user-group --home-dir "$state" --no-create-home --shell /usr/sbin/nologin pitboss-admin
fi
[[ $(id -u pitboss-admin) != 0 ]] || fail 'Refusing privileged service account.'
account=$(getent passwd pitboss-admin)
[[ "$account" == *":$state:/usr/sbin/nologin" ]] || fail 'Existing service account has unexpected home or login shell; inspect it manually.'
usermod -a -G bluetooth pitboss-admin
install -d -o root -g root -m 0755 "$app" "$app/releases"
install -d -o root -g pitboss-admin -m 0750 "$config"
install -d -o pitboss-admin -g pitboss-admin -m 0700 "$state"
release=$(mktemp -d "$app/releases/release-XXXXXXXX")
chmod 0755 "$release"
python3 -m venv "$release/venv"
"$release/venv/bin/python" -m pip install "$source_dir"
# Virtualenvs remain at their original absolute path; only current changes.
chmod -R a+rX "$release"
install -m 0644 "$source_dir/deploy/pitboss-admin.service" "$release/pitboss-admin.service"
install -m 0644 "$source_dir/deploy/manage.sh" "$release/manage.sh"
if [[ ! -e "$config/config.yaml" ]]; then
    install -o root -g pitboss-admin -m 0640 "$source_dir/deploy/config.yaml" "$config/config.yaml"
fi
if [[ ! -e "$config/environment" ]]; then
    install -o root -g pitboss-admin -m 0640 /dev/null "$config/environment"
fi
if [[ "$action" == upgrade ]]; then
    systemctl stop pitboss-admin.service
    backup
    # Never silently restart an old binary against a partially migrated database.
    trap 'printf "Upgrade failed; service remains stopped. Restore backup: %s\n" "$backup_dir" >&2' ERR
else
    runuser -u pitboss-admin -- "$release/venv/bin/pitboss-state" bootstrap "$state/state.sqlite3"
fi
runuser -u pitboss-admin -- env PITBOSS_MANAGED=true PITBOSS_CONFIG_FILE="$config/config.yaml" \
    "$release/venv/bin/pitboss-state" validate "$state/state.sqlite3"
ln -sfn "$release" "$app/current"
install -m 0644 "$release/pitboss-admin.service" "$unit"
systemctl daemon-reload
if [[ "$action" == upgrade ]]; then
    systemctl start pitboss-admin.service
    trap - ERR
    printf 'Upgrade started. Verify systemctl status, health and authenticated telemetry.\n'
else
    printf 'Installed but not started. Save the token. Start explicitly with: sudo systemctl enable --now pitboss-admin\n'
fi
