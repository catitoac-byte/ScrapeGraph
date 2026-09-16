"""Mede precisao e cobertura dos codigos contra uma amostra codificada a mao.

    uv run python painel/avaliar_codigos.py moda validacao_moda.json ouro_validacao_moda.json

Amostras e gabaritos ficam em dados/saida/lojas_google/validacao/ (fora do git).
"""
import json, re, collections, sys
SP=str(__import__("pathlib").Path(__file__).resolve().parents[1] / "dados/saida/lojas_google/validacao")+"/"
vert, amostra, ouro = sys.argv[1], sys.argv[2], sys.argv[3]
temas=[(t["id"],re.compile(t["re"],re.I)) for t in json.load(open(f"verticais/{vert}.json"))["temas"]]
am=json.load(open(SP+amostra)); ou={int(k):v for k,v in json.load(open(SP+ouro)).items()}
full={}
t=open(f"dados/saida/lojas_google/painel/{vert}/data.js").read(); d=json.loads(t[t.index("=")+1:].rstrip().rstrip(";"))
tp=collections.Counter();fp=collections.Counter();fn=collections.Counter();err=collections.defaultdict(list)
textos={}
for r in d["avaliacoes"]:
    if r["t"]: textos[r["t"][:400]]=r["t"]
for o in am:
    txt=textos.get(o["t"],o["t"]); r={k for k,rx in temas if rx.search(txt)}; g=set(ou[o["n"]])
    for c,_ in temas:
        if c in g and c in r: tp[c]+=1
        elif c in r: fp[c]+=1; err[c].append(f"FP{o['n']}")
        elif c in g: fn[c]+=1; err[c].append(f"FN{o['n']}")
print(f'{"codigo":<16}{"ouro":>5}{"precisao":>10}{"cobertura":>10}  erros')
for c,_ in temas:
    n=tp[c]+fn[c]; pr=tp[c]/(tp[c]+fp[c]) if tp[c]+fp[c] else None; rc=tp[c]/n if n else None
    print(f'{c:<16}{n:>5}{(f"{pr:.0%}" if pr is not None else "-"):>10}{(f"{rc:.0%}" if rc is not None else "-"):>10}  {" ".join(err[c][:10])}')
T=sum(tp.values()); print(f"GERAL precisao {T/(T+sum(fp.values())):.0%} cobertura {T/(T+sum(fn.values())):.0%}")
