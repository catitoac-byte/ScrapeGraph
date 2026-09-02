# Pacote de compartilhamento

Exportação da vertical `news-varredura` do projeto ScrapeGraph. Varredura de 2026-09-02.

## O que tem aqui

| Arquivo | Uso |
|---|---|
| `varredura-ia-dossie-completo.md` | Os 13 documentos em um arquivo só. É o que entregar para outro agente ou colar como contexto |
| `fatos-citaveis.csv` | 73 afirmações com número, fonte, URL, data e nível de confiança. Filtrar por `confianca` antes de escrever |
| `fontes.csv` | 39 fontes com status de coleta verificado e cadência |
| `biblioteca-anthropic.csv` | 44 posts de engenharia e pesquisa da Anthropic, com data e link |
| `raspar_news_ia.py` | Script de varredura recorrente. Sem dependência externa |

## Para outro projeto usar

Copiar a pasta inteira e apontar o agente para `varredura-ia-dossie-completo.md`.

Antes de escrever qualquer peça, filtrar os fatos:

```bash
python3 -c "
import csv
for f in csv.DictReader(open('fatos-citaveis.csv', encoding='utf-8-sig')):
    if f['confianca'] in ('A','B'):
        print(f\"[{f['confianca']}] {f['afirmacao']}: {f['numero']}  ({f['fonte']}, {f['data_fonte']})\")
"
```

## Para manter atualizado

```bash
python3 raspar_news_ia.py --dias 14
```

Gera um CSV e um markdown datados. Cobre 22 fontes, sendo 16 por RSS, 6 raspadas por HTML
porque não publicam feed, mais 4 consultas ao arXiv.

## Regra que não pode se perder na cópia

Nível **A** é fonte primária lida direto. **B** é primária citada por terceiro confiável.
**C** é secundária ou agregador de SEO.

Só A e B vão para material publicado. C é pista de pesquisa.

Ranking de LLM muda em semanas. Toda citação de leaderboard sai com a data junto.
