"""Gráficos da apresentação sobre saúde da mulher, derivados do SQLite.

Execute da raiz: python output/apresentacao/gerar_graficos.py
As fontes são abertas em modo somente leitura. PNG para slides; SVG/PDF
para edição/exportação. CSVs permitem auditar percentuais e denominadores.
Pontos em escala comum seguem Cleveland & McGill (1984); as escalas e os
recortes explícitos seguem a orientação de representação fiel de Cairo (2019).
"""

from pathlib import Path
import hashlib
import json
import sqlite3
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.lines import Line2D
import numpy as np
import pandas as pd


PASTA = Path(__file__).resolve().parent
RAIZ = PASTA.parents[1]
BANCO = RAIZ / "saude_mulher_partos.db"
MARROM, AZUL, TEXTO = "#964B00", "#31516A", "#302B27"
GRUPOS = ["menos_sem", "menos_sec", "mais_sem", "mais_sec"]
NOMES = {"CD": "RD do Congo", "SZ": "Eswatini", "CF": "Rep. Centro-Africana"}

SQL_CONTRACEPCAO = """
SELECT p.codigo, p.nome, MIN(e.ano) AS inicio, MAX(e.ano) AS fim,
       d.riqueza, m.escolaridade, CAST((m.idade-25)/5 AS INTEGER) AS faixa,
       COUNT(*) AS n, SUM(e.peso) AS peso, SUM(e.peso*e.usa_metodo) AS uso
FROM Entrevista e JOIN Mulher m ON m.id=e.mulher_id
JOIN Domicilio d ON d.id=m.domicilio_id
JOIN Levantamento l ON l.id=d.levantamento_id JOIN Pais p ON p.codigo=l.pais_codigo
WHERE e.coorte!='nucleo_exclusivo' AND e.peso>0 AND e.usa_metodo IN(0,1)
  AND m.idade BETWEEN 25 AND 39 AND d.riqueza BETWEEN 1 AND 5
  AND m.escolaridade BETWEEN 0 AND 3
GROUP BY p.codigo,p.nome,d.riqueza,m.escolaridade,faixa
"""

SQL_MATERNO = """
SELECT p.codigo,p.nome,MIN(e.ano) AS inicio,MAX(e.ano) AS fim,d.riqueza,d.residencia,
       COUNT(*) AS nascimentos_recentes,
       SUM(CASE WHEN n.consultas_prenatal_codigo BETWEEN 0 AND 90 THEN 1 ELSE 0 END) AS n_prenatal,
       SUM(CASE WHEN n.consultas_prenatal_codigo BETWEEN 0 AND 90 THEN e.peso ELSE 0 END) AS peso_pre,
       SUM(CASE WHEN n.consultas_prenatal_codigo BETWEEN 4 AND 90 THEN e.peso ELSE 0 END) AS peso_pre4,
       SUM(CASE WHEN n.cesarea_codigo IN(0,1) THEN 1 ELSE 0 END) AS n_cesarea,
       SUM(CASE WHEN n.cesarea_codigo IN(0,1) THEN e.peso ELSE 0 END) AS peso_ces,
       SUM(CASE WHEN n.cesarea_codigo=1 THEN e.peso ELSE 0 END) AS peso_ces1
FROM Crianca k JOIN Nascimento n ON n.id=k.nascimento_id
JOIN Entrevista e ON e.mulher_id=n.mulher_id JOIN Mulher m ON m.id=e.mulher_id
JOIN Domicilio d ON d.id=m.domicilio_id
JOIN Levantamento l ON l.id=d.levantamento_id JOIN Pais p ON p.codigo=l.pais_codigo
WHERE k.indice=1 AND e.data_cmc-n.data_cmc BETWEEN 0 AND 59 AND e.peso>0
  AND d.residencia IN(1,2) AND m.idade BETWEEN 15 AND 49
GROUP BY p.codigo,p.nome,d.riqueza,d.residencia
"""


def numero(x):
    return f"{x:.1f}".replace(".", ",")


