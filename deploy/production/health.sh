#!/usr/bin/env bash
set -euo pipefail

mode=${1:-local}
case "$mode" in
    local) base=http://127.0.0.1:18080 ;;
    https)
        [[ ${2:-} =~ ^[A-Za-z0-9][A-Za-z0-9.-]+$ ]]
        base="https://$2"
        ;;
    *) echo "Usage: health.sh local | https HOST" >&2; exit 2 ;;
esac
for endpoint in health ready; do
    curl --fail --silent --show-error --max-time 5 "$base/api/v1/$endpoint"
    printf '\n'
done
