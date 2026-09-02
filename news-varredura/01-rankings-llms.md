# Rankings de LLMs

Coletado em 2026-09-02. Leaderboard é foto, não filme. Toda citação precisa de data.

---

## Artificial Analysis, Intelligence Index

Lido direto de `artificialanalysis.ai/leaderboards/models` em 2026-09-02. **[A]**

| # | Modelo | Índice | Provedor | Contexto | Custo por tarefa |
|---|---|---|---|---|---|
| 1 | Claude Fable 5.1 (max com fallback) | 66 | Anthropic | 1M | US$ 3,69 |
| 2 | Claude Fable 5.1 (xhigh com fallback) | 65 | Anthropic | 1M | US$ 2,65 |
| 3 | Claude Opus 5 (max) | 63 | Anthropic | 1M | US$ 2,34 |
| 4 | Claude Opus 5 (xhigh) | 63 | Anthropic | 1M | US$ 1,80 |
| 5 | Claude Fable 5.1 (high com fallback) | 62 | Anthropic | 1M | US$ 1,43 |

Velocidade de saída no topo entre 47 e 66 tokens por segundo.

O detalhe interessante para copy. O mesmo modelo aparece várias vezes com esforço de
raciocínio diferente. Fable 5.1 vai de 62 a 66 pontos e o custo por tarefa mais que dobra,
de US$ 1,43 para US$ 3,69. A escolha de esforço virou variável de projeto, do mesmo jeito
que escolher o modelo.

## Arena, Elo de texto

Lido direto de `arena.ai/leaderboard/text` em 2026-09-02. 398 modelos, perto de 8 milhões
de votos. **[A]**

| # | Modelo | Elo | Organização | Licença |
|---|---|---|---|---|
| 1 | claude-fable-5 | 1508 ± 5 | Anthropic | Proprietária |
| 2 | claude-opus-4-6-high | 1505 ± 4 | Anthropic | Proprietária |
| 3 | claude-opus-4-7-high | 1502 ± 4 | Anthropic | Proprietária |
| 4 | muse-spark-1.2 (xHigh) | 1499 ± 10 | Meta | Proprietária |
| 5 | claude-opus-4-6 | 1498 ± 3 | Anthropic | Proprietária |

Atenção ao intervalo de confiança. Do 1º ao 5º a diferença é de 10 pontos de Elo com margens
de 3 a 10 pontos. Na prática o topo é um empate técnico. Dizer "modelo X é o melhor do mundo"
com base em Elo é imprecisão que um comprador técnico percebe.

O domínio da lmarena migrou para `arena.ai`. O link antigo devolve 301.

## Arena, leaderboard de agentes

Eixo novo e mais relevante que o Elo de texto para quem vende automação. Claude Opus 5 em
primeiro com 13,74%, Claude Opus 5 Max em segundo. **[A]**

A existência de um leaderboard separado para agentes é o sinal em si. Habilidade
conversacional e habilidade agêntica descolaram como métricas.

## Benchmarks de engenharia

Números coletados por busca, sem abertura do primário. Confirmar antes de publicar. **[C]**

| Benchmark | Líder | Marca |
|---|---|---|
| SWE-bench Verified | Claude Fable 5 | 95,0% |
| SWE-bench Verified (mai/2026) | Claude Mythos Preview | 93,9% |
| Terminal-Bench 2.1 | GPT-5.6 Sol | 89,5% |
| Terminal-Bench 2.1 | Claude Opus 5 | 89,1% |

Contexto que dá credibilidade a quem cita. O SWE-bench virou insuficiente sozinho. Surgiram
SetupBench para preparo de ambiente, SWE-Bench Pro para horizonte longo, SEC-bench para
segurança, Terminal-Bench e LongCLI-Bench para linha de comando. Existe literatura de 2026
argumentando que benchmarks de código estão desalinhados da engenharia de software agêntica
de verdade.

## Epoch Capabilities Index

O ECI resolve a saturação de benchmark. Benchmarks individuais saturam em meses, o que impede
comparar progresso ao longo do tempo. O ECI agrega vários deles numa escala única usando um
modelo de traço latente unidimensional. **[B]**

O achado que vale citar. O ritmo de melhoria da fronteira quase dobrou, de cerca de 8 pontos
por ano para 15 pontos por ano, com a virada em abril de 2024. A aceleração coincide com a
chegada dos modelos de raciocínio e com o peso crescente do aprendizado por reforço nos
laboratórios de fronteira.

## Como usar rankings em criativo sem se queimar

1. Sempre datar. "Em setembro de 2026, segundo o Artificial Analysis."
2. Preferir a tendência à posição. A posição muda em semanas, a tendência sustenta um ano.
3. Citar o intervalo de confiança quando existir. Sinaliza rigor.
4. Nunca misturar boards. Elo de Arena, Intelligence Index e SWE-bench medem coisas
   diferentes e não se somam.
5. Desconfiar de sites de leaderboard que aparecem bem no Google e não publicam metodologia.
   A varredura encontrou vários. Os que têm metodologia aberta são Artificial Analysis,
   Arena, Epoch AI e os leaderboards oficiais de cada benchmark.

## Fontes

- [Artificial Analysis, leaderboard de modelos](https://artificialanalysis.ai/leaderboards/models)
- [Arena, leaderboard de texto](https://arena.ai/leaderboard/text)
- [Epoch Capabilities Index](https://epoch.ai/eci)
- [Epoch AI, o avanço de capacidades acelerou](https://epoch.ai/data-insights/ai-capabilities-progress-has-sped-up)