def periodo(inicio, fim):
    return str(int(inicio)) if inicio == fim else f"{int(inicio)}–{int(fim)}"


def rotulo(linha):
    return f"{NOMES.get(linha.codigo, linha.nome)} · {periodo(linha.inicio, linha.fim)}"


def csv(df, nome):
    df.to_csv(PASTA / nome, index=False, encoding="utf-8-sig")


def salvar(fig, nome):
    # Mantém a proporção 16:9 e a mesma composição nos três formatos.
    fig.savefig(PASTA / f"{nome}.png", dpi=240, facecolor="white")
    fig.savefig(PASTA / f"{nome}.svg", facecolor="white")
    fig.savefig(PASTA / f"{nome}.pdf", facecolor="white")
    plt.close(fig)


def base(titulo, subtitulo):
    fig = plt.figure(figsize=(16, 9), facecolor="white")
    artistas = [fig.text(.045, .93, titulo, fontsize=25, weight="bold", color=TEXTO),
                fig.text(.045, .875, subtitulo, fontsize=15, color="#605951")]
    fig.canvas.draw()
    for artista in artistas:
        largura = artista.get_window_extent(fig.canvas.get_renderer()).width
        disponivel = fig.bbox.width * .91
        if largura > disponivel:
            artista.set_fontsize(artista.get_fontsize() * disponivel / largura)
    return fig


def pareado(df, esquerda, direita, legendas, titulo, subtitulo, rodape, arquivo,
            limite=100, coluna_nomes=None):
    fig = base(titulo, subtitulo)
    ax = fig.add_axes([.23, .22, .63, .55])
    y = np.arange(len(df))
    ax.hlines(y, df[esquerda], df[direita], color="#D6CDC3", linewidth=3, zorder=1)
    ax.scatter(df[esquerda], y, color=AZUL, marker="o", s=105, zorder=3)
    ax.scatter(df[direita], y, color=MARROM, marker="D", s=100, zorder=3)
    for pos, (_, linha) in enumerate(df.iterrows()):
        ax.annotate(numero(linha[esquerda]), (linha[esquerda], pos), xytext=(0, -22),
                    textcoords="offset points", ha="center", fontsize=14, color=AZUL)
        ax.annotate(numero(linha[direita]), (linha[direita], pos), xytext=(0, 13),
                    textcoords="offset points", ha="center", fontsize=14, color=MARROM)
        ax.text(1.035, pos, f"+{numero(linha[direita]-linha[esquerda])}",
                transform=ax.get_yaxis_transform(), va="center", fontsize=16,
                weight="bold", color=TEXTO)
    ax.text(1.035, 1.08, "Diferença\n(p.p.)", transform=ax.transAxes,
            fontsize=12, color="#605951")
    nomes = df[coluna_nomes] if coluna_nomes else df.apply(rotulo, axis=1)
    ax.set_yticks(y, nomes)
    ax.set_ylim(-.6, len(df)-.4)
    ax.invert_yaxis()
    ax.set_xlim(0, limite)
    ax.set_xticks(np.linspace(0, limite, 5))
    ax.set_xlabel("Percentual ponderado (%)", fontsize=15, labelpad=10)
    ax.tick_params(axis="both", length=0, labelsize=15, pad=9)
    ax.grid(axis="x", color="#E6E1DC", linewidth=.7)
    ax.set_axisbelow(True)
    for spine in ax.spines.values():
        spine.set_visible(False)
    handles = [Line2D([], [], linestyle="", marker="o", color=AZUL, markersize=9),
               Line2D([], [], linestyle="", marker="D", color=MARROM, markersize=8)]
    fig.legend(handles, legendas, loc="upper left", bbox_to_anchor=(.22, .845),
               ncol=2, frameon=False, fontsize=14, columnspacing=2)
    fig.text(.045, .06, rodape, fontsize=11.5, color="#605951", linespacing=1.65)
    salvar(fig, arquivo)


