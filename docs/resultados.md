# Resultados da carga oficial

Em **16 de outubro de 2026**, quatro configurações executaram a carga oficial da Rinha de Backend 2023 Q3. O padrão final persistiu **31.757 pessoas**, contra **8.261** da referência (**3,84 vezes; +284,42%**), sem eventos OOM observados na corrida final. Ainda registrou **22,20% KO** no Gatling e p99 das respostas OK de **11.115 ms**.

A maior contagem foi **34.163 pessoas**, com dois eventos OOM no Nginx. O padrão final foi escolhido pelos menores KO/p99 OK e ausência desses eventos, aceitando **7,04% menos registros** que a maior contagem. Esta é uma escolha operacional: pelo critério de classificação da competição, a execução com 34.163 continua sendo a melhor da campanha. Há uma corrida por configuração, sem estimativa de variabilidade.

## Configurações comparadas

| Configuração | Busca | Cache por réplica | Distribuição de recursos | Rede |
| --- | --- | ---: | --- | --- |
| `baseline-host` | Predicado por campo, sem pré-filtro GIN | Desligado (`0`) | Referência | Host |
| `indexed-cache-host` | Pré-filtro `pg_trgm` e predicado por campo | Até 10.000 pessoas | Referência | Host |
| `tuned-host` | Pré-filtro `pg_trgm` e predicado por campo | Até 10.000 pessoas | CPU e memória redistribuídas | Host |
| `memory-host` | Pré-filtro `pg_trgm` e predicado por campo | Até 10.000 pessoas | Só memória redistribuída | Host |

As quatro usam os mesmos quatro serviços, imagem da aplicação e esquema: duas APIs NestJS/Fastify, Nginx e PostgreSQL 16; **1,5 CPU e 2.688 MiB de memória** no total, equivalentes a **2.818.572.288 bytes**. O banco inicia vazio a cada corrida. O índice e a coluna de busca existem nas quatro configurações, mantendo o custo do índice nas inserções.

| Serviço | CPU das execuções 1, 2 e 4 | Memória das execuções 1 e 2 | CPU da execução 3 | Memória das execuções 3 e 4 |
| --- | ---: | ---: | ---: | ---: |
| Cada API | 0,35 | 384 MiB | 0,25 | 384 MiB |
| PostgreSQL | 0,65 | 1.792 MiB | 0,85 | 1.664 MiB |
| Nginx | 0,15 | 128 MiB | 0,15 | 256 MiB |

O Compose padrão atual contém a distribuição da quarta execução. O override `docker-compose.reference.yml`, aplicado depois do override host, recupera exatamente os limites das duas primeiras corridas; `docker-compose.cpu-experiment.yml` reproduz a terceira. Os IDs das imagens e hashes de entradas ficam nos metadados de cada execução.

## Medições

| Métrica | Referência `baseline-host` | Índice/cache `indexed-cache-host` | CPU/memória `tuned-host` | Só memória `memory-host` |
| --- | ---: | ---: | ---: | ---: |
| Pessoas persistidas | **8.261** | **34.163** | **31.346** | **31.757** |
| Requisições totais | 75.995 | 98.368 | 99.758 | 100.175 |
| Checks OK / KO | 23.550 / 52.445 | 75.567 / 22.801 | 74.752 / 25.006 | 77.940 / 22.235 |
| Falhas nos checks | 69,01% | 23,18% | 25,07% | 22,20% |
| Média de requisições/s, incluindo falhas | 350,21 | 451,23 | 459,71 | 459,52 |
| p50 de todas as respostas | 10.001 ms | 1.320 ms | 152 ms | 2.939 ms |
| p95 de todas as respostas | 12.815 ms | 10.985 ms | 12.632 ms | 10.952 ms |
| p99 de todas as respostas | 14.389 ms | 12.853 ms | 16.552 ms | 12.256 ms |
| p99 das respostas OK | 13.878 ms | 12.607 ms | 18.433 ms | 11.115 ms |
| Eventos `oom_kill` no Nginx | 2 | 2 | 0 | 0 |
| Injeção oficial | 205 s | 205 s | 205 s | 205 s |
| Janela entre primeira requisição e última conclusão | 216,662 s | 217,876 s | 216,420 s | 217,056 s |

