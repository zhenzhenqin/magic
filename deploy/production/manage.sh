#!/usr/bin/env bash
set -euo pipefail
umask 077

root=/opt/fooddiary
data="$root/shared/data"
db="$data/fooddiary.db"
media="$root/shared/media"
backup_root=/var/backups/fooddiary
maintenance="$root/shared/maintenance"
units=(fooddiary-api.service fooddiary-sticker.service fooddiary-ai.service)
action=${1:-}
[[ $EUID == 0 && -d $data && -d $backup_root ]]
case "$action" in backup|publish) ;; *) echo "Usage: manage.sh backup | publish SHA" >&2; exit 2 ;; esac
exec 9>"$root/shared/logs/management.lock"
flock -n 9
[[ ! -e $maintenance && ! -L $maintenance ]] || { echo "Resolve the existing maintenance marker first" >&2; exit 1; }

previous=
if [[ -L $root/current ]]; then
    previous=$(readlink -f "$root/current")
    [[ $previous =~ ^/opt/fooddiary/releases/[a-f0-9]{40}$ && -x $previous/backend/.venv/bin/python ]]
else
    [[ ! -e $root/current && ! -e $db ]]
fi
next=$previous
if [[ $action == publish ]]; then
    [[ ${2:-} =~ ^[a-f0-9]{40}$ ]]
    next="$root/releases/$2"
    [[ -d $next && ! -L $next && $(<"$next/REVISION") == "$2" && -f $next/web/index.html ]]
    [[ -x $next/backend/.venv/bin/python && -L $next/.env ]]
    nginx -t
    if [[ $next == "$previous" ]]; then
        bash "$next/deploy/production/health.sh" local
        printf 'Already running revision %s\n' "$2"
        exit
    fi
else
    [[ -n $previous && -f $db ]]
fi

active=()
for unit in "${units[@]}"; do
    if systemctl is-active --quiet "$unit"; then active+=("$unit"); fi
done

python="$next/backend/.venv/bin/python"
cd "$next/backend"
stamp=$(date -u +%Y%m%dT%H%M%S)-$$
snapshot="$backup_root/$stamp"
candidate="$data/.candidate-$stamp.db"
rollback="$data/.rollback-$stamp.db"
switched_db=false
switched_link=false
install -m 0644 /dev/null "$maintenance"

restore_services() {
    local unit
    for unit in "${active[@]}"; do systemctl start "$unit" || return; done
}

finish() {
    local result=$?
    trap - EXIT
    set +e
    if (( result != 0 )); then
        echo "Operation failed. Check the FoodDiary journal and the preserved recovery point." >&2
        if $switched_db || $switched_link; then
            systemctl stop fooddiary-api.service || exit "$result"
            if $switched_db; then
                runuser -u fooddiary -- "$python" -m app.maintenance seal-db "$db" || exit "$result"
                mv -T "$db" "$candidate.failed" || exit "$result"
                if [[ -f $rollback ]]; then mv -T "$rollback" "$db" || exit "$result"; fi
            fi
            if $switched_link; then
                if [[ -n $previous ]]; then
                    ln -s "$previous" "$root/.rollback-$stamp" && mv -Tf "$root/.rollback-$stamp" "$root/current" || exit "$result"
                else
                    unlink "$root/current" || exit "$result"
                fi
            fi
        fi
        restore_services || exit "$result"
    fi
    rm -f -- "$maintenance"
    exit "$result"
}
trap finish EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
for unit in "${active[@]}"; do systemctl stop "$unit"; done
for unit in "${units[@]}"; do
    status=$(systemctl show "$unit" --property=ActiveState --value)
    [[ $status == inactive || $status == failed ]]
done

if [[ -f $db ]]; then
    "$python" -m app.maintenance backup "$db" "$media" "$snapshot" --release "${previous##*/}"
    "$python" -m app.maintenance verify "$snapshot"
    printf 'Verified recovery point %s\n' "$snapshot"
fi
if [[ $action == backup ]]; then
    restore_services
    exit
fi

if [[ -f $db ]]; then
    install -m 0600 -o fooddiary -g fooddiary "$snapshot/fooddiary.db" "$candidate"
else
    install -m 0600 -o fooddiary -g fooddiary /dev/null "$candidate"
fi
runuser -u fooddiary -- "$python" -m app.maintenance migrate-candidate "$candidate"
if [[ -f $db ]]; then
    runuser -u fooddiary -- "$python" -m app.maintenance seal-db "$db"
    ln "$db" "$rollback"
fi
mv -Tf "$candidate" "$db"
switched_db=true
ln -s "$next" "$root/.current-$stamp"
mv -Tf "$root/.current-$stamp" "$root/current"
switched_link=true
systemctl start fooddiary-api.service
healthy=false
for attempt in {1..15}; do
    if bash "$next/deploy/production/health.sh" local; then healthy=true; break; fi
    sleep 1
done
$healthy
for unit in "${active[@]}"; do
    if [[ $unit != fooddiary-api.service ]]; then
        if ! systemctl start "$unit"; then echo "Optional worker failed to restart: $unit" >&2; fi
    fi
done
if [[ -f $rollback ]]; then rm -- "$rollback"; fi
printf 'Active revision %s\n' "$2"
