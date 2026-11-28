#!/usr/bin/env bash
set -euo pipefail

current=/opt/fooddiary/current
mode=${1:-local}
request() {
    curl --silent --show-error --noproxy '*' --max-time 5 --dump-header - --output /dev/null \
        --write-out '%{http_code}\n' "$@"
}

check_response() {
    local response=$1 expected_code=$2 name=$3 value=$4
    [[ ${response##*$'\n'} == "$expected_code" ]] &&
        awk -F ': *' -v name="$name" -v value="$value" '
            tolower($1)==name {gsub(/\r$/, "", $2); if ($2==value) count++}
            END {exit (count != 1)}' <<< "$response"
}

case "$mode" in
    local)
        revision=${2:-$(<"$current/REVISION")}
        [[ $revision =~ ^[a-f0-9]{40}$ ]]
        pid=$(systemctl show fooddiary-api.service -p MainPID --value)
        [[ $pid =~ ^[1-9][0-9]*$ ]]
        systemctl is-active --quiet fooddiary-api.service
        ss -H -lntp 'sport = :18080' | awk -v pid="$pid" '
            $4=="127.0.0.1:18080" && index($0, "pid=" pid ",") {good++}
            END {exit !(NR==1 && good==1)}'
        response=$(request http://127.0.0.1:18080/api/v1/ready)
        check_response "$response" 200 x-fooddiary-revision "$revision"
        echo "Local API and revision $revision are ready"
        ;;
    https|maintenance)
        host=${2:-}
        [[ $host =~ ^[a-zA-Z0-9][a-zA-Z0-9.-]+$ ]]
        if [[ $mode == maintenance ]]; then
            response=$(request --resolve "$host:443:127.0.0.1" "https://$host/api/v1/ready")
            check_response "$response" 503 x-fooddiary-maintenance 1
            echo "Trusted HTTPS maintenance response verified"
        else
            revision=${3:-}
            [[ $revision =~ ^[a-f0-9]{40}$ ]]
            response=$(request "https://$host/api/v1/ready")
            check_response "$response" 200 x-fooddiary-revision "$revision"
            echo "HTTPS revision $revision is ready"
        fi
        ;;
    *) echo "Usage: health.sh local [SHA] | https HOST SHA | maintenance HOST" >&2; exit 2 ;;
esac
