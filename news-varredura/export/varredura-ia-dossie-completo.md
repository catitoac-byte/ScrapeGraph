# Varredura de Internet sobre IA, dossiê completo

Documento único e autossuficiente. Reúne os 13 arquivos da vertical `news-varredura`
do projeto ScrapeGraph, exportados em 2026-09-02.

**Varredura de referência:** 2026-09-02.
**Conteúdo:** 73 fatos citáveis (24 nível A, 39 nível B,
10 nível C), 39 fontes catalogadas, 73 arquivos de bibliografia
analisados.

## Como usar este documento em outro projeto

Ele foi escrito para embasar criativos, textos comerciais e narrativa de expertise em IA,
automação e pesquisa de mercado, sempre com fonte real e datada.

A regra que governa tudo aqui é o nível de confiança de cada afirmação.

| Nível | Significado | Pode ir para peça publicada |
|---|---|---|
| **A** | Fonte primária aberta e lida na varredura | Sim, com citação e data |
| **B** | Fonte primária citada por terceiro confiável | Sim, checando o primário antes |
| **C** | Fonte secundária ou agregador de SEO | Não. Serve de pista de pesquisa |

Números de nível C existem de propósito. Indicam onde vale investir uma checagem.

Leaderboards mudam em semanas. Toda citação de ranking precisa sair acompanhada da data.

## Índice

1. News Varredura Internet  
2. Sumário executivo  
3. Rankings de LLMs  
4. Modelos abertos contra proprietários  
5. Harness, orquestração e agentes  
6. Agent Skills e context engineering  
7. Embeddings, recuperação e RAG  
8. Metodologias de ponta  
9. Mercado, adoção e ROI  
10. IA em pesquisa de mercado e insights  
11. Fontes para acompanhar  
12. Achados da varredura  
13. Biblioteca de fundamentos  

---

## News Varredura Internet

Vertical de inteligência sobre IA para embasar criativos, textos comerciais e a narrativa
de expertise da empresa em automação, IA e pesquisa de mercado.

A regra desta pasta é simples. Nenhum número entra num criativo sem fonte, URL e data.

### Varredura de referência

Primeira varredura completa em **2026-09-02**.

### Como está organizado

| Arquivo | O que cobre |
|---|---|
| `00-sumario-executivo.md` | Os 20 fatos mais citáveis, prontos para copy |
| `01-rankings-llms.md` | Rankings, benchmarks, quem lidera o quê |
| `02-abertos-vs-pagos.md` | Modelos de peso aberto contra proprietários, custo |
| `03-harness-e-agentes.md` | Harness, orquestração, MCP, agentes em produção |
| `04-skills-context-engineering.md` | Agent Skills, context engineering, progressive disclosure |
| `05-embeddings-rag.md` | Embeddings, MTEB, RAG agêntico, reranking, context rot |
| `06-metodologias-de-ponta.md` | RLVR, evals, LLM as judge, pós-treino |
| `07-mercado-adocao-roi.md` | Adoção corporativa, investimento, a taxa real de fracasso |
| `08-ia-pesquisa-de-mercado.md` | O setor de insights, GRIT, respondentes sintéticos |
| `09-fontes-para-acompanhar.md` | Livros, blogs, cursos, newsletters, papers, leaderboards |
| `10-achados-da-varredura.md` | O que a varredura automática trouxe de novo, com correções |
| `11-fundamentos-biblioteca.md` | Curadoria da bibliografia de fundamentos, com caminho legítimo |
| `dados/fatos-citaveis.csv` | Base estruturada de claims com fonte, data e nível de confiança |
| `dados/fontes.csv` | Catálogo de fontes com feed RSS quando existe |
| `dados/biblioteca-anthropic.csv` | Arquivo completo de 44 posts de engenharia e pesquisa da Anthropic |
| `raspar_news_ia.py` | Varredura recorrente por RSS, Atom e arXiv |

### Níveis de confiança

Toda afirmação carrega um nível. Isso define o que pode ir para um criativo público.

| Nível | Significado | Pode publicar |
|---|---|---|
| **A** | Fonte primária aberta e lida diretamente nesta varredura | Sim, com citação |
| **B** | Fonte primária citada por terceiro confiável, não aberta direto | Sim, checando o primário antes |
| **C** | Fonte secundária ou agregador de SEO | Não. Serve de pista, precisa de confirmação |

Números de nível C existem aqui de propósito. Eles indicam onde vale investir uma checagem,
não servem de munição para peça publicada.

### Rotina sugerida

1. Rodar `python3 raspar_news_ia.py` toda segunda. A saída datada cai em `dados/saida/`.
2. Ler o digest, promover o que for relevante para o arquivo temático correspondente.
3. Antes de qualquer peça, filtrar `dados/fatos-citaveis.csv` por `confianca` igual a A ou B.
4. Reconferir números de nível A a cada trimestre. Leaderboard muda rápido.

### O script de varredura

`raspar_news_ia.py` roda sem dependência externa, só biblioteca padrão.

```bash
python3 raspar_news_ia.py              # janela de 14 dias
python3 raspar_news_ia.py --dias 30    # janela maior
python3 raspar_news_ia.py --verificar  # testa se todas as fontes respondem
python3 raspar_news_ia.py --tudo       # sem filtro de palavra chave
```

Ele cobre 22 fontes vivas. Dezesseis por RSS ou Atom, seis por raspagem de HTML porque não
publicam feed, e mais quatro consultas ao arXiv. A saída são dois arquivos datados em
`dados/saida/`, um CSV para filtrar e um markdown para ler.

As fontes que não têm feed e precisam de checagem manual estão em `dados/fontes.csv` com
status `sem feed`. São justamente os leaderboards e os relatórios anuais, que mudam devagar e
compensam olhar de mês em mês.

Primeira execução em 2026-09-02, janela de 21 dias. 272 itens relevantes de 3.224 coletados.

---

## Sumário executivo

Varredura de 2026-09-02. Os fatos abaixo são os mais úteis para copy, apresentação comercial
e posicionamento de expertise. Cada um traz fonte, data e nível de confiança.

---

### Os 20 fatos mais citáveis

#### Adoção e mercado

**1.** 88% das organizações já usam IA em ao menos uma função de negócio.
*Stanford HAI, AI Index Report 2026, mar/2026.* **[A]**

**2.** IA generativa chegou a 53% de adoção populacional em três anos. Mais rápido que o
computador pessoal e mais rápido que a internet.
*Stanford HAI, AI Index Report 2026.* **[A]**

**3.** O investimento privado dos EUA em IA foi de US$ 285,9 bilhões em 2025, mais de 23 vezes
o da China, que ficou em US$ 12,4 bilhões.
*Stanford HAI, AI Index Report 2026.* **[A]**

**4.** O valor anual estimado das ferramentas de IA generativa para o consumidor americano
chegou a US$ 172 bilhões no início de 2026. O valor mediano por usuário triplicou entre
2025 e 2026.
*Stanford HAI, AI Index Report 2026.* **[A]**

**5.** O gasto empresarial com APIs de LLM saltou de US$ 3,5 bilhões no fim de 2024 para
US$ 8,4 bilhões. A Anthropic passou a Open AI e ficou com 40% do share, contra 27% da
Open AI, que tinha 50% em 2023.
*Menlo Ventures, State of Generative AI.* **[B]**

#### O contraste que vende consultoria

**6.** 95% dos pilotos de IA generativa não entregam ROI mensurável. O estudo ouviu 52
executivos, pesquisou 153 líderes e analisou 300 implantações públicas.
*MIT, GenAI Divide.* **[B]**

**7.** Só 31% das organizações têm um agente rodando em produção.
*S&P Global Market Intelligence.* **[B]**

**8.** A adoção de agentes segue em um dígito em quase toda função de negócio, mesmo com 88%
de adoção geral de IA.
*Stanford HAI, AI Index Report 2026.* **[A]**

> **Ângulo de copy.** A distância entre o item 1 e o item 8 é o mercado inteiro. Todo mundo
> comprou IA. Quase ninguém colocou agente em produção. A causa apontada nos estudos não é o
> modelo, é integração com dado institucional real e ausência de infraestrutura de medição.

#### Capacidade e ritmo

**9.** No SWE-bench Verified, o desempenho subiu de 60% para perto de 100% da baseline humana
em um único ano.
*Stanford HAI, AI Index Report 2026.* **[A]**

**10.** Agentes de IA passaram de 12% para cerca de 66% de sucesso em tarefas reais de
computador.
*Stanford HAI, AI Index Report 2026.* **[A]**

**11.** O ritmo de avanço da fronteira praticamente dobrou, de cerca de 8 pontos por ano para
15 pontos por ano no Epoch Capabilities Index. A virada coincide com a chegada dos modelos de
raciocínio e do foco em aprendizado por reforço.
*Epoch AI, Epoch Capabilities Index.* **[B]**

#### Custo

**12.** O custo de inferência cai cerca de 10 vezes por ano. Desempenho equivalente ao GPT-4,
que custava perto de US$ 30 por milhão de tokens no início de 2023, hoje sai por menos de
um dólar.
*Compilação de análises de preço, 2026.* **[C]**

**13.** O custo por token cai pela metade a cada 2,6 meses aproximadamente.
*Compilação de análises de preço, 2026.* **[C]**

#### Modelos abertos