A vazão inclui requisições que falharam; não representa apenas operações bem-sucedidas. “OK” significa que o check da simulação passou: um POST com `400` ou `422` também é esperado e conta como OK. A contagem de pessoas é consultada separadamente no banco, após a carga; não é o total de respostas OK.

O perfil oficial injeta usuários durante 205 segundos e aguarda as requisições restantes. Por isso a janela medida pode ultrapassar 205 segundos. A execução de referência teve saída zero do processo Gatling e concluiu esse perfil, mas acumulou erros HTTP, fechamentos prematuros e pressão de memória descritos abaixo.

![Pessoas persistidas, carga, latência e eventos OOM nas quatro configurações](assets/comparacao.png)

[Gráfico em SVG](assets/comparacao.svg). As curvas usam janelas de cinco segundos; o resumo usa as estatísticas globais do Gatling. A tentativa inválida na rede bridge foi excluída da figura.

## O que ocorreu na referência

| Operação | Requisições | Checks OK | Checks KO |
| --- | ---: | ---: | ---: |
| Criação | 54.625 | 13.660 | 40.965 |
| Consulta por ID | 7.590 | 4.214 | 3.376 |
| Busca válida | 9.590 | 1.682 | 7.908 |
| Busca inválida | 4.190 | 3.994 | 196 |

O relatório registrou 30.116 respostas `500` em criação, 9.277 respostas `500` em consultas/buscas, 13.034 fechamentos prematuros e 18 recusas de conexão. Os logs mostraram espera pelo pool do PostgreSQL: as buscas por varredura ocupavam as conexões e dificultavam o atendimento das outras operações. Uma inspeção encontrou 27 de 29 sessões da aplicação executando busca; outra observação registrou uma consulta de 12,79 segundos, acima dos 10 segundos disponíveis para obter uma conexão do pool. Essas observações sustentam a hipótese de disputa por CPU e conexões; não medem isoladamente a contribuição de cada fator.

O cgroup do Nginx registrou **dois eventos `oom_kill`**. O processo principal e o contêiner continuaram ativos, com `OOMKilled=false` na inspeção do Docker; esse campo sozinho não demonstra ausência de processos mortos por memória. Os eventos e fechamentos fazem parte do resultado sob os limites configurados. Não se deve resumir essa corrida como “sem OOM” nem usar sua vazão como capacidade sustentada.

## Índice, cache e nova hipótese de recursos

A segunda execução manteve as quotas originais e habilitou o pré-filtro GIN e o cache positivo por ID. A contagem subiu em **25.902 pessoas**, de 8.261 para 34.163 (**+313,55%**), enquanto o p99 OK passou de 13.878 para 12.607 ms. Como índice e cache mudaram juntos, o ganho observado pertence ao conjunto, sem atribuição individual a uma técnica.

Ainda ocorreram 12.703 fechamentos prematuros, 7.046 respostas `500` em criação e 3.052 respostas `500` em consultas/buscas. O Nginx teve novamente dois eventos `oom_kill`. A execução atendeu mais operações, mas permaneceu limitada por CPU do banco, espera por conexão e memória do balanceador.

As amostras mostraram o PostgreSQL saturado por CPU, usando no máximo cerca de **168 MiB** dos 1.792 MiB disponíveis. As APIs tiveram uso mediano abaixo de **20% de um CPU**, e o Nginx chegou a cerca de **124 MiB** sob um limite de 128 MiB. Essa observação motivou o terceiro experimento: transferir 0,20 CPU das APIs para o banco e 128 MiB do banco para o Nginx, preservando o orçamento total.

## Uma redistribuição que regrediu

O terceiro experimento, `tuned-host`, persistiu **31.346 pessoas**, **2.817 a menos** que a segunda execução (**−8,25%**). O p99 OK piorou de **12.607 para 18.433 ms**, e as falhas passaram de 23,18% para **25,07%**. A mediana total caiu para 152 ms, mas isso não impediu a piora da cauda nem recuperou a contagem: uma métrica agregada isolada esconderia a regressão.