def padronizar(a, minimo=30):
    a = a.copy()
    a["grupo"] = None
    a.loc[(a.riqueza<=2)&(a.escolaridade==0), "grupo"] = "menos_sem"
    a.loc[(a.riqueza<=2)&(a.escolaridade>=2), "grupo"] = "menos_sec"
    a.loc[(a.riqueza>=4)&(a.escolaridade==0), "grupo"] = "mais_sem"
    a.loc[(a.riqueza>=4)&(a.escolaridade>=2), "grupo"] = "mais_sec"
    b = a.dropna(subset="grupo").groupby(["codigo","nome","grupo","faixa"], as_index=False)[["n","peso","uso"]].sum()
    linhas, cobertura = [], []
    for (codigo, nome), g in b.groupby(["codigo", "nome"]):
        n = g.pivot(index="faixa", columns="grupo", values="n").reindex(index=[0,1,2], columns=GRUPOS)
        elegivel = bool(n.ge(minimo).all().all())
        cobertura.append({"codigo":codigo,"nome":nome,"minimo_por_faixa":minimo,
                          "menor_celula":float(n.fillna(0).min().min()),"incluido":elegivel})
        if not elegivel:
            continue
        pais = a[a.codigo==codigo]
        padrao = pais.groupby("faixa").peso.sum().reindex([0,1,2])
        padrao = padrao / padrao.sum()
        pesos = g.pivot(index="faixa", columns="grupo", values="peso").reindex(index=[0,1,2], columns=GRUPOS)
        usos = g.pivot(index="faixa", columns="grupo", values="uso").reindex(index=[0,1,2], columns=GRUPOS)
        estimativas = (100*usos/pesos).mul(padrao, axis=0).sum()
        assert np.isclose(padrao.sum(), 1)
        for grupo in GRUPOS:
            linhas.append({"codigo":codigo,"nome":nome,"inicio":pais.inicio.min(),"fim":pais.fim.max(),
                           "grupo":grupo,"n":int(n[grupo].sum()),
                           "percentual":estimativas[grupo],"minimo_por_faixa":minimo})
    return pd.DataFrame(linhas), pd.DataFrame(cobertura)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    plt.rcParams.update({"font.family":"DejaVu Sans", "text.color":TEXTO,
                         "axes.labelcolor":TEXTO, "xtick.color":TEXTO, "ytick.color":TEXTO,
                         "svg.fonttype":"none", "pdf.fonttype":42})
    with BANCO.open("rb") as arquivo:
        hash_antes = hashlib.file_digest(arquivo, "sha256").hexdigest()
    with sqlite3.connect(BANCO.as_uri()+"?mode=ro", uri=True) as banco:
        a = pd.read_sql_query(SQL_CONTRACEPCAO, banco)
        materno = pd.read_sql_query(SQL_MATERNO, banco)
        assert not banco.execute("""SELECT n.mulher_id FROM Crianca k
            JOIN Nascimento n ON n.id=k.nascimento_id WHERE k.indice=1
            GROUP BY n.mulher_id HAVING COUNT(*)>1 LIMIT 1""").fetchone(), "Último parto duplicado"
    estimativas, cobertura = padronizar(a)
    csv(a, "contracepcao_estratos_25_39.csv")
    csv(estimativas, "contracepcao_perfis_padronizados.csv")
    csv(cobertura, "cobertura_comparacao_perfis.csv")
    sensibilidade = []
    for minimo in (30,50,100):
        estimativa, cob = padronizar(a, minimo)
        cob["limiar"] = minimo
        sensibilidade.append(cob)
    csv(pd.concat(sensibilidade, ignore_index=True), "sensibilidade_cobertura.csv")
    perfis = estimativas.pivot(index=["codigo","nome","inicio","fim"], columns="grupo", values="percentual").reset_index()
    perfis["diferenca_pp"] = perfis.menos_sec-perfis.mais_sem
    perfis = perfis.sort_values("diferenca_pp", ascending=False)
    assert perfis[GRUPOS].ge(0).all().all() and perfis[GRUPOS].le(100).all().all()
    csv(perfis, "slide7_contrastes.csv")
    pareado(perfis, "mais_sem", "menos_sec",
            ["Maior riqueza · sem escolaridade", "Menor riqueza · secundário/superior"],
            "Mais riqueza não coincide sempre com maior uso contraceptivo",
            "Comparação entre perfis de mulheres de 25–39 anos, com a mesma composição etária em cada país",
            "Menor riqueza = quintis 1–2; maior riqueza = quintis 4–5, relativos a cada país. Uso atual de qualquer método.\n"
            "Somente países com ≥30 respostas por perfil em cada faixa: 25–29, 30–34 e 35–39 anos. Associações descritivas, sem inferência causal.",
            "slide7a_escolaridade_riqueza")

    fig = base("A associação com escolaridade varia entre os países",
               "Uso contraceptivo ponderado e padronizado por idade (%) · mulheres de 25–39 anos")
    ax = fig.add_axes([.23,.25,.68,.53])
    cor = LinearSegmentedColormap.from_list("terra", ["#FFF8EF","#CC9A61","#6B310B"])
    valores = perfis[GRUPOS].to_numpy()
    im = ax.imshow(valores, vmin=0, vmax=100, cmap=cor, aspect="auto")
    for linha in range(len(perfis)):
        for coluna in range(4):
            valor = valores[linha,coluna]
            ax.text(coluna, linha, numero(valor), ha="center", va="center", fontsize=19,
                    color="white" if valor>55 else TEXTO, weight="bold")
    ax.set_yticks(np.arange(len(perfis)), perfis.apply(rotulo, axis=1))
    ax.set_xticks(range(4), ["Menor riqueza\nSem escolaridade", "Menor riqueza\nSecundário/superior",
                             "Maior riqueza\nSem escolaridade", "Maior riqueza\nSecundário/superior"])
    ax.tick_params(length=0, labelsize=13.5, pad=12)
    for spine in ax.spines.values():
        spine.set_visible(False)
    cb = fig.colorbar(im, cax=fig.add_axes([.49,.13,.34,.018]), orientation="horizontal")
    cb.set_ticks([0,25,50,75,100])
    cb.ax.tick_params(labelsize=11, length=0)
    cb.outline.set_visible(False)
    fig.text(.045,.045,"Mesmo recorte do gráfico anterior. Países ordenados pelo contraste entre menor riqueza com escolaridade e maior riqueza sem escolaridade.\n"
             "Estimativas pontuais; não foram calculados intervalos de confiança considerando o desenho amostral DHS.", fontsize=11.5, color="#605951", linespacing=1.6)
    salvar(fig, "slide7b_perfis_completos")

    csv(materno, "cuidado_materno_estratos.csv")
    prenatal = materno[materno.riqueza.between(1,5)].groupby(["codigo","nome","riqueza"], as_index=False).agg(
        inicio=("inicio","min"),fim=("fim","max"),n=("n_prenatal","sum"),
        peso=("peso_pre","sum"),numerador=("peso_pre4","sum"))
    prenatal["percentual"] = 100*prenatal.numerador/prenatal.peso
    prenatal.loc[prenatal.n<30,"percentual"] = np.nan
    csv(prenatal, "prenatal_por_riqueza.csv")
    extremos = prenatal.pivot(index=["codigo","nome"],columns="riqueza",values="percentual")[[1,5]].dropna().rename(columns={1:"pobre",5:"rico"}).reset_index()
    periodos = prenatal.groupby("codigo",as_index=False).agg(inicio=("inicio","min"),fim=("fim","max"))
    extremos = extremos.merge(periodos, on="codigo")
    extremos["diferenca_pp"] = extremos.rico-extremos.pobre
    csv(extremos, "prenatal_contrastes_todos_paises.csv")
    exemplo_pre = extremos.set_index("codigo").loc[["ZM","BU","AO"]].reset_index()
    pareado(exemplo_pre, "pobre", "rico", ["Quintil mais pobre", "Quintil mais rico"],
            "Baixa desigualdade não garante ampla cobertura de pré-natal",
            "≥4 consultas no último parto dos cinco anos anteriores à entrevista · três exemplos entre os países comparáveis",
            "Mulheres de 15–49 anos; percentuais ponderados entre respostas válidas. Quintis relativos a cada país.\n"
            "≥30 respostas em cada quintil extremo. O indicador descreve quantidade de consultas, não qualidade do cuidado.",
            "slide8_prenatal_riqueza")

    cesarea = materno.groupby(["codigo","nome","residencia"],as_index=False).agg(
        inicio=("inicio","min"),fim=("fim","max"),n=("n_cesarea","sum"),
        peso=("peso_ces","sum"),numerador=("peso_ces1","sum"))
    cesarea["percentual"] = 100*cesarea.numerador/cesarea.peso
    cesarea.loc[cesarea.n<30,"percentual"] = np.nan
    csv(cesarea, "cesareas_por_residencia.csv")
    areas = cesarea.pivot(index=["codigo","nome"],columns="residencia",values="percentual")[[1,2]].dropna().rename(columns={1:"urbano",2:"rural"}).reset_index()
    periodos = cesarea.groupby("codigo",as_index=False).agg(inicio=("inicio","min"),fim=("fim","max"))
    areas = areas.merge(periodos, on="codigo")
    areas["diferenca_pp"] = areas.urbano-areas.rural
    csv(areas, "cesareas_contrastes_todos_paises.csv")
    exemplo_ces = areas.set_index("codigo").loc[["AO","RW","LS"]].reset_index()
    pareado(exemplo_ces, "rural", "urbano", ["Área rural", "Área urbana"],
            "O contexto nacional também diferencia a assistência ao parto",
            "Cesáreas no último parto dos cinco anos anteriores à entrevista · exemplos com levantamentos em 2023–2025",
            "Mulheres de 15–49 anos; percentuais ponderados entre respostas válidas, com ≥30 respostas por área.\n"
            "Frequência de cesáreas, isoladamente, não identifica necessidade clínica, qualidade do cuidado nem sucesso de políticas públicas.",
            "slide9_cesareas_territorio", limite=40)

    validacao = {
        "banco":BANCO.name,"sha256":hash_antes,
        "mulheres_recorte_25_39":int(a.n.sum()),"paises_com_riqueza_escolaridade_validas":int(a.codigo.nunique()),
        "paises_com_quatro_perfis_comparaveis":int(len(perfis)),
        "perfis_menor_riqueza_escolarizada_acima_maior_riqueza_sem":int((perfis.diferenca_pp>0).sum()),
        "paises_prenatal_comparavel":int(len(extremos)),"mais_rico_acima_mais_pobre":int((extremos.diferenca_pp>0).sum()),
        "paises_cesarea_comparavel":int(len(areas)),"cesarea_urbano_acima_rural":int((areas.diferenca_pp>0).sum()),
        "avisos":["Análise exploratória; os grupos não foram aleatorizados.",
                  "Sem intervalos de confiança ou testes que incorporem estratos e conglomerados DHS.",
                  "Contracepção padronizada apenas por idade, não por residência, união, paridade ou intenção reprodutiva.",
                  "Não uso contraceptivo não equivale a necessidade não atendida ou falta de autonomia.",
                  "Não comparar diretamente os percentuais de contracepção com os de cuidado materno: os denominadores diferem.",
                  "O pré-natal e as cesáreas foram recalculados no modelo de partos, com idade 15–49 e ponderação.",
                  "Anos dos levantamentos variam; não são estimativas contemporâneas para toda a região."]
    }
    with BANCO.open("rb") as arquivo:
        assert hashlib.file_digest(arquivo,"sha256").hexdigest()==hash_antes, "Banco de origem alterado"
    (PASTA/"validacao.json").write_text(json.dumps(validacao,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    metodologia = """GRÁFICOS PARA A APRESENTAÇÃO — SAÚDE DA MULHER NA ÁFRICA SUBSAARIANA

Fonte: saude_mulher_partos.db, derivado dos levantamentos DHS do projeto.
Reprodução: python output/apresentacao/gerar_graficos.py
Leitura do banco em modo somente leitura; hash SHA-256 registrado em validacao.json.

SLIDE 7 — ESCOLARIDADE, RIQUEZA E CONTRACEPÇÃO
População: mulheres de 25 a 39 anos com resposta contraceptiva válida, peso positivo,
riqueza 1–5 e escolaridade 0–3; uma coorte temática por país.
Menor riqueza: quintis 1–2. Maior riqueza: quintis 4–5. Quintil 3 excluído dos
perfis contrastados, mas incluído na população etária de referência do país.
Escolaridade: nenhuma (0) versus secundário/superior (2–3). Primário não integra
os perfis, mas integra a população de referência.
Faixas: 25–29, 30–34 e 35–39. Cada um dos quatro perfis deve ter pelo menos
30 respostas em cada faixa. A mesma distribuição ponderada de idade de todas
as mulheres elegíveis do país é aplicada aos quatro perfis.
Fórmula: taxa padronizada do perfil = soma_faixas(proporção_etária_referência *
soma(peso*uso)_perfil,faixa / soma(peso)_perfil,faixa) * 100.
Não foram ajustadas outras características. A restrição etária permite observar
mulheres com mais tempo para completar escolarização; não elimina confundimento.
Os países excluídos e os limiares alternativos de 50/100 estão nos CSVs de cobertura.
O resultado para os sete países elegíveis não pode ser generalizado aos 37 países.

SLIDE 8 — PRÉ-NATAL
Mulheres de 15–49 anos; último parto nos 60 meses anteriores à entrevista,
identificado pela criança com indice=1. Cada mulher entra uma vez.
≥4 consultas é o indicador adotado pelo projeto; códigos 0–90 válidos, 4–90 no numerador.
Percentuais ponderados; pelo menos 30 respostas por quintil para exibição.
Não é uma medida de adequação clínica atual nem de qualidade do cuidado.
Exemplos apresentados: Zâmbia (pequena diferença, patamar elevado), Burundi
(pequena diferença, patamar mais baixo) e Angola (grande diferença). Os demais
países constam no CSV completo. As datas são diferentes e estão nos rótulos;
os exemplos não constituem comparação contemporânea nem ranking de políticas.

SLIDE 9 — CESÁREAS
Mesmo recorte de último parto, idade e peso; inclui residências válidas mesmo sem
informação de riqueza. Cesarea_codigo=1 no numerador; códigos 0/1 no denominador.
Percentuais ponderados, pelo menos 30 respostas por área e sem padronização etária.
Conflitos de atributos do parto detectados na migração ficam NULL e são excluídos
do denominador correspondente. Países escolhidos para ilustrar diferentes níveis:
Angola, Ruanda e Lesoto, com levantamentos de 2023–2025. Não constituem ranking.

LEITURA DOS RESULTADOS
Associações descritivas, sem demonstração de causalidade ou significância estatística.
Não uso contraceptivo não significa falta de acesso, autonomia ou necessidade não
atendida: não foram avaliados intenção reprodutiva, união ou atividade sexual.
Cesáreas mais ou menos frequentes não demonstram isoladamente melhor/pior cuidado.
Períodos e denominadores são próprios de cada comparação; nunca somar pesos dos
países para inferir uma prevalência da África Subsaariana.
"""
    (PASTA/"metodologia.txt").write_text(metodologia,encoding="utf-8")
    print(json.dumps(validacao,ensure_ascii=False,indent=2), flush=True)
    print(perfis[["codigo","mais_sem","menos_sec","diferenca_pp"]].round(2).to_string(index=False),flush=True)
    print(exemplo_ces[["codigo","rural","urbano","diferenca_pp"]].round(2).to_string(index=False),flush=True)


if __name__ == "__main__":
    main()
