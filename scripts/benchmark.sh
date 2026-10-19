#!/usr/bin/env bash
set -euo pipefail
repo="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
label="${SEARCH_MODE:-indexed}"
reset=false
while (($#)); do
  case "$1" in
    --label) label="${2:?Informe um nome após --label}"; shift 2 ;;
    --reset) reset=true; shift ;;
    --help|-h)
      printf '%s\n' 'Uso: [SEARCH_MODE=scan|indexed CACHE_SIZE=0|10000] ./scripts/benchmark.sh [--label nome] [--reset]' 'Executa a carga oficial completa em localhost:9999 e salva benchmark/results/.' 'Sem --reset exige banco vazio. --reset APAGA o volume pessoas deste projeto Compose.'
      exit 0 ;;
    *) printf 'Argumento desconhecido: %s\n' "$1" >&2; exit 2 ;;
  esac
done
[[ "$label" =~ ^[a-zA-Z0-9_-]+$ ]] || { printf 'Label aceita apenas letras, números, _ e -.\n' >&2; exit 2; }
export DOCKER_CONFIG="${DOCKER_CONFIG:-${XDG_CACHE_HOME:-$(dirname "$repo")/.cache}/docker}"
export COMPOSE_FILE="${COMPOSE_FILE:-$repo/docker-compose.yml}"
mkdir -p "$DOCKER_CONFIG"
cd "$repo"
tools="$(python3 scripts/prepare-benchmark.py)"
readarray -t paths < <(python3 -c 'import json,sys; x=json.load(sys.stdin); print(x["java_home"]); print(x["gatling_home"]); print(x["simulations"]); print(x["resources"])' <<< "$tools")
export JAVA_HOME="${paths[0]}"
compose=(docker compose --project-directory "$repo")
if $reset; then
  printf 'Reset solicitado: apagando o volume de desenvolvimento deste projeto.\n'
  "${compose[@]}" down --volumes --remove-orphans
fi
bash scripts/build-image.sh
"${compose[@]}" up -d --no-build --wait --wait-timeout 180
initial_count="$(curl --fail --silent --show-error --max-time 10 http://localhost:9999/contagem-pessoas)"
[[ "$initial_count" == "0" ]] || { printf 'Banco contém %s pessoas. Carga cancelada; use --reset apenas para apagar esses dados.\n' "$initial_count" >&2; exit 1; }
run="$repo/benchmark/results/$(date -u +%Y%m%dT%H%M%SZ)-$label"
mkdir -p "$run/gatling"
printf '%s\n' "$tools" > "$run/tools.json"
printf '%s\n' "$initial_count" > "$run/initial-count.txt"
node scripts/verify-limits.mjs > "$run/docker-limits.json"
python3 scripts/benchmark-metadata.py "$run" "$label"
docker compose logs --no-color > "$run/docker-before.log"
python3 scripts/monitor-benchmark.py "$run/resource-samples.jsonl" &
monitor_pid=$!
cleanup() { kill "$monitor_pid" 2>/dev/null || true; wait "$monitor_pid" 2>/dev/null || true; }
trap cleanup EXIT INT TERM
printf 'Teste oficial completo iniciado; resultado: %s\n' "$run"
set +e
(cd "${paths[1]}" && bash bin/gatling.sh -rm local -s RinhaBackendSimulation \
  -rd "NestJS $label; official da99faf563c23dca43a5afa2ac31a34ca8cc39e6" \
  -rf "$run/gatling" -sf "${paths[2]}" -rsf "${paths[3]}" \
  -erjo '-Xms256m -Xmx1g -XX:ActiveProcessorCount=2') 2>&1 | tee "$run/gatling.log"
gatling_status=${PIPESTATUS[0]}
set -e
printf '%s\n' "$gatling_status" > "$run/gatling-exit-code.txt"
cleanup
trap - EXIT INT TERM
sleep 3
"${compose[@]}" logs --no-color > "$run/docker-after.log" 2>&1 || true
set +e
curl --fail --silent --show-error --max-time 60 http://localhost:9999/contagem-pessoas > "$run/contagem-pessoas.log" 2> "$run/final-count-error.log"
count_status=$?
printf '\n' >> "$run/contagem-pessoas.log"
printf '%s\n' "$count_status" > "$run/final-count-exit-code.txt"
python3 scripts/benchmark-metadata.py "$run" --verify
source_status=$?
set -e
python3 - "$run/run-status.json" "$gatling_status" "$count_status" "$source_status" <<'PY'
import json, pathlib, sys
gatling, count, source = map(int, sys.argv[2:])
status = {
    "valid": gatling == 0 and count == 0 and source == 0,
    "gatling_exit_code": gatling,
    "final_count_http_exit_code": count,
    "source_unchanged": source == 0,
    "invalid_reasons": [reason for failed, reason in ((gatling != 0, "gatling_failed"), (count != 0, "final_count_http_failed"), (source != 0, "source_changed")) if failed],
}
pathlib.Path(sys.argv[1]).write_text(json.dumps(status, indent=2) + "\n")
PY
if ((count_status != 0)); then
  "${compose[@]}" exec -T db psql -U rinha -d rinha -Atc 'SELECT count(*) FROM pessoas' > "$run/diagnostic-db-count.txt" 2> "$run/diagnostic-db-count-error.log" || true
  cat "$run/final-count-error.log" >&2
  printf 'Execução inválida: contagem HTTP falhou (exit %s). Logs e contagem SQL diagnóstica preservados em %s.\n' "$count_status" "$run" >&2
  exit 1
fi
if ((source_status != 0)); then
  printf 'Execução inválida: arquivos da aplicação mudaram durante a carga. Veja %s/source-integrity.json.\n' "$run" >&2
  exit 1
fi
python3 scripts/summarize-benchmark.py "$run"
printf 'Teste encerrado (exit %s). Relatório: %s\n' "$gatling_status" "$run/summary.json"
exit "$gatling_status"