**14.** A distância entre o melhor modelo proprietário e o melhor de peso aberto está em 3,4
pontos no Artificial Analysis Intelligence Index. Kimi K3 marca 59,7 contra 63,1 do
Claude Opus 5.
*Artificial Analysis.* **[B]**

**15.** Em código a distância cai para 2,1 pontos e em tarefas agênticas também 2,1 pontos.
No raciocínio mais difícil ela persiste. No HLE os abertos ficam em 34% a 36% contra 44% a
45% dos proprietários.
*Artificial Analysis.* **[B]**

**16.** Kimi K3, aberto em 27/jul/2026, é o maior modelo aberto já lançado. 2,8 trilhões de
parâmetros totais, 104 bilhões ativos, 896 experts, contexto de 1 milhão de tokens, visão e
vídeo nativos.
*Moonshot AI.* **[B]**

#### Agentes, harness e skills

**17.** O Model Context Protocol virou padrão de fato em 18 meses. 97 milhões de downloads
mensais de SDK em mar/2026, com suporte de Anthropic, Open AI, Google, Microsoft e AWS.
*Documentação e reportagem sobre MCP.* **[B]**

**18.** Desenho de harness muda o resultado de forma brutal. No experimento da Anthropic, um
agente solo levou 20 minutos e US$ 9. O harness completo com planner, generator e evaluator
levou 6 horas e US$ 200. Vinte vezes mais caro, com qualidade incomparavelmente superior.
*Anthropic Engineering, Harness design for long-running application development, 24/mar/2026.* **[A]**

**19.** Agent Skills virou padrão aberto e foi adotado por Cursor, GitHub Copilot, Open AI
Codex e Gemini CLI. Um skill custa de 50 a 100 tokens no startup e só carrega o corpo
completo quando é relevante.
*Anthropic e agentskills.io.* **[B]**

**20.** Times que dominam context engineering completam tarefas 55% mais rápido e cometem 40%
menos erros.
*Anthropic, Agentic Coding Trends Report 2026.* **[B]**

---

### Três narrativas prontas

#### Narrativa 1. O abismo entre comprar IA e operar IA

88% das empresas usam IA. 95% dos pilotos não entregam ROI. Só 31% têm agente em produção.
A conclusão dos estudos é sempre a mesma. O gargalo não está no modelo, está em conectar o
agente a dado institucional real e em construir a medição que prova que aquilo funciona.

Serve para. Abertura de proposta, pitch de diagnóstico, post de LinkedIn contra o hype.

#### Narrativa 2. O modelo virou commodity, o sistema em volta não

A distância entre o melhor modelo aberto e o melhor proprietário caiu para 3,4 pontos. O custo
de inferência cai pela metade a cada 2,6 meses. Ao mesmo tempo, o mesmo modelo dentro de um
harness bem desenhado produz resultado incomparável ao de uma chamada solta. Vinte vezes mais
caro em compute e ainda assim a escolha certa.

Serve para. Justificar preço de projeto, explicar por que a entrega não é "plugar uma API".

#### Narrativa 3. Pesquisa de mercado no ponto de virada

67% dos fornecedores de pesquisa já embutem IA generativa direto no entregável ao cliente.
Dado sintético saltou de nicho para os três temas mais comentados do setor. E a preocupação
com qualidade de dado subiu 40% no ano, com respondente sintético apontado como causa
principal. O setor está dividido entre profundidade humana e velocidade de máquina.

Serve para. Conteúdo para o público de insights, diferenciação contra fornecedores que só
empacotam LLM.

*Fonte da narrativa 3. GRIT Insights Practice Report 2026, Greenbook, jun/2026.* **[B]**

---

### O que evitar dizer

- Não citar "95% dos pilotos falham" sem dizer que o estudo é do MIT e explicar a metodologia.
  O número é o mais contestado do setor e vira munição contra quem usa mal.
- Não citar posição de leaderboard sem data. Artificial Analysis e Arena mudam em semanas.
- Não usar números marcados com **[C]** em peça pública. São pistas de pesquisa.
- Não apresentar respondente sintético como substituto de voz real do cliente. As próprias
  plataformas do setor posicionam sintético como pré-teste de hipótese.

---

## Rankings de LLMs

Coletado em 2026-09-02. Leaderboard é foto, não filme. Toda citação precisa de data.

---

### Artificial Analysis, Intelligence Index

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

### Arena, Elo de texto

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

### Arena, leaderboard de agentes

Eixo novo e mais relevante que o Elo de texto para quem vende automação. Claude Opus 5 em
primeiro com 13,74%, Claude Opus 5 Max em segundo. **[A]**

A existência de um leaderboard separado para agentes é o sinal em si. Habilidade
conversacional e habilidade agêntica descolaram como métricas.

### Benchmarks de engenharia

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

### Epoch Capabilities Index

O ECI resolve a saturação de benchmark. Benchmarks individuais saturam em meses, o que impede
comparar progresso ao longo do tempo. O ECI agrega vários deles numa escala única usando um
modelo de traço latente unidimensional. **[B]**

O achado que vale citar. O ritmo de melhoria da fronteira quase dobrou, de cerca de 8 pontos
por ano para 15 pontos por ano, com a virada em abril de 2024. A aceleração coincide com a
chegada dos modelos de raciocínio e com o peso crescente do aprendizado por reforço nos
laboratórios de fronteira.

### Como usar rankings em criativo sem se queimar

1. Sempre datar. "Em setembro de 2026, segundo o Artificial Analysis."
2. Preferir a tendência à posição. A posição muda em semanas, a tendência sustenta um ano.
3. Citar o intervalo de confiança quando existir. Sinaliza rigor.
4. Nunca misturar boards. Elo de Arena, Intelligence Index e SWE-bench medem coisas
   diferentes e não se somam.
5. Desconfiar de sites de leaderboard que aparecem bem no Google e não publicam metodologia.
   A varredura encontrou vários. Os que têm metodologia aberta são Artificial Analysis,
   Arena, Epoch AI e os leaderboards oficiais de cada benchmark.

### Fontes

