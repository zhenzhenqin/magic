#!/usr/bin/env bash
set -euo pipefail
umask 077

root=/opt/fooddiary
data="$root/shared/data"
db="$data/fooddiary.db"
media="$root/shared/media"
backup_root=/var/backups/fooddiary
maintenance="$root/shared/maintenance"
state="$root/shared/logs/active-operation"
api=fooddiary-api.service
units=("$api" fooddiary-sticker.service fooddiary-ai.service)
action=${1:-}
[[ $EUID == 0 && -d $data && -d $backup_root ]]
case "$action" in backup|publish|recover) ;; *) echo "Usage: manage.sh backup [--keep-three] | publish SHA | recover" >&2; exit 2 ;; esac
exec 9>"$root/shared/logs/management.lock"
flock -n 9 || { echo "Another FoodDiary writer operation holds the management lock" >&2; exit 1; }

valid_release() {
    [[ $1 == "$root/releases/${1##*/}" && ${1##*/} =~ ^[a-f0-9]{40}$ && -d $1 && ! -L $1 ]]
}

save_state() {
    local temp
    temp=$(mktemp -- "${state}.XXXXXX") || return
    {
        printf 'phase=%q\nprevious=%q\nnext=%q\nstamp=%q\n' "$phase" "$previous" "$next" "$stamp"
        printf 'active=('
        if (( ${#active[@]} )); then printf '%q ' "${active[@]}"; fi
        printf ')\n'
    } >"$temp" && mv -Tf -- "$temp" "$state"
}

load_state() {
    [[ -f $state && ! -L $state && $(stat -c '%u:%a' "$state") == 0:600 ]] || return
    # The journal is generated here in a root-only directory. Values are shell-escaped on write.
    source "$state"
    [[ $stamp =~ ^[0-9]{8}T[0-9]{6}-[0-9]+$ ]] || return
    valid_release "$next" || return
    if [[ -n $previous ]]; then valid_release "$previous" || return; fi
    case "$phase" in preflight|pending|replacing|committed|retry) ;; *) return 1 ;; esac
}

release_command() {
    local release=$1
    shift
    (cd "$release/backend" && "$release/backend/.venv/bin/python" "$@")
}

stop_writers() {
    local unit status
    systemctl stop "${units[@]}" || return
    for unit in "${units[@]}"; do
        status=$(systemctl show "$unit" --property=ActiveState --value) || return
        [[ $status == inactive || $status == failed ]] || return 1
    done
}

select_release() {
    if [[ -n $1 ]]; then
        ln -sfn -- "$1" "$root/.current-$stamp" && mv -Tf -- "$root/.current-$stamp" "$root/current"
    elif [[ -L $root/current ]]; then
        [[ $(readlink -f "$root/current") == "$next" ]] && unlink "$root/current"
    else
        [[ ! -e $root/current ]]
    fi
}

resume() {
    local release=$1 unit attempt since
    shift
    since=$(date -u +'%Y-%m-%dT%H:%M:%S.%NZ') || return
    if (( $# )); then systemctl start "$@" || return; fi
    for attempt in {1..20}; do
        if bash "$release/deploy/production/health.sh" local "${release##*/}" >/dev/null; then
            local ready=true
            for unit in "$@"; do
                case "$unit" in
                    fooddiary-sticker.service|fooddiary-ai.service)
                        if ! systemctl is-active --quiet "$unit" ||
                            ! release_command "$release" -m app.maintenance worker-ready "$unit" "$since"; then
                            ready=false
                        fi
                        ;;
                esac
            done
            if $ready; then return 0; fi
        fi
        sleep 1
    done
    return 1
}

complete_operation() {
    local release=$1
    [[ $(readlink -f "$root/current") == "$release" ]] || return
    bash "$release/deploy/production/health.sh" local "${release##*/}" || return
    phase=committed
    next=$release
    save_state || return
    rm -f -- "$maintenance" "$data/.rollback-$stamp.db" || return
    rm -- "$state"
}

recover_operation() {
    local rollback="$data/.rollback-$stamp.db" failed suffix unit
    if [[ $phase == committed ]]; then
        # After resuming traffic the live DB may contain new user data. Never restore an older DB here.
        for unit in "${active[@]}"; do systemctl is-active --quiet "$unit" || return; done
        complete_operation "$next"
        return
    fi
    if [[ $phase == preflight && -n $previous ]]; then
        complete_operation "$previous"
        return
    fi
    if [[ $phase != preflight && $phase != retry ]]; then stop_writers || return; fi
    if [[ $phase == replacing ]]; then
        if [[ -n $previous && ! -f $rollback ]]; then return 1; fi
        if [[ ! -e $db || ! $db -ef $rollback ]]; then
            failed=$(mktemp -d -- "$data/.failed-$stamp-XXXXXX") || return
            for suffix in '' -wal -shm -journal; do
                if [[ -e $db$suffix ]]; then mv -T -- "$db$suffix" "$failed/fooddiary.db$suffix" || return; fi
            done
            if [[ -n $previous ]]; then ln -- "$rollback" "$db" || return; fi
        fi
        select_release "$previous" || return
    fi
    if [[ -z $previous ]]; then
        [[ ! -L $maintenance ]] || return
        install -m 0644 /dev/null "$maintenance" || return
        phase=retry
        save_state || return
        echo "First release is offline. Maintenance stays active; publish a verified revision to retry." >&2
        return 0
    fi
    resume "$previous" "${active[@]}" || return
    complete_operation "$previous"
}

finish() {
    local code=$?
    trap - EXIT
    if (( code != 0 )) && [[ -f $state ]]; then
        if ! recover_operation; then
            echo "Recovery incomplete. The maintenance marker and recovery point remain; run manage.sh recover after diagnosis." >&2
        fi
    fi
    exit "$code"
}

if [[ $action == recover ]]; then
    load_state
    recover_operation
    exit
fi

if [[ -e $state || -e $maintenance || -L $maintenance ]]; then
    load_state
    [[ $action == publish && $phase == retry && -z $previous && ! -e $db && ! -e $root/current && ! -L $root/current ]] ||
        { echo "An interrupted operation needs manage.sh recover" >&2; exit 1; }
fi

previous=
if [[ -L $root/current ]]; then
    previous=$(readlink -f "$root/current")
    valid_release "$previous"
    [[ -f $db && ! -L $db ]]
else
    [[ ! -e $root/current && ! -e $db ]]
fi
next=$previous
if [[ $action == publish ]]; then
    [[ ${2:-} =~ ^[a-f0-9]{40}$ ]]
    next="$root/releases/$2"
    valid_release "$next"
    [[ -x $next/backend/.venv/bin/python && ! -L $next/backend/.venv && -L $next/.env ]]
    nginx -t
    release_command "$next" "$next/deploy/production/release-manifest.py" verify "$next" "$2" --prepared
    if [[ $next == "$previous" ]]; then
        bash "$next/deploy/production/health.sh" local "$2"
        exit
    fi
else
    [[ -n $previous && ( -z ${2:-} || ${2:-} == --keep-three ) ]]
fi

active=()
for unit in "${units[@]}"; do
    if systemctl is-active --quiet "$unit"; then active+=("$unit"); fi
done
stamp=$(date -u +%Y%m%dT%H%M%S)-$$
phase=preflight
save_state
trap finish EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
install -m 0644 /dev/null "$maintenance"
host=$(release_command "$next" -c 'from urllib.parse import urlsplit; from app.core.config import Settings; print(urlsplit(Settings().app_origins[0]).hostname)')
bash "$next/deploy/production/health.sh" maintenance "$host"
phase=pending
save_state
stop_writers

snapshot="$backup_root/release-$stamp"
if [[ $action == backup ]]; then snapshot="$backup_root/daily-$stamp"; fi
if [[ -n $previous ]]; then
    release_command "$next" -m app.maintenance backup "$db" "$media" "$snapshot" --release "${previous##*/}"
    release_command "$next" -m app.maintenance verify "$snapshot"
fi
if [[ $action == backup ]]; then
    resume "$previous" "${active[@]}"
    complete_operation "$previous"
    if [[ ${2:-} == --keep-three ]]; then release_command "$previous" -m app.maintenance retain-daily "$backup_root" "$snapshot"; fi
    exit
fi

python="$next/backend/.venv/bin/python"
candidate="$data/.candidate-$stamp.db"
if [[ -n $previous ]]; then
    install -m 0600 -o fooddiary -g fooddiary "$snapshot/fooddiary.db" "$candidate"
else
    install -m 0600 -o fooddiary -g fooddiary /dev/null "$candidate"
fi
(
    cd "$next/backend"
    runuser -u fooddiary -- "$python" -m app.maintenance migrate-candidate "$candidate"
    if [[ -n $previous ]]; then runuser -u fooddiary -- "$python" -m app.maintenance seal-db "$db"; fi
)
if [[ -n $previous ]]; then ln -- "$db" "$data/.rollback-$stamp.db"; fi
phase=replacing
save_state
mv -Tf -- "$candidate" "$db"
select_release "$next"
workers=()
for unit in "${active[@]}"; do if [[ $unit != "$api" ]]; then workers+=("$unit"); fi; done
resume "$next" "$api" "${workers[@]}"
complete_operation "$next"
echo "Active revision ${next##*/}"
