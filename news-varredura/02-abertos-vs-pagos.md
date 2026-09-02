# Modelos abertos contra proprietários

Coletado em 2026-09-02.

---

## A distância atual

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

## Os lançamentos abertos de 2026

Entre abril e julho de 2026 saíram GLM 5.2, Kimi K3, Kimi K2.7 Code, MiniMax M3 e
DeepSeek V4 Pro. **[B]**

### Kimi K3, Moonshot AI
Aberto em 27/jul/2026. Maior modelo aberto já lançado. 2,8 trilhões de parâmetros totais,
104 bilhões ativos, 896 experts, contexto de 1 milhão de tokens, visão e vídeo nativos.
Licença própria com limiar de receita comercial, ou seja, não é permissiva de verdade acima
de certo faturamento. Terminal-Bench 2.1 em 88,3.

### GLM 5.2, Zhipu AI
Licença MIT, contexto de 1 milhão, GPQA Diamond em 91,2%. A licença MIT é o diferencial
comercial contra o Kimi.

### DeepSeek V4
V4 Pro com 1,6 trilhão de parâmetros totais e contexto perto de 1,04 milhão. V4 Flash com
284 bilhões, mesma classe de contexto, mais throughput e menos custo. Licença MIT.

### Qwen, Alibaba
Qwen 3.6 com pesos no Hugging Face. Qwen 3.7 Max saiu em 19/mai/2026 só por API, sem pesos
publicados. Vale registrar o movimento. A linha topo de gama do Qwen fechou.

## O ponto de licença que quase ninguém checa

"Peso aberto" e "open source" não são a mesma coisa. Na varredura apareceram três regimes
distintos no mesmo grupo de modelos ditos abertos.

1. **MIT de verdade.** GLM 5.2 e DeepSeek V4. Uso comercial livre.
2. **Licença própria com gatilho de receita.** Kimi K3. Acima de certo faturamento a coisa
   muda.
3. **Aberto na geração anterior, fechado no topo.** Qwen 3.6 aberto, Qwen 3.7 Max só API.

Para proposta comercial isso importa mais que meio ponto de benchmark. Vale colocar a
verificação de licença como item de checklist de arquitetura.

## Custo, o argumento mais forte

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

## Ângulo de posicionamento

O barateamento derruba o argumento de que IA é cara. Ele também derruba o argumento de que o
modelo é o diferencial. Se a capacidade fica barata e o gap aberto contra fechado é de três
pontos, o valor migra para três lugares.

1. O dado que só o cliente tem.
2. O harness e a orquestração em volta do modelo.
3. A medição que prova que aquilo funcionou.

Esses três são exatamente onde uma empresa de automação e pesquisa entrega. É a ponte natural
entre a varredura técnica e o discurso comercial.

## Fontes

- [Artificial Analysis, lançamentos recentes de peso aberto](https://artificialanalysis.ai/articles/recent-open-weights-model-launches)
- [Artificial Analysis, Openness Index](https://artificialanalysis.ai/evaluations/artificial-analysis-openness-index)
- [Epoch Capabilities Index](https://epoch.ai/eci)