Não houve novos eventos `oom_kill` em nenhum dos quatro cgroups, e os contêineres permaneceram ativos. Ainda assim, os logs registraram timeouts no pool e respostas `502` com `no live upstreams` no Nginx: o balanceador marcou temporariamente as APIs como indisponíveis após falhas sob sobrecarga. A ausência de OOM não significa que a carga foi atendida sem falhas.

Essa combinação manteve índice e cache já habilitados; seu resultado não é um efeito adicional dessas técnicas. A quarta execução, `memory-host`, manteve a memória da terceira e restaurou a CPU das duas primeiras. Compará-la à terceira testa a distribuição de CPU sob a mesma memória; compará-la à segunda testa a redistribuição de memória com a mesma CPU. Uma observação por configuração continua sem estimar variabilidade.

## Escolha da configuração padrão

A quarta execução persistiu **31.757 pessoas**, registrou **22,20% KO**, p99 OK de **11.115 ms** e zero eventos `oom_kill` nos quatro cgroups. Todos os contêineres continuaram ativos, conforme a [inspeção após a corrida](../benchmark/evidence/20261016T130832Z-memory-host/runtime-after.json). A memória do Nginx ficou com limite de 256 MiB; o banco recebeu 1.664 MiB, mantendo as quotas de CPU originais.

Essa foi a configuração escolhida como padrão operacional. Ela persistiu **2.406 pessoas a menos** que a segunda (**−7,04%**), mas apresentou menos KO, menor p99 OK e nenhum OOM observado. A contagem é o critério do ranking, portanto essa perda não é ocultada nem descrita como melhoria de pontuação. A mediana total da quarta, 2.939 ms, também foi pior que a da segunda, 1.320 ms.

O pico ainda excedeu a capacidade: foram **15.302 respostas `500` em criação**, **6.610 respostas `500` em consultas/buscas** e **323 fechamentos prematuros**. A espera pelo pool continuou aparecendo nos logs. O resultado final melhorou a referência, mas não demonstra atendimento confiável do perfil inteiro nem elimina a necessidade de novas medições antes de uma decisão de produção.

## Metodologia e condições do host

