#!/usr/bin/env bash
set -euo pipefail
repo_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd "$repo_root"

# Public build inputs only. Proxy credentials, if injected, remain Docker's
# predefined proxy arguments; the additional CA is an ephemeral BuildKit secret.
build_options=()
for proxy_name in HTTP_PROXY HTTPS_PROXY NO_PROXY http_proxy https_proxy no_proxy; do
  if [[ -n ${!proxy_name:-} ]]; then
    build_options+=(--build-arg "$proxy_name")
  fi
done
if [[ -n ${NODE_EXTRA_CA_CERTS:-} && -f $NODE_EXTRA_CA_CERTS ]]; then
  build_options+=(--secret "id=custom_ca,src=$NODE_EXTRA_CA_CERTS")
fi
if [[ -n ${RINHA_BUILD_NETWORK:-} ]]; then
  build_options+=(--network "$RINHA_BUILD_NETWORK")
fi
# Some cloud hosts resolve their egress proxy through /etc/hosts. BuildKit does
# not inherit those aliases, even with host networking. Resolve them afresh;
# never store a platform IP or proxy credential in the repository/image.
if [[ ${RINHA_BUILD_NETWORK:-} == host && -n ${HTTPS_PROXY:-${https_proxy:-}} ]]; then
  proxy_mappings=$(python3 - <<'PY'
import os, socket, urllib.parse
hosts = {urllib.parse.urlsplit(os.environ.get(k, '')).hostname
         for k in ('HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy')}
for host in sorted(h for h in hosts if h):
    address = socket.getaddrinfo(host, None, socket.AF_INET)[0][4][0]
    print(f'{host}:{address}')
PY
)
  while IFS= read -r mapping; do
    [[ -z $mapping ]] || build_options+=(--add-host "$mapping")
  done <<< "$proxy_mappings"
fi
docker build "${build_options[@]}" --tag rinha-backend-nest:local .
