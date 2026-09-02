# Harness, orquestração e agentes

Coletado em 2026-09-02. Este é o tema mais denso da varredura e o mais diretamente ligado ao
que a empresa vende.

---

## O que é um harness

Harness é o arcabouço de orquestração que estrutura o comportamento do modelo em tarefas
longas e complexas. Ele define decomposição, gestão de contexto e passagem de bastão entre
sessões. A frase da própria Anthropic é direta. O desenho do harness tem impacto substancial
na eficácia de código agêntico de longa duração.

Fonte primária lida direto. Anthropic Engineering, *Harness design for long-running
application development*, 24/mar/2026. **[A]**

## A arquitetura de três agentes

| Papel | Função | Detalhe que importa |
|---|---|---|
| **Planner** | Expande um prompt curto em especificação detalhada de produto | Escopo ambicioso, sem superespecificar implementação técnica |
| **Generator** | Implementa as features seguindo a spec | Começou em sprints discretos, foi simplificado quando os modelos passaram a sustentar sessões longas |
| **Evaluator** | Testa o resultado de forma interativa via Playwright e dá nota contra critérios concretos | Separado da geração de propósito |

O motivo de separar o avaliador é o achado mais transferível de todos. Agentes tendem a
elogiar o próprio trabalho com confiança, mesmo quando a qualidade é obviamente medíocre.
Autoavaliação não funciona. Julgamento precisa de um agente com contexto e incentivo
diferentes.

## Os números do experimento

| Cenário | Tempo | Custo |
|---|---|---|
| Agente solo, criador de jogos | 20 minutos | US$ 9 |
| Harness completo, criador de jogos | 6 horas | US$ 200 |
| Harness simplificado (Opus 4.6), aplicação DAW | 3h50 | US$ 124,70 |

Vinte vezes mais caro em compute, com qualidade de saída dramaticamente superior. Este par de
números é o melhor argumento disponível contra a ideia de que automação com IA é "plugar uma
API". **[A]**

## As quatro lições de desenho

1. **Separação de responsabilidades.** Desacoplar avaliação de geração produz julgamento
   melhor que autoavaliação.
2. **Passagem de bastão estruturada.** Usar arquivos para comunicação entre agentes preserva
   contexto entre sessões.
3. **Simplificação progressiva.** Remover componentes conforme os modelos melhoram evita
   dívida técnica. O harness de hoje precisa ser menor que o de ontem.
4. **Critérios verificáveis.** Converter julgamento subjetivo em padrão mensurável, por
   exemplo qualidade de design, originalidade, acabamento e funcionalidade, é o que permite
   nota consistente.

## O harness anterior, ainda útil

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

## Model Context Protocol

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

## Agentes em produção, o retrato honesto

- Só 31% das organizações têm um agente rodando em produção. *S&P Global.* **[B]**
- 88% dos pilotos de agente nunca chegam a produção. **[C]**
- A implantação de agentes segue em um dígito em quase toda função de negócio.
  *Stanford AI Index 2026.* **[A]**
- Agentes de IA melhoraram de 12% para cerca de 66% de sucesso em tarefas reais de computador.
  *Stanford AI Index 2026.* **[A]**

A causa apontada nos estudos não é o modelo. É integração ruim e prioridade desalinhada. O
padrão comum entre quem deu certo é um só. Agentes conectados a dado institucional real, não
chatbot com prompt de sistema.

## Tendências de código agêntico

Anthropic, *Agentic Coding Trends Report* 2026. **[B]**

- Desenvolvedores usam IA em cerca de 60% do trabalho.
- Ainda assim conseguem delegar totalmente entre 0% e 20% das tarefas.
- 2026 marca a virada de assistente único para times de agentes coordenados, capazes de rodar
  autonomamente por horas ou dias.
- O engenheiro migra de escrever código para orquestrar os sistemas que escrevem código.

O par 60% contra 0 a 20% é ótimo para copy. Ele desarma tanto o cético quanto o entusiasta na
mesma frase.

## Fontes

- [Anthropic Engineering](https://www.anthropic.com/engineering)
- [Harness design for long-running application development](https://www.anthropic.com/engineering/harness-design-long-running-apps)
- [Effective harnesses for long-running agents](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents)
- [Especificação MCP 2026-07-28](https://blog.modelcontextprotocol.io/posts/2026-07-28/)
- [Arena, leaderboard de agentes](https://arena.ai/leaderboard)
