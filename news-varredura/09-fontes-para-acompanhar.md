# Fontes para acompanhar

Coletado em 2026-09-02. Partiu da lista original de cinco categorias e foi expandido com o que
a varredura mostrou ser realmente usado em 2026.

---

## 1. Livros

### Os quatro da lista original, checados

| Livro | Autor | Situação |
|---|---|---|
| AI Engineering, Building Applications with Foundation Models | Chip Huyen, O'Reilly 2025 | Foi o livro mais lido da plataforma O'Reilly em 2025. Continua sendo a referência número um para engenharia de IA |
| Designing Machine Learning Systems | Chip Huyen | Complementar ao anterior. Cobre drift de dados, retreino e avaliação |
| Machine Learning System Design Interview | Ali Aminian e Alex Xu | Padrões de sistema em formato de entrevista |
| Generative AI System Design Interview | Ali Aminian e Hao Sheng | Mesmo formato, focado em generativo |

### Acréscimos que a varredura recomendou

- **Hands-On Large Language Models**, Jay Alammar e Maarten Grootendorst. O mais visual para
  entender o que acontece por dentro.
- **The LLM Engineering Handbook**, Paul Iusztin e Maxime Labonne.
- **Co-Intelligence**, Ethan Mollick. O único da lista que serve para conversa com cliente e
  não só com engenheiro. Útil para quem escreve copy.

## 2. Blogs de pesquisa e engenharia

### Os da lista original
- [Anthropic Engineering](https://www.anthropic.com/engineering). Publicou em 2026 o material
  mais aplicável do ano sobre harness e agentes de longa duração. Prioridade máxima.
- [OpenAI Research](https://openai.com/research)
- [Google DeepMind Blog](https://deepmind.google/discover/blog/)
- [Allen Institute for AI](https://allenai.org/blog). Origem do Tülu 3 e do termo RLVR.

### Acréscimos com alto retorno
- [Artificial Analysis](https://artificialanalysis.ai). Benchmark independente com metodologia
  aberta. A fonte mais citável para comparação de modelos.
- [Epoch AI](https://epoch.ai). Rigor quantitativo sobre ritmo de progresso e economia de
  compute. Origem do ECI.
- [Greenbook e Research World](https://www.greenbook.org). Obrigatórios para o setor de
  insights.
- [Sebastian Raschka, Ahead of AI](https://magazine.sebastianraschka.com). Faz a curadoria
  trimestral de papers de LLM, o que economiza semanas.

### Posts individuais de 2026 que valem leitura integral
- Harness design for long-running application development, Anthropic, 24/mar/2026.
- Effective harnesses for long-running agents, Anthropic, 26/nov/2025.
- Scaling Managed Agents, decoupling the brain from the hands, Anthropic, 08/abr/2026.
- Building a C compiler with a team of parallel Claudes, Anthropic, 05/fev/2026.
- Quantifying infrastructure noise in agentic coding evals, Anthropic, 05/fev/2026.

## 3. Cursos e canais

### Cursos verificados como gratuitos em 2026
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

### Canais
- **Two Minute Papers**, para varredura visual rápida.
- **ByteByteAI e ByteByteGo**, para padrões de sistema.
- **Yannic Kilcher**, para leitura crítica de paper.

## 4. Newsletters

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

## 5. Papers

### Os fundamentais, que continuam valendo
- Attention Is All You Need. A arquitetura Transformer.
- Scaling Laws for Neural Language Models. Por que tamanho importa e quanto.
- InstructGPT. O nascimento do RLHF e do assistente moderno.
- BERT. Bidirecionalidade e pré-treino.
- DDPM. Modelos de difusão.

### Os que faltavam na lista e explicam 2026
- **Tülu 3**, pós-treino aberto. Onde o termo RLVR foi cunhado.
- **Rubrics as Rewards**, RL além de domínios verificáveis. O caminho para aplicar RL em
  julgamento subjetivo.
- **Densing Law of LLMs**, sobre densidade de capacidade por parâmetro ao longo do tempo.
- **Memory in the Age of AI Agents**, memória de agente.
- **Position, Coding Benchmarks Are Misaligned with Agentic Software Engineering**. A crítica
  de dentro do campo aos próprios benchmarks.
- **Agentic Harness Engineering**, evolução automática de harness guiada por observabilidade.

### Como acompanhar sem afogar
1. A curadoria trimestral do Raschka em `magazine.sebastianraschka.com` resolve 80% do
   trabalho.
2. [Hugging Face Papers](https://huggingface.co/papers) traz o que a comunidade votou.
3. Coletâneas no GitHub. `VoltAgent/awesome-ai-agent-papers` e `opendilab/awesome-RLVR`.
4. `arxiv.org/list/cs.AI/new` só para quem tem disciplina de filtrar.

## 6. Leaderboards, a categoria que faltava na lista

Nenhum dos cinco tipos originais cobre o mais útil para argumento comercial. Ranking com
metodologia aberta.

| Leaderboard | O que mede | Nota |
|---|---|---|
| [Artificial Analysis](https://artificialanalysis.ai/leaderboards/models) | Inteligência, custo, velocidade | O mais completo para decisão de arquitetura |
| [Arena](https://arena.ai/leaderboard) | Elo por preferência humana, texto e agentes | Cuidar do intervalo de confiança |
| [Epoch Capabilities Index](https://epoch.ai/eci) | Capacidade agregada ao longo do tempo | O único que resiste à saturação de benchmark |
| [MTEB](https://huggingface.co/spaces/mteb/leaderboard) | Embeddings | Conferir versão e board antes de citar |
| [SWE-bench](https://www.swebench.com) | Resolução de issue real de software | Padrão do setor, já saturando |

## 7. Filtro de qualidade de fonte

A varredura de setembro atravessou dezenas de sites que ranqueiam bem no Google e publicam
número sem metodologia. O critério que separou o joio.

**Aceitar.** Publica metodologia, data de coleta e tamanho de amostra. Tem nome e instituição
por trás. Permite reproduzir o número.

**Descartar.** Título com ano no formato "Melhores X de 2026", sem autor identificado, sem
metodologia, com link de afiliado. Número redondo demais e sem fonte primária.

**Cuidado especial.** Fornecedor que publica o tamanho do próprio mercado. O incentivo é
evidente. Serve de indicativo de tendência, nunca de dado auditado.