O harness usa Gatling **3.9.5**, JRE **17** e os três arquivos oficiais fixados no commit [`da99faf563c23dca43a5afa2ac31a34ca8cc39e6`](https://github.com/zanfranceschi/rinha-de-backend-2023-q3/tree/da99faf563c23dca43a5afa2ac31a34ca8cc39e6), sem alterar a simulação ou os TSV. Os hashes estão em [official-source.json](../benchmark/official-source.json). São 25 segundos de aquecimento e 180 segundos de rampas até 600 criações/s, 100 buscas/s e 40 buscas inválidas/s. Após POST aceito, a simulação consulta o recurso pelo cabeçalho `Location`.

O PostgreSQL usa volume persistente e mantém `fsync`, `synchronous_commit` e `full_page_writes` habilitados. O código espera o INSERT terminar antes do `201`. A contagem executa `SELECT count(*)` diretamente, sem cache. Os [limites observados no runtime](../benchmark/evidence/20261016T125218Z-baseline-host/docker-limits.json) confirmam as quotas dos quatro contêineres.

A [validação final](../benchmark/validation.json) confirmou **cinco testes locais e 51 testes/casos HTTP aprovados**, verificação de tipos, compilação, instalação reutilizável e preparação do Gatling. Os testes HTTP usaram a mesma fonte e imagem da campanha antes da carga. Depois da quarta execução, Nginx e APIs foram parados, o PostgreSQL foi reiniciado e os serviços voltaram à prontidão sem remover o volume: a contagem ficou em **31.757 antes e depois**, e a mesma pessoa foi relida com UUID e hash de conteúdo idênticos. Essa verificação não simula uma falha abrupta do host.

O host local é Intel Xeon Platinum 8573C, com cinco vCPUs visíveis, quota de **quatro CPUs** no cgroup pai e **32 GiB** de memória. O Docker 28.4.0 é aninhado, usa cgroups v2 e armazenamento `vfs`. O Gatling executa na mesma máquina, fora do orçamento dos contêineres, com heap de até 1 GiB e `ActiveProcessorCount=2`. CPU, armazenamento e geração de carga compartilham recursos do host. A validação final também reconfirmou os limites padrão: **1,5 CPU e 2.818.572.288 bytes** na soma dos quatro cgroups.

A campanha usa `docker-compose.yml` com `docker-compose.host.yml`: continuam existindo Nginx, duas APIs e banco em contêineres separados e limitados; o namespace de rede é compartilhado com o host. As duas primeiras corridas usam também `docker-compose.reference.yml`; a terceira usa `docker-compose.cpu-experiment.yml`; a quarta usa somente base e host. Os metadados registram os arquivos Compose, parâmetros, versões, hashes de fontes e IDs das imagens.

As medições foram realizadas com a implementação na árvore de trabalho, antes de commitá-la. O campo `git_commit` dos metadados é o HEAD inicial `c08dd33`, que continha somente o README e **não identifica a implementação testada**. A versão da aplicação é atestada pelos hashes dos arquivos e pelo ID da imagem em execução, `sha256:9fb5aeee3b1eacb61c75f18ba156ca1e0becd7f1f497bb52b7e50e6a9573105d`, comum à campanha. Os parâmetros e limites variam conforme cada experimento; os metadados devem ser consultados junto à evidência.

Houve uma tentativa anterior na rede bridge, em `20261016T124526Z-baseline`. A porta publicada passou a responder `ECONNREFUSED` enquanto o Nginx respondia `200` diretamente pelo IP do contêiner. Ela foi marcada `invalid_infrastructure`, preservada para auditoria e **excluída das tabelas, diferenças e gráficos de comparação**.

## Comparação histórica com a final de 2023

O [ranking final oficial](https://github.com/zanfranceschi/rinha-de-backend-2023-q3/blob/da99faf563c23dca43a5afa2ac31a34ca8cc39e6/README.md#resultado-da-etapa-final) é ordenado pela contagem persistida, sem fórmula que combine latência e vazão:

| Posição oficial | Participante | Pessoas persistidas | p99 publicado, respostas OK |
| --- | --- | ---: | ---: |
| 1 | viniciusfonseca | 44.936 | 17.418 ms |
| 2 | h4nkb31f0ng | 44.270 | 15.690 ms |
| 3 | grupo-2a | 44.200 | 17.668 ms |
| 4 | sofia_aripiprazole | 43.731 | 58.571 ms |
| 5 | lpicanco | 42.832 | 29.764 ms |
| 6 | isadora-souza | 42.612 | 57.327 ms |
| 7 | vimsos | 42.041 | 3.159 ms |
| 8 | jrodrigues | 41.193 | 44.445 ms |
| 9 | navarro | 39.356 | 23.958 ms |
| 10 | navarro-touche | 36.106 | 11.772 ms |

As quatro execuções ficaram abaixo das contagens dos dez finalistas. O padrão final, com **31.757 pessoas**, atingiu **70,67%** das 44.936 do vencedor (**13.179 a menos**). A maior contagem local, **34.163**, corresponde a **76,03%** do vencedor (**10.773 a menos**) e permanece abaixo das 36.106 pessoas do décimo colocado. Nenhuma posição oficial é atribuída à implementação local.

O p99 OK final de 11.115 ms e o de 12.607 ms da melhor contagem devem ser lidos junto aos respectivos **22,20% e 23,18% KO**. A latência das requisições OK não resume a qualidade de atendimento quando parte relevante da carga falha.

A coluna “p99 geral” do README oficial usa o p99 das requisições **OK** presente nos artefatos. No [relatório do vencedor](https://github.com/zanfranceschi/rinha-de-backend-2023-q3/blob/da99faf563c23dca43a5afa2ac31a34ca8cc39e6/resultados/final/viniciusfonseca/rinhabackendsimulation-20230826001734949/js/global_stats.json), `percentiles4.ok` é **17.418 ms** e `percentiles4.total` é **17.357 ms**. A tabela histórica usa a mesma métrica OK; as latências de todas as respostas da campanha local são apresentadas separadamente.

O [host original](https://github.com/zanfranceschi/rinha-de-backend-2023-q3/blob/da99faf563c23dca43a5afa2ac31a34ca8cc39e6/misc/lshw-aws) era uma EC2 `t3a.xlarge` com AMD EPYC 7571 e 16 GiB. São máquinas e condições de rede, armazenamento e disputa diferentes. O ranking serve para contextualizar os números; não demonstra como esta API se sairia naquela máquina em 2023.

## Artefatos e auditoria

| Execução | Horário local em 16/10/2026 | Evidência | Uso |
| --- | --- | --- | --- |
| Tentativa bridge | 09:45 BRT | [Execução excluída](../benchmark/evidence/20261016T124526Z-baseline/summary.json) | Diagnóstico de infraestrutura |
| Referência host | 09:52–09:56 BRT | [Resumo](../benchmark/evidence/20261016T125218Z-baseline-host/summary.json), [ambiente](../benchmark/evidence/20261016T125218Z-baseline-host/environment.json), [manifesto](../benchmark/evidence/20261016T125218Z-baseline-host/manifest.json) | Resultado da referência |
| Índice e cache host | 09:56–10:00 BRT | [Resumo](../benchmark/evidence/20261016T125656Z-indexed-cache-host/summary.json), [ambiente](../benchmark/evidence/20261016T125656Z-indexed-cache-host/environment.json), [manifesto](../benchmark/evidence/20261016T125656Z-indexed-cache-host/manifest.json) | Efeito conjunto de consulta e cache |
| CPU e memória redistribuídas host | 10:02–10:06 BRT | [Resumo](../benchmark/evidence/20261016T130257Z-tuned-host/summary.json), [ambiente](../benchmark/evidence/20261016T130257Z-tuned-host/environment.json), [manifesto](../benchmark/evidence/20261016T130257Z-tuned-host/manifest.json) | Regressão observada |
| Só memória redistribuída host | 10:08–10:12 BRT | [Resumo](../benchmark/evidence/20261016T130832Z-memory-host/summary.json), [ambiente](../benchmark/evidence/20261016T130832Z-memory-host/environment.json), [manifesto](../benchmark/evidence/20261016T130832Z-memory-host/manifest.json) | Padrão operacional escolhido |

Os nomes de diretórios usam **UTC** (`Z`), três horas à frente de BRT. Por exemplo, `20261016T125218Z` corresponde a 16/10/2026 às 09:52:18 BRT. A data da pasta registra a preparação da execução, antes do início das requisições.

Cada pacote em `benchmark/evidence/` inclui o relatório Gatling completo compactado, logs, metadados, contagem, série temporal, manifesto e `SHA256SUMS`. Para validar os arquivos de uma execução:

```bash
cd benchmark/evidence/20261016T125218Z-baseline-host
sha256sum -c SHA256SUMS
```

Extraia `gatling-report.tar.gz` e abra o `index.html` dentro do diretório da simulação para explorar o relatório interativo. Os comandos para repetir a carga e gerar figuras estão no [README](../README.md#reproduzir-a-carga-oficial).

## Limites das conclusões

Há uma execução por configuração. O experimento permanece exploratório, sem estimativa de variância ou significância estatística. Cache e caminho de busca mudam juntos na primeira comparação. A terceira altera CPU e memória em conjunto; a quarta permite contrastar essas distribuições em etapas, mas não elimina a variabilidade entre corridas. Também permanece o custo de manutenção do GIN na referência.

Os próximos experimentos úteis são repetir as combinações de cache e consulta separadamente, verificar os planos SQL e acompanhar saturação do pool e memória do Nginx. Ampliar conexões sem reduzir o custo das consultas pode apenas aumentar a disputa pelo mesmo orçamento do banco.
