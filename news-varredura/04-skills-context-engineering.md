# Agent Skills e context engineering

Coletado em 2026-09-02.

---

## Context engineering, a definição que funciona

Context engineering é a prática de desenhar deliberadamente o que o modelo vê em cada chamada
de inferência. A formulação da Anthropic. O conjunto de estratégias para curar e manter o
conjunto ótimo de tokens durante a inferência, incluindo toda informação que chega ali fora
dos prompts.

A distinção contra prompt engineering vale um slide inteiro. Prompt engineering é redigir a
instrução certa. Context engineering é entregar a informação certa. Conforme os agentes
ficaram capazes, o gargalo mudou de "o agente não entende o que eu quero" para "o agente não
tem o contexto necessário para fazer bem". **[B]**

### Os quatro pilares

| Pilar | O que é |
|---|---|
| Instruções | Prompt de sistema e enquadramento de comportamento |
| Recuperação | RAG e busca ancorada |
| Memória | Estado curto de conversa e estado longo persistente |
| Ferramentas | A superfície de function calling, cada vez mais padronizada via MCP |

## Agent Skills

Lançado pela Anthropic como padrão aberto em outubro de 2025. Virou padrão aberto em
`agentskills.io` em dezembro de 2025 e foi adotado por Cursor, GitHub Copilot, Open AI Codex,
Gemini CLI e dezenas de outros. Em 29/jan/2026 saiu o guia oficial de 32 páginas. **[B]**

### Formato

Um skill é uma pasta com um arquivo `SKILL.md` que traz frontmatter YAML e instruções em
markdown. Ele ensina o modelo a lidar com uma tarefa específica de forma consistente e
repetível.

### Progressive disclosure em três níveis

| Nível | O que carrega | Custo |
|---|---|---|
| 1. Startup | Só `name` e `description` do frontmatter de cada skill instalado | 50 a 100 tokens por skill |
| 2. Ativação | O corpo completo do `SKILL.md` quando o modelo julga relevante | 275 a 8.000 tokens |
| 3. Profundidade | Arquivos auxiliares na pasta, referência, padrões de API, templates | Sob demanda |

Este é o padrão de arquitetura mais importante do ano para quem constrói agentes. Ele resolve
o dilema entre dar muita instrução e estourar a janela de contexto. Cem skills instalados
custam de 5 a 10 mil tokens permanentes e só o relevante paga o preço cheio.

### O ponto de negócio

Como skills são markdown em inglês corrente, especialista de domínio e líder de time
configuram o comportamento do agente diretamente, sem passar por engenharia.

Para uma empresa de pesquisa de mercado isso é a peça que faltava. O metodologista escreve o
skill de análise de verbatim. O especialista em amostragem escreve o skill de validação de
quota. Nenhum deles precisa abrir código.

## O retorno mensurado

Times que mantêm bons arquivos de contexto para seus agentes cometem 40% menos erros e
completam tarefas 55% mais rápido que quem não mantém. *Anthropic, Agentic Coding Trends
Report 2026.* **[B]**

Cuidado ao citar. Este número circula em várias reproduções secundárias com fraseado levemente
diferente. Antes de colocar em peça publicada, vale abrir o relatório original e confirmar a
metodologia da amostra.

## Como isso vira entregável

A combinação harness mais skills descreve um produto vendável com nome próprio.

1. **Diagnóstico.** Mapear onde o time perde contexto hoje.
2. **Skills de domínio.** Codificar o método da casa em `SKILL.md`, escrito pelo especialista.
3. **Harness.** Planner, generator e evaluator sobre o fluxo de trabalho real.
4. **Medição.** Critérios verificáveis e avaliação separada da geração.
5. **Simplificação recorrente.** Revisar trimestralmente o que o modelo novo tornou
   desnecessário.

Os passos 1, 3 e 5 saem direto da documentação de engenharia da Anthropic. O passo 4 sai da
literatura de evals. Nada aqui é opinião, tudo tem fonte.

## Fontes

- [Anthropic Engineering](https://www.anthropic.com/engineering)
- [Agent Skills, padrão aberto](https://agentskills.io)
- [Sourcegraph, guia prático de context engineering 2026](https://sourcegraph.com/blog/context-engineering)
