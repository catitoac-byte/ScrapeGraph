# Achados da varredura

Primeira execução do `raspar_news_ia.py` em 2026-09-02, janela de 21 dias. 235 itens relevantes
de 2.875 coletados. Este arquivo guarda o que a varredura automática trouxe de novo e que ainda
não estava nos arquivos temáticos.

---

## O achado mais valioso para o nosso posicionamento

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

## Correções e atualizações aos arquivos temáticos

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

## Harness e agentes

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

## Avaliação, o tema que mais apareceu

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

## Embeddings e recuperação

- **Multi-Vector (Late Interaction) Embedding Models with Sentence Transformers.**
  Hugging Face, 18/ago/2026.
- **Training and Finetuning Multi-Vector Embedding Models with Sentence Transformers.**
  Hugging Face, 26/ago/2026.

Late interaction saiu do paper e entrou na biblioteca mais usada do mercado, com tutorial de
treino e de fine-tuning. Isso muda o custo de adoção da técnica descrita no arquivo `05`.

## Mercado

- **Stripe compra a OpenRouter por US$ 7 bilhões.** Latent Space, 17/ago/2026. Confirmar em
  fonte primária. Se procede, é sinal forte sobre roteamento de modelo como camada de
  infraestrutura com valor econômico próprio.
- **Frontier model cost and open-weights popularity is driving demand for model routing.**
  Latent Space, 18/ago/2026. Conecta direto com a tese do arquivo `02`.
- **Our position on open-weights models.** Anthropic News, 27/jul/2026. A posição oficial de
  quem lidera os rankings sobre modelo aberto. Leitura obrigatória antes de qualquer conteúdo
  sobre o tema.

## Limitação conhecida da coleta

As três fontes de pesquisa de mercado, Greenbook, Research World e Quirks, são raspadas por
HTML porque não publicam RSS. A listagem delas não expõe data no link, então esses itens vêm
sem data e não são filtrados pela janela de tempo. Na prática significa que a seção `insights`
do digest mistura conteúdo novo com arquivo antigo.

Correção possível numa próxima iteração. Abrir cada artigo para extrair a data da página, ao
custo de uma requisição por item. Enquanto isso, tratar a lista de insights como sugestão de
leitura, não como novidade da semana.

## Biblioteca da Anthropic Engineering

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