- [Artificial Analysis, leaderboard de modelos](https://artificialanalysis.ai/leaderboards/models)
- [Arena, leaderboard de texto](https://arena.ai/leaderboard/text)
- [Epoch Capabilities Index](https://epoch.ai/eci)
- [Epoch AI, o avanço de capacidades acelerou](https://epoch.ai/data-insights/ai-capabilities-progress-has-sped-up)

---

## Modelos abertos contra proprietários

Coletado em 2026-09-02.

---

### A distância atual

Segundo o Artificial Analysis, a diferença entre o melhor proprietário e o melhor de peso
aberto está em **3,4 pontos** no Intelligence Index. **[B]**

| Índice | Melhor aberto | Melhor proprietário | Distância |
|---|---|---|---|
| Intelligence Index | Kimi K3 (max), 59,7 | Claude Opus 5, 63,1 | 3,4 |
| Coding Index | Kimi K3 (max), 76,2 | GPT-5.6 Sol (xhigh), 78,3 | 2,1 |
| Agentic Index | Qwen3.8 2.4T A95B, 57,1 | Claude Opus 5, 59,2 | 2,1 |
| HLE | 34% a 36% | 44% a 45% | 8 a 11 pontos |

A leitura correta. Em tarefa comum a distância é quase irrelevante. No raciocínio mais duro
ela continua grande. Quem vende projeto precisa saber separar as duas coisas, porque a decisão
de usar aberto ou proprietário depende de qual dos dois regimes o caso de uso vive.

A Epoch AI estima que os melhores modelos de peso aberto ficam em média quatro meses atrás da
fronteira fechada desde janeiro de 2026, o equivalente a cerca de oito pontos no ECI. **[B]**

### Os lançamentos abertos de 2026

Entre abril e julho de 2026 saíram GLM 5.2, Kimi K3, Kimi K2.7 Code, MiniMax M3 e
DeepSeek V4 Pro. **[B]**

#### Kimi K3, Moonshot AI
Aberto em 27/jul/2026. Maior modelo aberto já lançado. 2,8 trilhões de parâmetros totais,
104 bilhões ativos, 896 experts, contexto de 1 milhão de tokens, visão e vídeo nativos.
Licença própria com limiar de receita comercial, ou seja, não é permissiva de verdade acima
de certo faturamento. Terminal-Bench 2.1 em 88,3.

#### GLM 5.2, Zhipu AI
Licença MIT, contexto de 1 milhão, GPQA Diamond em 91,2%. A licença MIT é o diferencial
comercial contra o Kimi.

#### DeepSeek V4
V4 Pro com 1,6 trilhão de parâmetros totais e contexto perto de 1,04 milhão. V4 Flash com
284 bilhões, mesma classe de contexto, mais throughput e menos custo. Licença MIT.

#### Qwen, Alibaba
Qwen 3.6 com pesos no Hugging Face. Qwen 3.7 Max saiu em 19/mai/2026 só por API, sem pesos
publicados. Vale registrar o movimento. A linha topo de gama do Qwen fechou.

### O ponto de licença que quase ninguém checa

"Peso aberto" e "open source" não são a mesma coisa. Na varredura apareceram três regimes
distintos no mesmo grupo de modelos ditos abertos.

1. **MIT de verdade.** GLM 5.2 e DeepSeek V4. Uso comercial livre.
2. **Licença própria com gatilho de receita.** Kimi K3. Acima de certo faturamento a coisa
   muda.
3. **Aberto na geração anterior, fechado no topo.** Qwen 3.6 aberto, Qwen 3.7 Max só API.

Para proposta comercial isso importa mais que meio ponto de benchmark. Vale colocar a
verificação de licença como item de checklist de arquitetura.

### Custo, o argumento mais forte

O custo de inferência caiu cerca de 10 vezes por ano, uma das quedas de preço mais rápidas da
história da computação. **[C]**

- Desempenho classe GPT-4 saiu de perto de US$ 30 por milhão de tokens no início de 2023 para
  menos de um dólar em 2026.
- O custo por token cai pela metade a cada 2,6 meses aproximadamente.
- A queda por marco de capacidade varia de 9 a 900 vezes por ano, com mediana perto de 50.

Todos os números acima vieram de agregadores e análises secundárias. São coerentes entre si e
com a tendência conhecida, e ainda assim precisam de confirmação numa fonte primária antes de
ir para peça publicada. O caminho de confirmação é a série histórica de preços do
Artificial Analysis e o AI Index da Stanford.

### Ângulo de posicionamento

O barateamento derruba o argumento de que IA é cara. Ele também derruba o argumento de que o
modelo é o diferencial. Se a capacidade fica barata e o gap aberto contra fechado é de três
pontos, o valor migra para três lugares.

1. O dado que só o cliente tem.
2. O harness e a orquestração em volta do modelo.
3. A medição que prova que aquilo funcionou.

Esses três são exatamente onde uma empresa de automação e pesquisa entrega. É a ponte natural
entre a varredura técnica e o discurso comercial.

### Fontes

- [Artificial Analysis, lançamentos recentes de peso aberto](https://artificialanalysis.ai/articles/recent-open-weights-model-launches)
- [Artificial Analysis, Openness Index](https://artificialanalysis.ai/evaluations/artificial-analysis-openness-index)
- [Epoch Capabilities Index](https://epoch.ai/eci)

---

## Harness, orquestração e agentes

Coletado em 2026-09-02. Este é o tema mais denso da varredura e o mais diretamente ligado ao
que a empresa vende.

---

### O que é um harness

Harness é o arcabouço de orquestração que estrutura o comportamento do modelo em tarefas
longas e complexas. Ele define decomposição, gestão de contexto e passagem de bastão entre
sessões. A frase da própria Anthropic é direta. O desenho do harness tem impacto substancial
na eficácia de código agêntico de longa duração.

Fonte primária lida direto. Anthropic Engineering, *Harness design for long-running
application development*, 24/mar/2026. **[A]**

### A arquitetura de três agentes

| Papel | Função | Detalhe que importa |
|---|---|---|
| **Planner** | Expande um prompt curto em especificação detalhada de produto | Escopo ambicioso, sem superespecificar implementação técnica |
| **Generator** | Implementa as features seguindo a spec | Começou em sprints discretos, foi simplificado quando os modelos passaram a sustentar sessões longas |
| **Evaluator** | Testa o resultado de forma interativa via Playwright e dá nota contra critérios concretos | Separado da geração de propósito |

O motivo de separar o avaliador é o achado mais transferível de todos. Agentes tendem a
elogiar o próprio trabalho com confiança, mesmo quando a qualidade é obviamente medíocre.
Autoavaliação não funciona. Julgamento precisa de um agente com contexto e incentivo
diferentes.

### Os números do experimento

| Cenário | Tempo | Custo |
|---|---|---|
| Agente solo, criador de jogos | 20 minutos | US$ 9 |
| Harness completo, criador de jogos | 6 horas | US$ 200 |
| Harness simplificado (Opus 4.6), aplicação DAW | 3h50 | US$ 124,70 |

Vinte vezes mais caro em compute, com qualidade de saída dramaticamente superior. Este par de
números é o melhor argumento disponível contra a ideia de que automação com IA é "plugar uma
API". **[A]**

### As quatro lições de desenho

1. **Separação de responsabilidades.** Desacoplar avaliação de geração produz julgamento
   melhor que autoavaliação.
2. **Passagem de bastão estruturada.** Usar arquivos para comunicação entre agentes preserva
   contexto entre sessões.
3. **Simplificação progressiva.** Remover componentes conforme os modelos melhoram evita
   dívida técnica. O harness de hoje precisa ser menor que o de ontem.
4. **Critérios verificáveis.** Converter julgamento subjetivo em padrão mensurável, por
   exemplo qualidade de design, originalidade, acabamento e funcionalidade, é o que permite
   nota consistente.

### O harness anterior, ainda útil

Anthropic Engineering, *Effective harnesses for long-running agents*, 26/nov/2025. Arquitetura
de duas partes para o problema de que agentes trabalham em sessões discretas e cada sessão
nova começa sem memória. **[A]**

**Initializer.** Monta o ambiente na primeira rodada, cria um `init.sh` para subir o servidor,
gera lista de features em JSON, com mais de 200 features no exemplo do claude.ai, inicializa
o repositório git e produz um `claude-progress.txt` de histórico.

**Coding agent.** Ataca uma feature por vez. Começa cada sessão lendo os arquivos de progresso
e o log do git. Roda teste ponta a ponta básico antes de implementar. Faz commit com mensagem
descritiva. Só marca a feature como concluída depois de testar de verdade.

| Falha | Correção |
|---|---|
| Agente tenta fazer tudo ao mesmo tempo | Trabalho incremental de uma feature por vez |
| Declara o projeto pronto cedo demais | Lista estruturada de features impede a falsa vitória |
| Progresso e bugs não documentados | Commits e arquivo de progresso permitem recuperação |
| Teste insuficiente | Automação de browser para verificação ponta a ponta |

Achado relevante para arquitetura. Compactação de contexto sozinha não sustenta desempenho ao
longo de várias janelas. Precisa de estado externo em arquivo.

### Model Context Protocol

O MCP virou padrão de fato de integração de agentes em 18 meses desde a abertura em novembro
de 2024. **[B]**

- 97 milhões de downloads mensais de SDK em março de 2026.
- Suporte de Anthropic, Open AI, Google, Microsoft e AWS.
- Especificação `2026-07-28`. A mudança estrutural foi sair de protocolo bidirecional com
  estado para requisição e resposta sem estado, o que destrava escala empresarial.
- 28% das empresas da Fortune 500 já implantaram servidores MCP.
- Projeção Gartner. Até o fim de 2026, 40% das aplicações empresariais devem trazer agentes
  específicos de tarefa e 75% dos fornecedores de API gateway devem ter recursos de MCP.

O que isso significa comercialmente. A camada de conexão entre agente e sistema virou
commodity padronizada. Quem vendia integração ponto a ponto perdeu o produto. O valor migrou
para o que se faz com a conexão.

### Agentes em produção, o retrato honesto

- Só 31% das organizações têm um agente rodando em produção. *S&P Global.* **[B]**
- 88% dos pilotos de agente nunca chegam a produção. **[C]**
- A implantação de agentes segue em um dígito em quase toda função de negócio.
  *Stanford AI Index 2026.* **[A]**
- Agentes de IA melhoraram de 12% para cerca de 66% de sucesso em tarefas reais de computador.
  *Stanford AI Index 2026.* **[A]**

A causa apontada nos estudos não é o modelo. É integração ruim e prioridade desalinhada. O
padrão comum entre quem deu certo é um só. Agentes conectados a dado institucional real, não
chatbot com prompt de sistema.

### Tendências de código agêntico

Anthropic, *Agentic Coding Trends Report* 2026. **[B]**

- Desenvolvedores usam IA em cerca de 60% do trabalho.
- Ainda assim conseguem delegar totalmente entre 0% e 20% das tarefas.
- 2026 marca a virada de assistente único para times de agentes coordenados, capazes de rodar
  autonomamente por horas ou dias.
- O engenheiro migra de escrever código para orquestrar os sistemas que escrevem código.

O par 60% contra 0 a 20% é ótimo para copy. Ele desarma tanto o cético quanto o entusiasta na
mesma frase.

### Fontes

- [Anthropic Engineering](https://www.anthropic.com/engineering)
- [Harness design for long-running application development](https://www.anthropic.com/engineering/harness-design-long-running-apps)
- [Effective harnesses for long-running agents](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents)
- [Especificação MCP 2026-07-28](https://blog.modelcontextprotocol.io/posts/2026-07-28/)
- [Arena, leaderboard de agentes](https://arena.ai/leaderboard)

---

## Agent Skills e context engineering

Coletado em 2026-09-02.

---

### Context engineering, a definição que funciona

Context engineering é a prática de desenhar deliberadamente o que o modelo vê em cada chamada
de inferência. A formulação da Anthropic. O conjunto de estratégias para curar e manter o
conjunto ótimo de tokens durante a inferência, incluindo toda informação que chega ali fora
dos prompts.

A distinção contra prompt engineering vale um slide inteiro. Prompt engineering é redigir a
instrução certa. Context engineering é entregar a informação certa. Conforme os agentes
ficaram capazes, o gargalo mudou de "o agente não entende o que eu quero" para "o agente não
tem o contexto necessário para fazer bem". **[B]**

#### Os quatro pilares

| Pilar | O que é |
|---|---|
| Instruções | Prompt de sistema e enquadramento de comportamento |
| Recuperação | RAG e busca ancorada |
| Memória | Estado curto de conversa e estado longo persistente |
| Ferramentas | A superfície de function calling, cada vez mais padronizada via MCP |

### Agent Skills

Lançado pela Anthropic como padrão aberto em outubro de 2025. Virou padrão aberto em
`agentskills.io` em dezembro de 2025 e foi adotado por Cursor, GitHub Copilot, Open AI Codex,
Gemini CLI e dezenas de outros. Em 29/jan/2026 saiu o guia oficial de 32 páginas. **[B]**

#### Formato

Um skill é uma pasta com um arquivo `SKILL.md` que traz frontmatter YAML e instruções em
markdown. Ele ensina o modelo a lidar com uma tarefa específica de forma consistente e
repetível.

#### Progressive disclosure em três níveis

| Nível | O que carrega | Custo |
|---|---|---|
| 1. Startup | Só `name` e `description` do frontmatter de cada skill instalado | 50 a 100 tokens por skill |
| 2. Ativação | O corpo completo do `SKILL.md` quando o modelo julga relevante | 275 a 8.000 tokens |
| 3. Profundidade | Arquivos auxiliares na pasta, referência, padrões de API, templates | Sob demanda |

Este é o padrão de arquitetura mais importante do ano para quem constrói agentes. Ele resolve
o dilema entre dar muita instrução e estourar a janela de contexto. Cem skills instalados
custam de 5 a 10 mil tokens permanentes e só o relevante paga o preço cheio.

#### O ponto de negócio

Como skills são markdown em inglês corrente, especialista de domínio e líder de time
configuram o comportamento do agente diretamente, sem passar por engenharia.

Para uma empresa de pesquisa de mercado isso é a peça que faltava. O metodologista escreve o
skill de análise de verbatim. O especialista em amostragem escreve o skill de validação de
quota. Nenhum deles precisa abrir código.

### O retorno mensurado

Times que mantêm bons arquivos de contexto para seus agentes cometem 40% menos erros e
completam tarefas 55% mais rápido que quem não mantém. *Anthropic, Agentic Coding Trends
Report 2026.* **[B]**

Cuidado ao citar. Este número circula em várias reproduções secundárias com fraseado levemente
diferente. Antes de colocar em peça publicada, vale abrir o relatório original e confirmar a
metodologia da amostra.

### Como isso vira entregável

A combinação harness mais skills descreve um produto vendável com nome próprio.

1. **Diagnóstico.** Mapear onde o time perde contexto hoje.
2. **Skills de domínio.** Codificar o método da casa em `SKILL.md`, escrito pelo especialista.
3. **Harness.** Planner, generator e evaluator sobre o fluxo de trabalho real.
4. **Medição.** Critérios verificáveis e avaliação separada da geração.
5. **Simplificação recorrente.** Revisar trimestralmente o que o modelo novo tornou
   desnecessário.

Os passos 1, 3 e 5 saem direto da documentação de engenharia da Anthropic. O passo 4 sai da
literatura de evals. Nada aqui é opinião, tudo tem fonte.

### Fontes

- [Anthropic Engineering](https://www.anthropic.com/engineering)
- [Agent Skills, padrão aberto](https://agentskills.io)
- [Sourcegraph, guia prático de context engineering 2026](https://sourcegraph.com/blog/context-engineering)

---

## Embeddings, recuperação e RAG

Coletado em 2026-09-02.

---

### MTEB, o estado do leaderboard

Aviso metodológico que precede qualquer citação. **MTEB v2, de 2026, não é comparável com
MTEB v1.** Os rankings também variam entre os boards English v2 e multilingual MMTEB. Citar
"primeiro lugar no MTEB" sem dizer qual board e qual versão é erro. **[B]**

O leaderboard oficial é um Space do Hugging Face que carrega por JavaScript e não pode ser
lido por fetch simples. A consulta precisa ser feita no navegador. Os números abaixo vieram de
busca e estão marcados como pista, não como fato publicável. **[C]**

| Modelo | Nota | Observação |
|---|---|---|
| tencent/KaLM-Embedding-Gemma3-12B | topo entre abertos | 11,76 bi de parâmetros, 3840 dimensões |
| Qwen3-Embedding 8B | cerca de 75% de média MTEB | aberto |
| NVIDIA NV-Embed-v2 | 72,31 no MTEB English | 4096 dimensões, contexto de 32K |
| Gemini Embedding | SOTA no MTEB multilingual em mar/2025 | hospedado |
| BAAI BGE-M3 | o mais baixado do Hugging Face | denso, esparso e multivetor num só modelo, 100+ idiomas |

O BGE-M3 merece destaque de arquitetura, não de ranking. Ele entrega recuperação densa,
esparsa e multivetor no mesmo modelo, o que reduz a complexidade da stack.

### A arquitetura padrão de 2026

O default deixou de ser embedding denso puro. O padrão atual é: **recuperação híbrida com BM25
mais denso, fusão por RRF, e reranker cross-encoder no fim.** **[B]**

| Camada | Função | Ganho reportado |
|---|---|---|
| BM25 | Casamento léxico exato, nomes, códigos, siglas | Cobre o ponto cego do denso |
| Denso | Similaridade semântica | Cobre paráfrase e sinônimo |
| RRF | Fusão dos dois rankings | Não exige calibrar escalas |
| Cross-encoder | Reordenação com interação bidirecional | 5 a 15 pontos de MRR em conjuntos difíceis |

### Context rot, o achado que muda projeto

Modelos com janela de 1 milhão de tokens ou mais ainda mostram degradação de 20% a 50% quando
o fato crítico está no meio da sequência. Conforme o contexto cresce, informação irrelevante
dilui o sinal mesmo com recuperação perfeita. **[B]**

A consequência prática desmonta um mito comercial inteiro. Janela gigante não elimina RAG. Ela
muda o problema de "achar o documento" para "posicionar o trecho certo na posição de alta
atenção". É exatamente isso que o reranking faz. Ele move os melhores trechos para onde o
modelo presta atenção.

Frase pronta para uso. Contexto de um milhão de tokens não é memória, é espaço. Quem enche o
espaço sem curadoria perde de 20% a 50% de desempenho no que estava no meio.

### RAG agêntico

A virada é de pipeline de recuperar e gerar em um passo para agente de recuperação em vários
passos. **[B]**

No RAG agêntico a recuperação vira uma ferramenta que o modelo pode chamar várias vezes dentro
do mesmo turno. O agente inspeciona a pergunta, decide se precisa de mais evidência, emite uma
nova busca com a consulta reescrita, e só gera a resposta final quando tem contexto suficiente.

O que isso muda no projeto:
- O custo por resposta deixa de ser fixo e passa a ser variável.
- A latência sobe e precisa de orçamento explícito.
- A avaliação precisa medir o caminho, não só a resposta.
- Reescrita de consulta vira componente de primeira classe.

### Checklist de recuperação para proposta técnica

1. Híbrido BM25 mais denso, com RRF. Denso puro ficou para trás.
2. Reranker cross-encoder obrigatório em conjunto difícil.
3. Medir posição do trecho relevante, não só se ele foi recuperado.
4. Definir orçamento de latência e de chamadas antes de adotar RAG agêntico.
5. Escolher o embedding pelo board certo. Multilingual para base em português, não English v2.
6. Reavaliar o embedding a cada seis meses. O campo se move rápido e a migração custa
   reindexação completa.

### Fontes

- [MTEB Leaderboard, Hugging Face](https://huggingface.co/spaces/mteb/leaderboard)
- [Redis, modelos de reranking para RAG em 2026](https://redis.io/blog/top-reranking-models-rag-accuracy/)
- [arXiv, recuperação para busca agêntica via interação direta com o corpus](https://arxiv.org/pdf/2605.05242)

---

## Metodologias de ponta

Coletado em 2026-09-02. O que mudou de verdade em como se treina, avalia e opera modelo.

---

### RLVR, aprendizado por reforço com recompensa verificável

O que é. Um paradigma de pós-treino que substitui o modelo de recompensa por uma função de
verificação. A completação sai da política, é verificada por uma função determinística, e se a
resposta está verificadamente correta o modelo recebe recompensa. **[B]**

Origem. O termo foi cunhado no Tülu 3, do Allen Institute, no outono de 2024.

Por que importa. É a técnica por trás do salto dos modelos de raciocínio. A aceleração medida
pelo Epoch Capabilities Index, de 8 para 15 pontos por ano, coincide com a chegada dos modelos
de raciocínio e com o peso crescente do RL nos laboratórios de fronteira.

Escala em 2026. Métodos de RL viraram fatia crescente do compute de treino de fronteira. Runs
individuais de ablação já consomem de 10 mil a 100 mil horas de GPU.

Extensão. *Rubrics as Rewards* leva a ideia para domínios não verificáveis usando rubrica como
sinal de recompensa. É o caminho para aplicar a técnica onde não existe resposta certa
computável, que é justamente o caso de análise qualitativa e de insight.

### Evals, o que virou consenso operacional

Este é o bloco mais transferível para consultoria, porque descreve infraestrutura que a maioria
das empresas não tem. Lembrar do achado do MIT. A causa raiz do fracasso dos pilotos não é
tecnologia, é que ninguém construiu a medição que prova que o piloto funciona. **[B]**

#### Os três modos de LLM as judge

| Modo | Quando usar |
|---|---|
| Comparação pareada | Escolher qual de duas saídas é melhor. O mais confiável |
| Nota com referência | Existe resposta correta conhecida para comparar |
| Nota sem referência | Só rubrica, sem âncora. O mais frágil dos três |

#### Calibração

- Amostrar de 200 a 500 casos representativos com anotação de especialista.
- Iterar o texto do prompt até a correlação passar de 0,85.
- Reteste trimestral, porque modelo e dado mudam.
- Alternativa mais enxuta. De 100 a 300 traces de produção, de 2 a 3 anotadores humanos, com a
  mesma rubrica que o juiz vai ver.

#### Produção

- Amostragem de 1% a 10% dos traces em produção, mais 100% em CI.
- Humano cuida do que for sinalizado como falha.
- Modelo de juiz menor e rápido para fluxo bloqueante. Modelo grande só em análise offline.
- Cachear prompt e resultado de avaliação para entrada idêntica.

#### Regras de ouro

1. Usar família de modelo diferente da do gerador, para evitar viés de autopreferência. É a
   mesma lógica do evaluator separado no harness da Anthropic.
2. Checagem determinística com código, por exemplo validade de esquema e casamento exato.
   Juiz de LLM só para checagem semântica, como correção, fidelidade e segurança.
3. Consistência de harness. Mesmo modelo de juiz, mesma rubrica, mesma temperatura entre
   rodadas. Harness que muda entre execuções produz notas incomparáveis.

### O fio condutor das três frentes

Harness, skills e evals resolvem o mesmo problema por ângulos diferentes.

| Frente | Problema que resolve |
|---|---|
| Harness | O agente não sustenta tarefa longa e se autoelogia |
| Skills | O conhecimento de domínio não cabe no contexto |
| Evals | Ninguém sabe provar que funcionou |

E os três convergem na mesma regra estrutural. **Separar quem faz de quem julga.** No harness
é o evaluator apartado do generator. Nos evals é a família de modelo diferente da do gerador.
Nos skills é a descrição que decide a ativação, separada do corpo que executa.

Essa convergência é um insight legítimo de arquitetura e dá uma boa tese de conteúdo.

### Fontes

- [Tülu 3, pós-treino aberto](https://arxiv.org/pdf/2411.15124)
- [Rubrics as Rewards, RL além de domínios verificáveis](https://openreview.net/forum?id=c1bTcrDmt4)
- [Awesome RLVR, coletânea](https://github.com/opendilab/awesome-RLVR)
- [Evidently AI, guia de LLM as judge](https://www.evidentlyai.com/llm-guide/llm-as-a-judge)
- [Arize, juízes que aguentam produção](https://arize.com/blog/how-to-build-llm-as-a-judge-evaluators-that-hold-up-in-production/)

---

## Mercado, adoção e ROI

Coletado em 2026-09-02. Bloco de números para abertura de proposta e conteúdo executivo.

---

### Stanford HAI, AI Index Report 2026

Publicado em março de 2026. Fonte primária lida direto. É a fonte mais segura da varredura
inteira para número de mercado. **[A]**

#### Adoção
- 88% das organizações usam IA em ao menos uma função de negócio.
- 70% usam IA generativa em ao menos uma função.
- 53% de adoção populacional de IA generativa em três anos, mais rápido que o computador
  pessoal e que a internet.
- 4 em cada 5 universitários usam IA generativa.
- Mais de 80% dos estudantes de ensino médio e superior nos EUA usam IA em trabalho escolar.
- A implantação de agentes segue em um dígito em quase toda função de negócio.

#### Capacidade
- No SWE-bench Verified, o desempenho subiu de 60% para perto de 100% da baseline humana em um
  ano.
- Agentes passaram de 12% para cerca de 66% de sucesso em tarefas reais de computador.
- Vários modelos já igualam ou superam a baseline humana em questões científicas de nível de
  doutorado.
- A indústria produziu mais de 90% dos modelos de fronteira notáveis de 2025.

#### Investimento
- Investimento privado dos EUA em IA. US$ 285,9 bilhões em 2025.
- Mais de 23 vezes o investimento da China, que ficou em US$ 12,4 bilhões.
- 1.953 novas empresas de IA financiadas nos EUA em 2025.

#### Valor para o consumidor
- US$ 172 bilhões por ano em valor estimado das ferramentas de IA generativa para o consumidor
  americano no início de 2026.
- O valor mediano por usuário triplicou entre 2025 e 2026.

Nota de checagem. Reproduções secundárias do mesmo relatório citam investimento corporativo
global de US$ 581,7 bilhões, alta de 130% no ano, e US$ 170,9 bilhões só em IA generativa. Esses
três números não apareceram na leitura direta da página do relatório e precisam ser confirmados
no PDF completo antes de uso. **[C]**

### Menlo Ventures, gasto empresarial com LLM

- O gasto empresarial com APIs de LLM foi de US$ 3,5 bilhões no fim de 2024 para US$ 8,4
  bilhões, mais que o dobro em seis meses. **[B]**
- Share de API empresarial. Anthropic com 40%, contra 12% em 2023. Open AI com 27%, contra 50%
  em 2023. Google subindo.
- No mercado específico de código, Anthropic com cerca de 54% e Open AI com cerca de 21% em
  meados de 2026. **[B]**

Como usar. Este é o dado que mostra que a preferência empresarial não segue o hype de consumo.
Serve bem em conversa com comprador técnico.

### A taxa de fracasso

- 95% dos pilotos de IA generativa não entregam ROI mensurável. Estudo do MIT com 52
  entrevistas com executivos, pesquisa com 153 líderes e análise de 300 implantações públicas.
  Apesar de US$ 30 a 40 bilhões investidos globalmente. **[B]**
- Só 31% das organizações têm agente em produção. *S&P Global Market Intelligence.* **[B]**
- 88% dos pilotos de agente nunca chegam a produção. **[C]**

#### O diagnóstico, que é o produto

As fontes convergem em três causas, e nenhuma delas é o modelo.

1. **Integração.** Agentes que dão certo estão conectados a dado institucional real, não são
   chatbot com prompt de sistema.
2. **Medição.** Ninguém construiu a infraestrutura que prova que o piloto funcionou.
3. **Prioridade desalinhada.** O piloto foi escolhido por visibilidade, não por retorno.

Cada uma dessas três é uma linha de serviço vendável. E as três se sustentam em fonte citável.

### Mercado de coleta de dados, contexto do produto

- Mercado de web scraping com IA. US$ 10,2 bilhões em 2026, projeção de US$ 23,7 bilhões em
  2030, CAGR de 23,5%. **[C]**
- Requisições automatizadas superaram as humanas pela primeira vez. Bots geram 57,5% do
  tráfego HTML. **[C]**
- Scrapers respondem por 10,2% de todo o tráfego global mesmo após mitigação de bot. Crawlers
  de IA são cerca de um quinto do tráfego de bot verificado. **[C]**
- Por setor. Moda 53%, hospitalidade 49%, saúde 34%. **[C]**

Todos os números deste bloco vieram de fornecedores do próprio setor de scraping, que têm
interesse comercial no tamanho do número. Tratar como indicativo de tendência, não como dado
auditado. A tendência em si, de que coleta automatizada virou infraestrutura padrão, é
consistente entre fontes independentes.

### Fontes

- [Stanford HAI, AI Index Report 2026](https://hai.stanford.edu/ai-index/2026-ai-index-report)
- [Menlo Ventures, State of Generative AI](https://menlovc.com)
- [MIT, cobertura do estudo sobre ROI de pilotos](https://www.healthcareitnews.com/news/mit-95-enterprise-ai-pilots-fail-deliver-measurable-roi)

---

## IA em pesquisa de mercado e insights

Coletado em 2026-09-02. O bloco mais importante para o posicionamento da empresa, porque é onde
a competência técnica encontra o setor de destino.

---

### GRIT Insights Practice Report 2026

Greenbook, 16ª edição, publicado em junho de 2026, com coleta no primeiro trimestre de 2026.
É o maior estudo do setor com compradores, fornecedores e tendências. **[B]**

#### Os achados centrais

**IA generativa saiu do experimento e virou prática.** 67% dos fornecedores de pesquisa já
embutem IA generativa diretamente no entregável ao cliente.

**Dado sintético virou tema de topo.** Emotion e affect analytics, video analytics com IA e
dado sintético apareceram como métodos de ruptura em 2026. O sintético saltou de tema de nicho
para os três assuntos mais comentados do setor em uma única onda.

**E aí vem a tensão.** 87% dos praticantes que usaram dado sintético se disseram satisfeitos.
Ao mesmo tempo, a preocupação com qualidade de dado subiu 40% no ano, com respondente sintético
apontado como causa principal.

Essa contradição aparente é o material mais rico da varredura para conteúdo de autoridade.
Quem usa gosta. O setor como um todo desconfia. As duas coisas são verdade ao mesmo tempo e
explicar por quê posiciona a empresa como quem entende o problema de verdade.

**Detecção de fraude.** Uso regular entre 70% e 88% conforme o segmento.

**Insights ops.** 8 em cada 10 profissionais dizem que a função tem papel significativo.

**Nova segmentação.** Pela primeira vez o GRIT separa os benchmarks por porte de empresa e por
perfil, liderado por tecnologia contra liderado por serviço. Isso permite comparar adoção de
IA, portfólio de métodos, orçamento, equipe e investimento em tecnologia entre segmentos.

#### A frase do relatório que vale um post inteiro

O setor está se dividindo em dois modelos. De um lado, amplitude, julgamento humano e execução
tradicional de pesquisa. Do outro, profundidade analítica, integração operacional e velocidade
aumentada por máquina.

E a advertência que acompanha. Os mais em risco não são os adotantes lentos de IA. São os
executores eficientes sem um ponto claro de controle.

Essa é a melhor tese de conteúdo disponível para o público de insights em 2026. Ela contraria a
narrativa preguiçosa de "adote IA ou morra" e abre espaço para falar de governança, que é
exatamente onde uma casa de automação séria entrega.

### Tamanho do setor

Dados ESOMAR, Global Market Research Report. **[B]**

- A indústria de insights cresceu 8% em 2023, de quase US$ 130 bilhões para US$ 142 bilhões.
- Publicações mais recentes da Research World falam em um setor de US$ 153 bilhões. Confirmar a
  data base antes de citar. **[C]**
- Composição. Data analytics passou a ser o maior segmento com 39%, à frente da pesquisa de
  mercado estabelecida com 36%. Reporting fica com 24%.
- Data analytics é o segmento que mais cresce em termos absolutos, com alta de 16,9%.
- A base do relatório de 2024 cobre mais de 110 países e regiões, o equivalente a 80% da
  indústria global.

O dado de composição é forte. **Analytics ultrapassou pesquisa de mercado dentro da própria
indústria de insights.** Para quem vende automação e IA para esse público, essa é a
legitimação estrutural do discurso.

### O ecossistema de ferramentas

Duas categorias que o mercado confunde e que precisam ser separadas em qualquer material. **[B]**

#### Entrevista qualitativa moderada por IA, com humano real
Listen Labs, Outset, Strella, Glaut, Conveo, Voicepanel, Wondering.

O moderador é IA. O respondente é gente. Listen Labs e Voicepanel também recrutam, o que
elimina a etapa mais lenta da maioria dos estudos. Conveo e Outset aparecem como as escolhas
mais gerais para escala. Strella é citada por profundidade que soa moderada.

#### Respondente sintético, sem humano
Personia, Synthetic Users, BluePill, Aaru, Evidenza, Qualtrics Edge.

A posição predominante nas próprias fontes do setor é clara. Para profundidade qualitativa
genuína, entrevista moderada por IA com humano real. Sintético serve para pré-morte de
hipótese e não substitui a voz real do cliente.

Existe ainda um dado circulando de que 97% dos pesquisadores usam IA mas só 8% confiam em
participante gerado por IA. A fonte é secundária e precisa de confirmação antes de qualquer
uso público. **[C]**

#### Um achado de risco que vale conhecer

Há pesquisa apontando que personas sintéticas às quais se atribuem duas identidades acabam
performando apenas uma delas, o que colapsa a interseccionalidade. Em português claro, uma
persona sintética definida como "mulher negra de 50 anos do interior" tende a responder como
se fosse só um desses eixos. **[C]**

Se confirmado no primário, é um argumento técnico forte e específico, do tipo que diferencia
quem estudou de quem repetiu manchete.

### Como a varredura técnica vira argumento comercial

Cada achado técnico dos outros arquivos tem uma tradução direta para o setor de insights.

| Achado técnico | Tradução para pesquisa de mercado |
|---|---|
| Autoavaliação de agente não funciona, precisa de evaluator apartado | Análise gerada por IA precisa de camada de validação separada, não do mesmo modelo que gerou |
| Context rot, degradação de 20% a 50% no meio da janela | Jogar 200 transcrições numa janela de 1 milhão de tokens não produz análise, produz diluição |
| Progressive disclosure em skills | O metodologista codifica o método da casa sem depender de engenharia |
| Híbrido BM25 mais denso, com reranker | Busca em base de estudos anteriores precisa de casamento exato de marca e categoria, não só semântico |
| 95% dos pilotos sem ROI por falta de medição | O entregável de IA precisa vir com o instrumento que prova que funcionou |
| Skills e MCP viraram padrão aberto | Integração deixou de ser diferencial. O método é que é |

### Fontes

- [GRIT Insights Practice Report 2026, Greenbook](https://www.greenbook.org/grit/insights-practice-edition)
- [ESOMAR, biblioteca de publicações](https://shop.esomar.org/knowledge-center/library)
- [Research World, o setor de insights](https://researchworld.com/articles/inside-the-153bn-insights-industry)
- [Listen Labs, comparativo de plataformas](https://listenlabs.ai/blog/top-ai-qualitative-research-platforms)
- [Outset, ferramentas de pesquisa com IA em 2026](https://outset.ai/almanac/14-ai-market-research-tools-worth-using-in-2026)

---

## Fontes para acompanhar

Coletado em 2026-09-02. Partiu da lista original de cinco categorias e foi expandido com o que
a varredura mostrou ser realmente usado em 2026.

---

### 1. Livros

#### Os quatro da lista original, checados

| Livro | Autor | Situação |
|---|---|---|
| AI Engineering, Building Applications with Foundation Models | Chip Huyen, O'Reilly 2025 | Foi o livro mais lido da plataforma O'Reilly em 2025. Continua sendo a referência número um para engenharia de IA |
| Designing Machine Learning Systems | Chip Huyen | Complementar ao anterior. Cobre drift de dados, retreino e avaliação |
| Machine Learning System Design Interview | Ali Aminian e Alex Xu | Padrões de sistema em formato de entrevista |
| Generative AI System Design Interview | Ali Aminian e Hao Sheng | Mesmo formato, focado em generativo |

#### Acréscimos que a varredura recomendou

- **Hands-On Large Language Models**, Jay Alammar e Maarten Grootendorst. O mais visual para
  entender o que acontece por dentro.
- **The LLM Engineering Handbook**, Paul Iusztin e Maxime Labonne.
- **Co-Intelligence**, Ethan Mollick. O único da lista que serve para conversa com cliente e
  não só com engenheiro. Útil para quem escreve copy.

### 2. Blogs de pesquisa e engenharia

#### Os da lista original
- [Anthropic Engineering](https://www.anthropic.com/engineering). Publicou em 2026 o material
  mais aplicável do ano sobre harness e agentes de longa duração. Prioridade máxima.
- [OpenAI Research](https://openai.com/research)
- [Google DeepMind Blog](https://deepmind.google/discover/blog/)
- [Allen Institute for AI](https://allenai.org/blog). Origem do Tülu 3 e do termo RLVR.

#### Acréscimos com alto retorno
- [Artificial Analysis](https://artificialanalysis.ai). Benchmark independente com metodologia
  aberta. A fonte mais citável para comparação de modelos.
- [Epoch AI](https://epoch.ai). Rigor quantitativo sobre ritmo de progresso e economia de
  compute. Origem do ECI.
- [Greenbook e Research World](https://www.greenbook.org). Obrigatórios para o setor de
  insights.
- [Sebastian Raschka, Ahead of AI](https://magazine.sebastianraschka.com). Faz a curadoria
  trimestral de papers de LLM, o que economiza semanas.

#### Posts individuais de 2026 que valem leitura integral
- Harness design for long-running application development, Anthropic, 24/mar/2026.
- Effective harnesses for long-running agents, Anthropic, 26/nov/2025.
- Scaling Managed Agents, decoupling the brain from the hands, Anthropic, 08/abr/2026.
- Building a C compiler with a team of parallel Claudes, Anthropic, 05/fev/2026.
- Quantifying infrastructure noise in agentic coding evals, Anthropic, 05/fev/2026.

### 3. Cursos e canais

#### Cursos verificados como gratuitos em 2026
- **Anthropic Academy**, lançada em março de 2026. Cerca de vinte cursos, todos gratuitos com
  certificado, cobrindo Claude, Claude Code, a API e MCP. O caminho mais curto para quem vai
  operar agentes.
- **Hugging Face Agents Course**, com certificado gratuito. E o LLM Course da mesma casa.
- **Stanford**, com aulas abertas. CS221 de IA, CS229 de machine learning, CS230 de deep
  learning, CS234 de reforço, CS224N de NLP e **CS336, LLM do zero**, que é o mais atual e não
  estava na lista original.
- **Andrej Karpathy, Neural Networks Zero to Hero**. Oito vídeos, cerca de doze horas, do
  backprop até um GPT funcionando.
- **MIT 6.S191**, deep learning em nível universitário.
- **fast.ai**, para quem prefere começar codando.
- **Elements of AI**, para não técnicos. Útil para treinar time comercial.

Aviso prático. Os vídeos da DeepLearning.AI seguem gratuitos, incluindo o curso de Agentic AI
do Andrew Ng. Laboratórios, quizzes e certificados passaram a exigir assinatura Pro de US$ 25
por mês na cobrança anual. **[B]**

#### Canais
- **Two Minute Papers**, para varredura visual rápida.
- **ByteByteAI e ByteByteGo**, para padrões de sistema.
- **Yannic Kilcher**, para leitura crítica de paper.

### 4. Newsletters

| Newsletter | Autor | Cadência | Para que serve |
|---|---|---|---|
| The Batch | Andrew Ng, DeepLearning.AI | Semanal | A única com credibilidade de ML no nível editorial. Diz o que a semana significa, não só o que aconteceu |
| Ahead of AI | Sebastian Raschka | Irregular | As explicações técnicas mais claras sobre arquitetura e treino |
| Import AI | Jack Clark | Semanal, gratuita | Profundidade de fronteira com viés de política pública |
| ByteByteGo | Alex Xu | Semanal | Padrões de sistema, ótimo para material visual |
| TLDR AI | | Diária | Compressão diária, para não perder lançamento |
| The Rundown AI | | Diária | O melhor digest diário de notícia |

Combinação recomendada pelas fontes. Uma diária para não perder lançamento, mais uma semanal
de profundidade. TLDR AI ou Rundown na diária, The Batch ou Import AI na semanal. Mais que isso
vira ruído.

### 5. Papers

#### Os fundamentais, que continuam valendo
- Attention Is All You Need. A arquitetura Transformer.
- Scaling Laws for Neural Language Models. Por que tamanho importa e quanto.
- InstructGPT. O nascimento do RLHF e do assistente moderno.
- BERT. Bidirecionalidade e pré-treino.
- DDPM. Modelos de difusão.

#### Os que faltavam na lista e explicam 2026
- **Tülu 3**, pós-treino aberto. Onde o termo RLVR foi cunhado.
- **Rubrics as Rewards**, RL além de domínios verificáveis. O caminho para aplicar RL em
  julgamento subjetivo.
- **Densing Law of LLMs**, sobre densidade de capacidade por parâmetro ao longo do tempo.
- **Memory in the Age of AI Agents**, memória de agente.
- **Position, Coding Benchmarks Are Misaligned with Agentic Software Engineering**. A crítica
  de dentro do campo aos próprios benchmarks.
- **Agentic Harness Engineering**, evolução automática de harness guiada por observabilidade.

#### Como acompanhar sem afogar
1. A curadoria trimestral do Raschka em `magazine.sebastianraschka.com` resolve 80% do
   trabalho.
2. [Hugging Face Papers](https://huggingface.co/papers) traz o que a comunidade votou.
3. Coletâneas no GitHub. `VoltAgent/awesome-ai-agent-papers` e `opendilab/awesome-RLVR`.
4. `arxiv.org/list/cs.AI/new` só para quem tem disciplina de filtrar.

### 6. Leaderboards, a categoria que faltava na lista

Nenhum dos cinco tipos originais cobre o mais útil para argumento comercial. Ranking com
metodologia aberta.

| Leaderboard | O que mede | Nota |
|---|---|---|
| [Artificial Analysis](https://artificialanalysis.ai/leaderboards/models) | Inteligência, custo, velocidade | O mais completo para decisão de arquitetura |
| [Arena](https://arena.ai/leaderboard) | Elo por preferência humana, texto e agentes | Cuidar do intervalo de confiança |
| [Epoch Capabilities Index](https://epoch.ai/eci) | Capacidade agregada ao longo do tempo | O único que resiste à saturação de benchmark |
| [MTEB](https://huggingface.co/spaces/mteb/leaderboard) | Embeddings | Conferir versão e board antes de citar |
| [SWE-bench](https://www.swebench.com) | Resolução de issue real de software | Padrão do setor, já saturando |

### 7. Filtro de qualidade de fonte

A varredura de setembro atravessou dezenas de sites que ranqueiam bem no Google e publicam
número sem metodologia. O critério que separou o joio.

**Aceitar.** Publica metodologia, data de coleta e tamanho de amostra. Tem nome e instituição
por trás. Permite reproduzir o número.

**Descartar.** Título com ano no formato "Melhores X de 2026", sem autor identificado, sem
metodologia, com link de afiliado. Número redondo demais e sem fonte primária.

**Cuidado especial.** Fornecedor que publica o tamanho do próprio mercado. O incentivo é
evidente. Serve de indicativo de tendência, nunca de dado auditado.

---

## Achados da varredura

Primeira execução do `raspar_news_ia.py` em 2026-09-02, janela de 21 dias. 235 itens relevantes
de 2.875 coletados. Este arquivo guarda o que a varredura automática trouxe de novo e que ainda
não estava nos arquivos temáticos.

---

### O achado mais valioso para o nosso posicionamento

**Simulation, the new Scaling Law. Joon Sung Park, Simile AI.** Latent Space, 21/ago/2026.

Joon Sung Park é o pesquisador por trás dos generative agents de Stanford, o trabalho que
mostrou agentes simulando comportamento humano em ambiente social. Ele agora está numa empresa
chamada Simile AI e defende simulação como a nova lei de escala.

Por que isso importa para uma casa de pesquisa de mercado. É a fundamentação acadêmica séria
do debate sobre respondente sintético, vinda de quem publicou o paper original em vez de quem
vende a ferramenta. Vale ouvir o episódio inteiro antes de escrever qualquer conteúdo sobre
dado sintético. Provavelmente é a melhor fonte disponível para tomar posição informada no tema
que o GRIT 2026 apontou como o de maior tensão do setor.

Ação sugerida. Ouvir, cruzar com o achado do GRIT sobre a alta de 40% na preocupação com
qualidade, e escrever uma peça de autoridade que nenhum concorrente vai conseguir copiar sem
fazer a mesma lição de casa.

### Correções e atualizações aos arquivos temáticos

**GLM 5.3 existe.** O arquivo `02-abertos-vs-pagos.md` documenta GLM 5.2. A varredura encontrou
duas fontes de agosto tratando de GLM 5.3.
- *GLM-5.3, how Chinese labs keep stride with the frontier*, Interconnects, 14/ago/2026.
- *Death of Params, Z.ai CEO Jie Tang on GLM 5.3 and the new post-training*, Latent Space,
  20/ago/2026.

O título do segundo sugere uma tese forte de que contagem de parâmetros perdeu relevância como
métrica. Confirmar antes de citar.

**Claude Fable 5.1 é recente.** *Claude Fable/Mythos 5.1, new SOTA model, 75% cache price cut*,
Latent Space, 02/set/2026. O corte de 75% no preço de cache é dado de custo relevante e reforça
o argumento do arquivo `02`. Confirmar na tabela oficial de preços antes de usar.

### Harness e agentes

- **The Evolution of the Agent Harness.** Latent Space, 22/ago/2026. Panorama externo do tema
  que o arquivo `03` cobre pela ótica da Anthropic. Útil para triangular.
- **How Much Memory Does Your Agent Actually Need?** Hugging Face, 18/ago/2026. Trata do
  problema que o harness da Anthropic resolve com arquivo de progresso.
- **React for Agents, Astro creator brings hooks to his meta-harness, Flue.** Latent Space,
  15/ago/2026.
- **The /wayfinder skill, navigating the fog of war of planning.** Latent Space, 20/ago/2026.
  Exemplo prático de skill de planejamento.
- **Patterns and problems in emerging multiagent systems.** Anthropic Research, 13/ago/2026.
  Leitura obrigatória para quem vai vender orquestração multiagente.

### Avaliação, o tema que mais apareceu

A varredura mostrou avaliação como o assunto mais quente de agosto de 2026. Três laboratórios
diferentes publicaram sobre isso na mesma janela.

- **BenchMIRT, what are LLM benchmarks actually measuring?** Hugging Face, 01/set/2026.
- **Piloting the world's first double-blind AI evaluations.** Google DeepMind, 27/ago/2026.
  Avaliação duplo cego em IA. O paralelo com metodologia de pesquisa clínica é evidente e dá
  uma ponte natural para o público de insights.
- **9 big questions benchmarks can help answer.** Epoch AI, 14/ago/2026.
- **Measuring benchmark optimization in speech recognition.** Hugging Face, 21/ago/2026.
- **Demystifying evals for AI agents.** Anthropic Engineering, 09/jan/2026.

Leitura da tendência. O setor passou de "qual modelo é melhor" para "o que os benchmarks estão
de fato medindo". É exatamente o ceticismo metodológico que uma casa de pesquisa entende
melhor que uma casa de software. Há um posicionamento inteiro aqui.

### Embeddings e recuperação

- **Multi-Vector (Late Interaction) Embedding Models with Sentence Transformers.**
  Hugging Face, 18/ago/2026.
- **Training and Finetuning Multi-Vector Embedding Models with Sentence Transformers.**
  Hugging Face, 26/ago/2026.

Late interaction saiu do paper e entrou na biblioteca mais usada do mercado, com tutorial de
treino e de fine-tuning. Isso muda o custo de adoção da técnica descrita no arquivo `05`.

### Mercado

- **Stripe compra a OpenRouter por US$ 7 bilhões.** Latent Space, 17/ago/2026. Confirmar em
  fonte primária. Se procede, é sinal forte sobre roteamento de modelo como camada de
  infraestrutura com valor econômico próprio.
- **Frontier model cost and open-weights popularity is driving demand for model routing.**
  Latent Space, 18/ago/2026. Conecta direto com a tese do arquivo `02`.
- **Our position on open-weights models.** Anthropic News, 27/jul/2026. A posição oficial de
  quem lidera os rankings sobre modelo aberto. Leitura obrigatória antes de qualquer conteúdo
  sobre o tema.

### Limitação conhecida da coleta

As três fontes de pesquisa de mercado, Greenbook, Research World e Quirks, são raspadas por
HTML porque não publicam RSS. A listagem delas não expõe data no link, então esses itens vêm
sem data e não são filtrados pela janela de tempo. Na prática significa que a seção `insights`
do digest mistura conteúdo novo com arquivo antigo.

Correção possível numa próxima iteração. Abrir cada artigo para extrair a data da página, ao
custo de uma requisição por item. Enquanto isso, tratar a lista de insights como sugestão de
leitura, não como novidade da semana.

### Biblioteca da Anthropic Engineering

A raspagem trouxe o arquivo completo, 44 posts de Anthropic Engineering, News e Research, com
data em 43 deles. Está em `dados/biblioteca-anthropic.csv`.

É a leitura de fundo mais densa que a varredura encontrou. A sequência recomendada para quem
vai construir agentes de verdade:

1. Building effective agents, 19/dez/2024. A base conceitual.
2. Effective context engineering for AI agents, 29/set/2025.
3. Equipping agents for the real world with Agent Skills, 16/out/2025.
4. Effective harnesses for long-running agents, 26/nov/2025.
5. Demystifying evals for AI agents, 09/jan/2026.
6. Harness design for long-running application development, 24/mar/2026.
7. Scaling managed agents, decoupling the brain from the hands, 08/abr/2026.
8. Patterns and problems in emerging multiagent systems, 13/ago/2026.

Os oito na ordem contam a história completa de como o campo saiu de prompt para arquitetura em
vinte meses. Serve de espinha dorsal para uma apresentação de expertise.

---

## Biblioteca de fundamentos

Análise do repositório `MinhNguyenDS/AI-pdf-books` feita em 2026-09-02. 73 arquivos, 706 MB,
174 estrelas, último push em 18/jul/2026.

Este arquivo guarda a curadoria. Não guarda os PDFs.

---

### Aviso de direito autoral

O repositório redistribui livros da O'Reilly, Manning, Springer e MIT Press. A licença MIT
declarada cobre a estrutura do repositório, não o conteúdo dos livros. Na prática é um espelho
de material protegido.

A decisão aqui foi absorver a bibliografia e descartar os arquivos. Para cada título que vale a
pena, este arquivo aponta o caminho legítimo. Vários deles têm cópia oficial gratuita, o que
torna a pirataria desnecessária inclusive por conveniência.

### O diagnóstico em uma frase

É uma boa biblioteca de fundamentos com cobertura zero da camada de 2025 e 2026.

Nada ali trata de context engineering, harness, Agent Skills, MCP, RLVR, avaliação como
infraestrutura de produção ou recuperação híbrida com reranking. São exatamente os temas dos
arquivos `03` a `06` desta pasta. As duas coisas são complementares, não concorrentes. O
repositório cobre a base que não muda. A varredura cobre a camada que muda todo mês.

---

### Camada 1. Vale absorver de verdade

Sete títulos justificam investimento de tempo ou de dinheiro.

| Título | Por que | Onde obter |
|---|---|---|
| **AI Engineering**, Chip Huyen | Já era a recomendação número um do arquivo `09`. O repositório confirma o consenso | [huyenchip.com/books](https://huyenchip.com/books/), O'Reilly |
| **Designing Machine Learning Systems**, Chip Huyen | Complementar ao anterior. Drift, retreino, avaliação | [huyenchip.com/books](https://huyenchip.com/books/), O'Reilly |
| **Build a Large Language Model (From Scratch)**, Raschka | O mesmo autor do Ahead of AI, que já está no nosso catálogo de feeds. Código aberto e gratuito no GitHub | [github.com/rasbt/LLMs-from-scratch](https://github.com/rasbt/LLMs-from-scratch), Manning |
| **Speech and Language Processing**, Jurafsky e Martin | O livro-texto de PNL. A 3ª edição é atualizada continuamente | **Gratuito e oficial**, [web.stanford.edu/~jurafsky/slp3](https://web.stanford.edu/~jurafsky/slp3/) |
| **Storytelling with Data**, Knaflic | O sleeper hit da lista para uma casa de insights. Não é sobre IA, é sobre a entrega. Resolve o problema do arquivo `08` sobre insight que não vira decisão | Editora |
| **Practical Statistics for Data Scientists** | Base quantitativa para quem entrega pesquisa. Amostragem, significância, viés | O'Reilly |
| **Building Applications with AI Agents**, O'Reilly | O único da lista que toca sistemas multiagente. Triangula com o material da Anthropic no arquivo `03` | O'Reilly |

### Camada 2. Gratuitos e legítimos, vale linkar no onboarding

| Título | Link oficial |
|---|---|
| Python Data Science Handbook, VanderPlas | [jakevdp.github.io/PythonDataScienceHandbook](https://jakevdp.github.io/PythonDataScienceHandbook/) |
| Python for Data Analysis, 3ª ed, McKinney | [wesmckinney.com/book](https://wesmckinney.com/book/) |
| Prompt Engineering Guide | [promptingguide.ai](https://www.promptingguide.ai/) |
| The Probability and Statistics Cookbook | Distribuição livre do autor |
| Stanford, cheatsheet de transformers e LLMs | Stanford CS |

Acréscimo que falta no repositório e é gratuito. **Dive into Deep Learning**, em
[d2l.ai](https://d2l.ai/). Substitui com vantagem o *Fundamentals of Deep Learning* da lista,
porque é mantido e traz implementação em PyTorch, JAX e TensorFlow.

### Camada 3. Os papers, todos livres no arXiv

Vinte e seis arquivos na pasta `Paper`, catorze deles são artigos identificados só pelo ID.
Resolvidos abaixo. Todos são gratuitos e legítimos no arXiv, então o repositório não agrega
nada aqui além da curadoria.

Os cinco que sustentam diretamente o que já escrevemos:

| ID | Título | Onde entra |
|---|---|---|
| 2306.05685 | Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena | Fundamenta o arquivo `06` sobre evals e o próprio Arena do arquivo `01` |
| 2305.20050 | Let's Verify Step by Step | Supervisão de processo, o precursor direto do RLVR do arquivo `06` |
| 2408.08435 | Automated Design of Agentic Systems | Desenho automático de sistema agêntico, dialoga com o harness do arquivo `03` |
| 2501.14249 | Humanity's Last Exam | O HLE que citamos no arquivo `02` para mostrar onde o gap aberto contra fechado persiste |
| 2408.08921 | Graph Retrieval-Augmented Generation, A Survey | Complementa o arquivo `05`, que não cobre RAG em grafo |

Os demais, por ordem de utilidade para nós:

| ID | Título |
|---|---|
| 2311.12022 | GPQA, A Graduate-Level Google-Proof Q&A Benchmark |
| 2406.01574 | MMLU-Pro, benchmark mais robusto de compreensão multitarefa |
| 2107.03374 | Evaluating Large Language Models Trained on Code, origem do HumanEval |
| 2401.05566 | Sleeper Agents, LLMs enganosos que sobrevivem ao treino de segurança |
| 2408.12599 | Controllable Text Generation for LLMs, A Survey |
| 2410.03131 | Code Comprehension then Auditing for Unsupervised LLM Evaluation |
| 1910.13461 | BART |
| 2001.08210 | mBART, pré-treino multilíngue |
| 2111.09543 | DeBERTaV3 |

Os quatro últimos são de arquitetura pré-LLM. Valem como história, não como operação.

Fora os artigos, a pasta traz dois materiais de método que valem para o time.
**How to Read a Paper** e **The Craft of Research**. Ler paper com método é habilidade
subestimada num time que precisa citar fonte primária.

### Camada 4. Pular

| Título | Motivo |
|---|---|
| NLTK Cookbook, NLP with Python, Foundations of Statistical NLP | PNL pré-LLM, de 1999 a 2009. História, não prática |
| Hands-On ML with Scikit-Learn and TensorFlow | Edição antiga. E não treinamos modelo do zero |
| Data Mining Concepts and Techniques, 3ª ed | De 2011, acadêmico |
| Exploratory Data Analysis with R | Somos casa Python |
| FastAPI, dois livros | Framework web genérico, não é diferencial nosso |
| Python for DevOps, AWS serverless, GenAI on Kubernetes | Infraestrutura, fora do nosso foco |
| Database Internals | Livro excelente, prioridade errada |
| Os três arquivos em vietnamita | Barreira de idioma |
| Generative AI with LangChain, 2024 | LangChain mudou muito desde 2024. Documentação atual vale mais |
| Designing Large Language Model Applications, 2023 | Anterior à era de agentes. Superado pelo que está nos arquivos `03` e `04` |

### O que a biblioteca não cobre, e nós já cobrimos

Esta é a parte que interessa para posicionamento. Nenhum dos 73 arquivos trata de:

- Context engineering e progressive disclosure. Arquivo `04`.
- Desenho de harness e arquitetura planner, generator, evaluator. Arquivo `03`.
- Agent Skills e MCP como padrão aberto. Arquivos `03` e `04`.
- RLVR e o pós-treino que explica os modelos de raciocínio. Arquivo `06`.
- Avaliação como infraestrutura de produção, com calibração e amostragem. Arquivo `06`.
- Recuperação híbrida, reranking, context rot e late interaction. Arquivo `05`.
- Qualquer coisa sobre pesquisa de mercado e insights. Arquivo `08`.

A conclusão prática. A biblioteca serve de camada de fundamentos para quem entra no time. A
vertical de varredura serve de camada de atualidade para quem escreve e vende. Manter as duas
separadas, com a biblioteca mudando devagar e a varredura mudando toda semana.

### Decisão

1. Não clonar os 706 MB. A bibliografia foi absorvida aqui.
2. Adquirir de forma legítima os sete títulos da camada 1. Assinatura da O'Reilly resolve
   cinco deles de uma vez e sai mais barato que comprar avulso.
3. Linkar os gratuitos da camada 2 no material de integração de quem entra no time.
4. Baixar do arXiv os cinco papers prioritários da camada 3 e anexá-los como leitura de apoio
   dos arquivos `02`, `03`, `05` e `06`.
5. Ignorar as camadas 4.

---

