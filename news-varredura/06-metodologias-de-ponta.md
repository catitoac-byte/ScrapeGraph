# Metodologias de ponta

Coletado em 2026-09-02. O que mudou de verdade em como se treina, avalia e opera modelo.

---

## RLVR, aprendizado por reforço com recompensa verificável

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

## Evals, o que virou consenso operacional

Este é o bloco mais transferível para consultoria, porque descreve infraestrutura que a maioria
das empresas não tem. Lembrar do achado do MIT. A causa raiz do fracasso dos pilotos não é
tecnologia, é que ninguém construiu a medição que prova que o piloto funciona. **[B]**

### Os três modos de LLM as judge

| Modo | Quando usar |
|---|---|
| Comparação pareada | Escolher qual de duas saídas é melhor. O mais confiável |
| Nota com referência | Existe resposta correta conhecida para comparar |
| Nota sem referência | Só rubrica, sem âncora. O mais frágil dos três |

### Calibração

- Amostrar de 200 a 500 casos representativos com anotação de especialista.
- Iterar o texto do prompt até a correlação passar de 0,85.
- Reteste trimestral, porque modelo e dado mudam.
- Alternativa mais enxuta. De 100 a 300 traces de produção, de 2 a 3 anotadores humanos, com a
  mesma rubrica que o juiz vai ver.

### Produção

- Amostragem de 1% a 10% dos traces em produção, mais 100% em CI.
- Humano cuida do que for sinalizado como falha.
- Modelo de juiz menor e rápido para fluxo bloqueante. Modelo grande só em análise offline.
- Cachear prompt e resultado de avaliação para entrada idêntica.

### Regras de ouro

1. Usar família de modelo diferente da do gerador, para evitar viés de autopreferência. É a
   mesma lógica do evaluator separado no harness da Anthropic.
2. Checagem determinística com código, por exemplo validade de esquema e casamento exato.
   Juiz de LLM só para checagem semântica, como correção, fidelidade e segurança.
3. Consistência de harness. Mesmo modelo de juiz, mesma rubrica, mesma temperatura entre
   rodadas. Harness que muda entre execuções produz notas incomparáveis.

## O fio condutor das três frentes

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

## Fontes

- [Tülu 3, pós-treino aberto](https://arxiv.org/pdf/2411.15124)
- [Rubrics as Rewards, RL além de domínios verificáveis](https://openreview.net/forum?id=c1bTcrDmt4)
- [Awesome RLVR, coletânea](https://github.com/opendilab/awesome-RLVR)
- [Evidently AI, guia de LLM as judge](https://www.evidentlyai.com/llm-guide/llm-as-a-judge)
- [Arize, juízes que aguentam produção](https://arize.com/blog/how-to-build-llm-as-a-judge-evaluators-that-hold-up-in-production/)
