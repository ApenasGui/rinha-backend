# NestJS na Rinha de Backend: de 8.261 para 31.757 pessoas com o mesmo orçamento

> Texto para revisão antes de publicar.

Implementei a edição 2023 Q3 da Rinha de Backend em NestJS 11, Fastify e PostgreSQL 16. Duas APIs, Nginx e banco dividem **1,5 CPU e 2.688 MiB de memória**, abaixo dos 3 GB permitidos. Rodei o Gatling oficial com os dados e o perfil originais, começando cada corrida com banco vazio.

A configuração final persistiu **31.757 pessoas**, **3,84 vezes** a referência de 8.261, sem eventos OOM observados nessa corrida. Ainda houve **22,20% de falhas nos checks**, com p99 das respostas OK de **11.115 ms**. A carga de pico continua acima da capacidade de atendimento.

| Configuração | Pessoas persistidas | KO | Eventos OOM no Nginx |
| --- | ---: | ---: | ---: |
| Referência, busca por varredura e cache desligado | 8.261 | 69,01% | 2 |
| Pré-filtro indexado e cache | 34.163 | 23,18% | 2 |
| CPU e memória redistribuídas | 31.346 | 25,07% | 0 |
| Só memória redistribuída, padrão final | 31.757 | 22,20% | 0 |

![Comparação das quatro configurações sob a carga oficial](assets/comparacao.png)

A busca usa `pg_trgm` sobre uma coluna de apoio e depois verifica cada campo separadamente. Essa segunda etapa evita correspondências que atravessam campos concatenados. Para leitura por UUID, há cache FIFO de até 10.000 pessoas por réplica. Como o contrato não tem edição nem exclusão, entradas positivas permanecem válidas; a outra réplica consulta o banco quando necessário.

A API aguarda o INSERT antes do `201`, deixa o índice único resolver apelidos concorrentes e mantém a durabilidade do PostgreSQL habilitada. A contagem consulta o banco diretamente. Após reiniciar banco e APIs, as 31.757 pessoas continuaram lá, e a mesma pessoa foi relida com conteúdo idêntico. O índice permaneceu no esquema de todas as configurações: a primeira comparação muda o caminho da consulta e o cache, sem remover o custo do GIN nas gravações.

Também houve uma hipótese que falhou. O banco saturava CPU, e o consumo mediano das APIs parecia deixar folga. Transferi 0,20 CPU das APIs para o PostgreSQL e 128 MiB do banco para o Nginx. A contagem caiu **8,25%**, e o p99 OK piorou para 18.433 ms, mesmo sem OOM. Utilização mediana foi insuficiente para justificar o corte de CPU nas APIs.

Restaurei a CPU e conservei a memória redistribuída. Escolhi essa quarta configuração pelos menores KO/p99 OK e zero OOM observado. Ela persiste **7,04% menos pessoas** que a maior contagem, de 34.163: pelo critério do ranking, a segunda corrida continua melhor.

O vencedor de 2023 registrou **44.936 pessoas**. Meu padrão final atingiu **70,67% dessa contagem**; a melhor contagem local, **76,03%**. Ambas ficaram abaixo das 36.106 pessoas do décimo finalista. O hardware é diferente, com Docker aninhado e Gatling compartilhando o host; esta é uma comparação histórica, sem colocação oficial.

O aprendizado foi medir também regressões, falhas e pressão de recursos. Houve uma corrida por configuração, e índice/cache mudaram juntos: os números são exploratórios, sem demonstrar estabilidade ou atribuir o ganho individual a cada técnica. Repetições e testes separados dessas escolhas seriam o próximo passo.

Código, relatório completo e comandos para reproduzir: [ApenasGui/rinha-backend](https://github.com/ApenasGui/rinha-backend). [Gráfico PNG para compartilhar](assets/comparacao.png).

#NestJS #Docker #PostgreSQL #Backend #RinhaDeBackend
