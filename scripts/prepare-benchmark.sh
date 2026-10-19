#!/usr/bin/env bash
set -euo pipefail
repo="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
tools="$(python3 "$repo/scripts/prepare-benchmark.py")"
readarray -t paths < <(python3 -c 'import json,sys; x=json.load(sys.stdin); print(x["java_home"]); print(x["gatling_home"]); print(x["simulations"]); print(x["resources"])' <<< "$tools")
export JAVA_HOME="${paths[0]}"
cd "${paths[1]}"
bash bin/gatling.sh -rm package -s RinhaBackendSimulation -sf "${paths[2]}" -rsf "${paths[3]}"
printf 'Gatling oficial verificado e compilado. Cache: %s\n' "${paths[1]}"
