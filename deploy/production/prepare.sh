#!/usr/bin/env bash
set -euo pipefail
umask 027

root=/opt/fooddiary
backup_root=/var/backups/fooddiary
python=${PYTHON_BIN:-python3.13}
action=${1:-check}

check() {
    [[ $(uname -s) == Linux && $(uname -m) == x86_64 ]]
    for command in "$python" nginx systemctl runuser flock curl; do command -v "$command" >/dev/null; done
    "$python" -c 'import platform, sqlite3, sys; assert sys.version_info[:2] == (3, 13); assert sqlite3.sqlite_version_info >= (3,35); print(sys.version.split()[0], sqlite3.sqlite_version, platform.libc_ver())'
    nginx -v
}

check
case "$action" in
    check) ;;
    init)
        [[ $EUID -eq 0 ]]
        getent passwd fooddiary >/dev/null || useradd --system --user-group --no-create-home --shell /usr/sbin/nologin fooddiary
        [[ $(id -u fooddiary) -ne 0 ]]
        install -d -o root -g root -m 0755 "$root" "$root/releases" "$root/shared" "$root/shared/acme"
        install -d -o root -g fooddiary -m 0750 "$root/shared/config" "$root/shared/models"
        install -d -o fooddiary -g fooddiary -m 0700 "$root/shared/data" "$root/shared/media"
        install -d -o root -g root -m 0700 "$root/shared/logs" "$backup_root"
        ;;
    release)
        [[ $EUID -eq 0 && ${2:-} =~ ^[a-f0-9]{40}$ && -d ${3:-} ]]
        release="$root/releases/$2"
        [[ -d $release && ! -L $release && $(<"$release/REVISION") == "$2" ]]
        if [[ $(readlink -f "$root/current") == "$release" ]]; then
            echo "The active release is read-only. Prepare a new revision instead." >&2
            exit 1
        fi
        [[ -f $release/web/index.html && -d $release/backend/app ]]
        "$python" "$release/deploy/production/release-manifest.py" verify "$release" "$2" --prepared
        wheelhouse=$(realpath "$3")
        config="$root/shared/config/fooddiary.env"
        [[ -f $config && ! -L $config && $(stat -c %a "$config") == 640 && $(stat -c %U:%G "$config") == root:fooddiary ]]
        if [[ -L $release/.env ]]; then
            [[ $(readlink "$release/.env") == "$config" ]]
        else
            [[ ! -e $release/.env ]]
            ln -s "$config" "$release/.env"
        fi
        environments=(.venv)
        if [[ ${4:-} == --with-sticker ]]; then environments+=(.sticker); fi
        cd "$release/backend"
        for directory in "${environments[@]}"; do
            [[ ! -L $directory ]]
            requirements=(-r requirements.txt)
            if [[ $directory == .sticker ]]; then requirements+=(-r requirements-sticker.txt); fi
            (
                umask 022
                "$python" -m venv "$directory"
                "$directory/bin/python" -m pip --disable-pip-version-check --no-cache-dir install \
                    --no-index --find-links "$wheelhouse" --only-binary=:all: "${requirements[@]}"
            )
            "$directory/bin/python" -m pip check
        done
        # Runtime files are readable by their consumers and writable by root only.
        chown -Rh root:root "$release"
        chmod 0755 "$release"
        find "$release/backend" "$release/deploy" "$release/web" -xdev -type d -exec chmod 0755 {} +
        find "$release/backend" "$release/deploy" "$release/web" -xdev -type f -exec chmod a+r,go-w {} +
        runuser -u www-data -- test -r "$release/web/index.html"
        runuser -u www-data -- test ! -r "$config"
        runuser -u fooddiary -- test ! -w "$release/backend/.venv"
        runuser -u fooddiary -- .venv/bin/python -c 'from pathlib import Path; from app.core.config import Settings; s=Settings(); assert s.app_env == "production" and Path(s.db_url.database) == Path("/opt/fooddiary/shared/data/fooddiary.db") and s.media_root == Path("/opt/fooddiary/shared/media"); assert not (s.ai_enabled or s.ai_byok_simulation or s.ai_available); print("Configuration, disabled external AI and service access verified")'
        if [[ -x .sticker/bin/python ]]; then
            runuser -u fooddiary -- .sticker/bin/python -c 'import numpy, onnxruntime; assert "CPUExecutionProvider" in onnxruntime.get_available_providers(); print(numpy.__version__, onnxruntime.__version__)'
        fi
        ;;
    *) echo "Usage: prepare.sh check | init | release SHA WHEELHOUSE [--with-sticker]" >&2; exit 2 ;;
esac
