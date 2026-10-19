# Rinha de Backend 2023 com NestJS

Implementação da [edição 2023 Q3 da Rinha de Backend](https://github.com/zanfranceschi/rinha-de-backend-2023-q3): API de pessoas em **NestJS 11.2.7**, **Fastify 5.11.3** e **PostgreSQL 16**, com duas réplicas atrás do Nginx. O Docker Compose distribui **1,5 CPU** e **2.688 MiB de memória** entre todos os serviços.

O objetivo é exercitar NestJS e Docker sob restrição de recursos e medir o efeito das decisões de implementação. Os [resultados e gráficos](docs/resultados.md) registram a carga oficial, a contagem persistida e as limitações da comparação histórica. O [guia de otimizações](docs/otimizacoes.md) explica os gargalos, os limites de CPU/RAM e os ganhos e regressões de cada experimento. O [post sobre a experiência](docs/post.md) reúne decisões e aprendizados.

A configuração padrão final persistiu **31.757 pessoas**, contra **8.261** da referência (**3,84 vezes**), sem eventos OOM observados na corrida final. Ainda houve **22,20% KO** no Gatling e p99 das respostas OK de **11.115 ms**. A maior contagem da campanha foi **34.163**, com dois eventos OOM no Nginx. Escolhi o padrão atual pelos menores KO/p99 e ausência desses eventos, aceitando **7,04% menos pessoas** que a melhor contagem. Cada configuração teve uma execução; o [relatório](docs/resultados.md) registra também a regressão do experimento de CPU.

![Comparação das quatro execuções: pessoas persistidas, requisições, latência e eventos OOM](docs/assets/comparacao.png)

## Executar

Pré-requisitos: Docker Engine com Docker Compose v2, suporte a limites de CPU/memória e porta 9999 disponível. Para desenvolver fora dos contêineres, use Node.js 24 e npm. O harness de carga usa Bash, Python 3.12+, Node.js 24, Git e curl. Em Linux x86_64, a preparação baixa um JRE 17 local com checksum verificado; em outras plataformas, defina `BENCHMARK_JAVA_HOME` para um Java 17 instalado. O compilador Scala desta versão do Gatling não é compatível com Java 21.

```bash
./scripts/build-image.sh
docker compose up -d --no-build --wait
curl http://localhost:9999/health
```

O banco começa vazio e conserva os dados no volume `pessoas`. Usuário e senha `rinha` são exclusivos deste ambiente local; na composição padrão, somente o Nginx publica uma porta no host. `/health` consulta o banco e é usado pelas verificações de prontidão.

```bash
curl -i http://localhost:9999/pessoas \
  -H 'Content-Type: application/json' \
  -d '{"apelido":"gui","nome":"Guilherme","nascimento":"2000-10-01","stack":["NestJS","Docker"]}'

curl 'http://localhost:9999/pessoas?t=nest'
curl http://localhost:9999/contagem-pessoas
```

O primeiro comando retorna `201` com o endereço do recurso no cabeçalho `Location`. Repetir o mesmo apelido retorna `422`.

## Contrato da API

| Endpoint | Comportamento |
| --- | --- |
| `POST /pessoas` | Cria uma pessoa; `201` e `Location: /pessoas/{uuid}`. |
| `GET /pessoas/{uuid}` | Recurso completo com `200`; inexistente ou UUID malformado com `404`. |
| `GET /pessoas?t=termo` | Busca por substring em apelido, nome e cada item da stack, sem distinguir maiúsculas; até 50 resultados. |
| `GET /contagem-pessoas` | Contagem atual do PostgreSQL em texto puro. |

`apelido` é obrigatório, único e limitado a 32 caracteres; `nome` é obrigatório e limitado a 100; `nascimento` deve ser uma data de calendário válida no formato `AAAA-MM-DD`. `stack` aceita ausência, `null` ou array de strings de até 32 caracteres. Os limites contam caracteres Unicode. Campos obrigatórios ausentes, vazios, nulos ou acima do limite e datas inválidas retornam `422`; tipos incompatíveis e JSON malformado retornam `400`. A ausência de `t`, um termo vazio ou contendo NUL retorna `400`. `%` e `_` são texto literal na busca. Apelidos preservam caixa; a busca ignora caixa.

## Arquitetura e recursos

```mermaid
flowchart LR
    gatling["Gatling 3.9.5\nfora do orçamento da aplicação"] --> nginx["Nginx :9999"]
    nginx --> api1["NestJS + Fastify\nréplica 1"]
    nginx --> api2["NestJS + Fastify\nréplica 2"]
    api1 --> pg[("PostgreSQL 16\nvolume persistente")]
    api2 --> pg
```

| Serviço | CPU | Memória |
| --- | ---: | ---: |
| API 1 | 0,35 | 384 MiB |
| API 2 | 0,35 | 384 MiB |
| PostgreSQL | 0,65 | 1.664 MiB |
| Nginx | 0,15 | 256 MiB |
| **Total** | **1,50** | **2.688 MiB** |

O total de memória é **2.818.572.288 bytes**, inferior até a 3 GB decimais. Os limites incluem os quatro serviços e são verificados nos contêineres durante a campanha.

Essa é a distribuição padrão atual, usada no quarto experimento. As duas primeiras corridas deram 1.792 MiB ao banco e 128 MiB ao Nginx, com as mesmas quotas de CPU atuais; `docker-compose.reference.yml` recupera essa distribuição. O terceiro experimento usou a memória atual, mas 0,25 CPU por API e 0,85 CPU no banco; `docker-compose.cpu-experiment.yml` permite reproduzi-lo.

A aplicação confirma o `INSERT` antes de responder `201`; o índice único do banco resolve a concorrência por apelido. A busca usa `pg_trgm` sobre uma coluna de apoio, seguida de uma verificação por campo. Cada API guarda até 10.000 pessoas em cache FIFO para leituras por ID; a contagem consulta sempre o banco. As razões, custos e limites dessas escolhas estão em [docs/arquitetura.md](docs/arquitetura.md).

## Desenvolvimento e verificações

```bash
npm ci
npm run check
npm test
npm run build
npm run test:integration
```

As verificações locais validam tipos, regras de entrada e compilação. O teste HTTP precisa da composição em execução e insere dados: cobre os endpoints, datas, Unicode, duplicatas concorrentes, busca literal, leitura através do balanceador e contagem. Para apontá-lo a outro endereço, defina `BASE_URL`.

Na implementação medida, passaram a verificação de tipos, a compilação, os cinco testes locais e os 51 testes/casos HTTP antes da carga. A preparação também verificou e compilou a simulação oficial. Após reiniciar banco e APIs, a contagem continuou em **31.757**, e a mesma pessoa foi relida com conteúdo idêntico. A [validação registrada](benchmark/validation.json) reúne testes, persistência, prontidão e quotas reais.

Para trabalhar na API com recarga automática, use o override que publica o PostgreSQL somente em `127.0.0.1:5432`:

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d db --wait
DATABASE_URL=postgres://rinha:rinha@localhost:5432/rinha npm run start:dev
```

A API de desenvolvimento escuta na porta 3000. Use `BASE_URL=http://localhost:3000` no teste HTTP desse fluxo. A composição padrão usa uma rede bridge e é a opção portátil; a campanha nesta nuvem usa o override de rede descrito a seguir.

## Rede nesta nuvem

Nesta máquina, a primeira tentativa de carga perdeu acesso à porta publicada `9999`: o host recebia `ECONNREFUSED`, enquanto o Nginx respondia `200` pelo IP do contêiner e os quatro contêineres continuavam em execução. Essa execução foi marcada como `invalid_infrastructure` e excluída da comparação; sua evidência foi preservada em `benchmark/evidence/20261016T124526Z-baseline/`.

O arquivo `docker-compose.host.yml` permite contornar a camada de publicação de portas neste ambiente. Ele conserva os mesmos quatro contêineres, seus limites, o balanceador e o fluxo Nginx → duas APIs → PostgreSQL. Os contêineres compartilham o namespace de rede do host: PostgreSQL escuta em `127.0.0.1:5432`, as APIs em `127.0.0.1:3001` e `:3002`, e o Nginx em `:9999`. O encaminhamento de porta do Docker sai desse caminho.

Use Docker Compose 2.24 ou superior e Linux com suporte a host networking; no Docker Desktop, o recurso precisa estar disponível e habilitado. As portas devem estar livres. Para reproduzir a configuração desta nuvem, execute antes dos comandos de inicialização e das cargas:

```bash
export COMPOSE_FILE=docker-compose.yml:docker-compose.host.yml \
  RINHA_BUILD_NETWORK=host \
  DOCKER_CONFIG=/workspace/.cache/docker \
  npm_config_cache=/workspace/.cache/npm \
  RINHA_BENCHMARK_CACHE=/workspace/.cache/rinha-benchmark
```

Os caminhos de cache são específicos desta nuvem; ajuste-os ao seu ambiente. Execute as quatro configurações no mesmo modo de rede. Para usar a rede bridge em outra máquina, omita `docker-compose.host.yml` de todos os comandos; os overrides de recursos continuam necessários nas três primeiras configurações. O override host não se combina com `docker-compose.dev.yml`.

## Reproduzir a carga oficial

O harness obtém o Gatling 3.9.5 e os arquivos oficiais fixados no commit [`da99faf`](https://github.com/zanfranceschi/rinha-de-backend-2023-q3/tree/da99faf563c23dca43a5afa2ac31a34ca8cc39e6). A simulação e os TSV são preservados: há 25 segundos de aquecimento e três minutos de rampas, chegando a 600 criações/s, 100 buscas/s e 40 buscas inválidas/s. Após uma criação aceita, a simulação faz uma leitura pelo `Location`, exercitando a consistência entre réplicas.

```bash
./scripts/prepare-benchmark.sh

export COMPOSE_FILE=docker-compose.yml:docker-compose.host.yml:docker-compose.reference.yml
SEARCH_MODE=scan CACHE_SIZE=0 \
  ./scripts/benchmark.sh --label baseline-host --reset

SEARCH_MODE=indexed CACHE_SIZE=10000 \
  ./scripts/benchmark.sh --label indexed-cache-host --reset

export COMPOSE_FILE=docker-compose.yml:docker-compose.host.yml:docker-compose.cpu-experiment.yml
SEARCH_MODE=indexed CACHE_SIZE=10000 \
  ./scripts/benchmark.sh --label tuned-host --reset

export COMPOSE_FILE=docker-compose.yml:docker-compose.host.yml
SEARCH_MODE=indexed CACHE_SIZE=10000 \
  ./scripts/benchmark.sh --label memory-host --reset
```

**`--reset` remove o volume de dados deste projeto. Execute somente em um ambiente dedicado a benchmark, sem dados úteis.** Cada corrida deve começar com o banco vazio, inclusive depois dos testes HTTP. Sem `--reset`, o script exige contagem zero e conserva o volume. A imagem, o esquema e o orçamento total são os mesmos nas quatro configurações. A referência desliga o cache e o pré-filtro da busca; a segunda habilita ambos; a terceira também redistribui CPU e memória; a quarta restaura a CPU mantendo a memória redistribuída. O índice GIN continua presente nas quatro, portanto esta comparação não mede o custo de criar ou manter o índice.

Cada execução salva `summary.json`, `time-series.json`, condições do host, limites dos contêineres, amostras de recursos, logs, contagem e relatório HTML completo do Gatling em `benchmark/results/<data-UTC>-<label>/`. O manifesto `benchmark/official-source.json` identifica os insumos e seus hashes. Os gráficos comparativos são gerados depois, usando somente execuções válidas:

```bash
python3 -m pip install matplotlib==3.10.8
python3 scripts/plot-benchmarks.py \
  benchmark/evidence/20261016T125218Z-baseline-host \
  benchmark/evidence/20261016T125656Z-indexed-cache-host \
  benchmark/evidence/20261016T130257Z-tuned-host \
  benchmark/evidence/20261016T130832Z-memory-host \
  --output benchmark/comparison
```

O último comando exporta `benchmark/comparison.svg` e `.png`. O repositório conserva evidências compactas selecionadas em `benchmark/evidence/`; os relatórios completos de novas execuções permanecem locais. A análise está em [docs/resultados.md](docs/resultados.md). Uma corrida por configuração é uma observação exploratória: não estabelece estabilidade, significância estatística ou um ganho garantido.

## Comparação com a edição de 2023

A [classificação final oficial](https://github.com/zanfranceschi/rinha-de-backend-2023-q3/blob/da99faf563c23dca43a5afa2ac31a34ca8cc39e6/README.md#resultado-da-etapa-final) usa a contagem de pessoas persistidas. O vencedor registrou **44.936 pessoas**; o décimo colocado, **36.106**. Não existe fórmula de pontos que combine vazão e latência.

O padrão final atingiu **70,67% da contagem do vencedor**, com **13.179 pessoas a menos**. A melhor contagem local, 34.163, corresponde a **76,03%** do vencedor; ambas ficaram abaixo dos dez finalistas. Essa comparação usa contagem, mesmo tendo escolhido o padrão por um compromisso operacional diferente do critério de classificação.

O teste original rodou em uma EC2 `t3a.xlarge`, com AMD EPYC 7571 e 16 GiB. Esta reprodução usa Intel Xeon Platinum 8573C, cinco vCPUs visíveis, quota de quatro CPUs no cgroup pai e quota de 32 GiB de memória. O Docker é aninhado, usa armazenamento `vfs`, e o gerador de carga disputa o host com a aplicação. A campanha nesta nuvem usa rede host para contornar a falha de publicação de portas. Os limites dos serviços continuam aplicados, mas os resultados são uma **comparação histórica em condições diferentes**, sem posição oficial no torneio.

A coluna “p99 geral” do README oficial corresponde ao p99 das requisições OK nos artefatos Gatling. No vencedor, são 17.418 ms para OK e 17.357 ms considerando todas as requisições. A análise identifica os dois valores para evitar comparar métricas diferentes.

## Fontes

- [Regras e contrato oficiais](https://github.com/zanfranceschi/rinha-de-backend-2023-q3/blob/da99faf563c23dca43a5afa2ac31a34ca8cc39e6/INSTRUCOES.md).
- [Simulação Gatling oficial](https://github.com/zanfranceschi/rinha-de-backend-2023-q3/blob/da99faf563c23dca43a5afa2ac31a34ca8cc39e6/stress-test/user-files/simulations/rinhabackend/RinhaBackendSimulation.scala).
- [Hardware da competição](https://github.com/zanfranceschi/rinha-de-backend-2023-q3/blob/da99faf563c23dca43a5afa2ac31a34ca8cc39e6/misc/lshw-aws).
- [Artefatos do vencedor da final](https://github.com/zanfranceschi/rinha-de-backend-2023-q3/tree/da99faf563c23dca43a5afa2ac31a34ca8cc39e6/resultados/final/viniciusfonseca).
