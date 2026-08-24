#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
search_warm_url="${TALKINGBOATS_SEARCH_WARM_URL:-}"
search_warm_timeout_seconds="${TALKINGBOATS_SEARCH_WARM_TIMEOUT_SECONDS:-30}"

if [[ -z "${search_warm_url}" ]]; then
  lan_address="$(/bin/bash "${script_dir}/talkingboats_lan_address.sh")"
  search_warm_url="http://${lan_address}:8034/api/clips/search?q=seattle+traffic&limit=1&recency=24h"
fi

for attempt in 1 2 3; do
  if curl --fail --silent --show-error --max-time "${search_warm_timeout_seconds}" \
    "${search_warm_url}" >/dev/null; then
    printf 'event=talkingboats_search_warm status=ok attempt=%s\n' "${attempt}"
    exit 0
  fi
  printf 'event=talkingboats_search_warm status=retry attempt=%s\n' "${attempt}" >&2
  sleep 5
done

printf 'event=talkingboats_search_warm status=failed attempts=3\n' >&2
exit 1
