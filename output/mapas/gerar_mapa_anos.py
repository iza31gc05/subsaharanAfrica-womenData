"""Mapa dos anos observados em cada levantamento, com metades de área igual.

Execute da raiz: python output/mapas/gerar_mapa_anos.py
Dependências: matplotlib, pandas, numpy, shapely.
A cor representa o ano final observado; o rótulo preserva o intervalo inteiro.
"""

import json
import sqlite3

from gerar_mapa import PASTA, RAIZ, ISO, SQL, FORA, TEXTO, projetar
import matplotlib.pyplot as plt
import matplotlib.patheffects as pe
import numpy as np
import pandas as pd
from matplotlib.cm import ScalarMappable
from matplotlib.colors import LinearSegmentedColormap, Normalize
from matplotlib.patches import Patch, PathPatch
from matplotlib.path import Path
from shapely.geometry import shape, box
from shapely.geometry.polygon import orient
from shapely import transform

MARRONS = LinearSegmentedColormap.from_list(
    "anos_marrons", ["#f1dfc5", "#d2a576", "#a0693d", "#63371f"])

ROTULOS = {
    "AO": (17.7, -12.7, "Angola"), "BJ": (2.3, 10.2, "Benin"),
    "BF": (-1.6, 12.7, "Burkina\nFaso"), "BU": (29.9, -3.4, "Burundi"),
    "CM": (12.7, 5.6, "Camarões"), "TD": (18.7, 15.5, "Chade"),
    "KM": (43.5, -11.7, "Comores"), "CG": (15.2, -1.1, "Congo"),
    "CD": (23.6, -3.4, "R. D. do\nCongo"), "CI": (-5.5, 7.6, "Costa do\nMarfim"),
    "SZ": (31.5, -26.5, "Eswatini"), "ET": (39.6, 8.7, "Etiópia"),
    "GA": (11.6, -.7, "Gabão"), "GH": (-1.2, 7.6, "Gana"),
    "GN": (-10.8, 10.4, "Guiné"), "GM": (-15.3, 13.5, "Gâmbia"),
    "LS": (28.3, -29.5, "Lesoto"), "LB": (-9.4, 6.5, "Libéria"),
    "MD": (46.8, -19.4, "Madagascar"), "MW": (34.2, -13.3, "Malaui"),
    "ML": (-3.5, 18.4, "Mali"), "MZ": (35.3, -19.4, "Moçambique"),
    "NM": (17.2, -22, "Namíbia"), "NG": (8, 9.2, "Nigéria"),
    "NI": (9.1, 17.5, "Níger"), "KE": (38, .7, "Quênia"),
    "CF": (20.8, 6.8, "Rep. Centro-\nAfricana"), "RW": (29.9, -1.9, "Ruanda"),
    "SN": (-14.6, 14.8, "Senegal"), "SL": (-11.8, 8.5, "Serra Leoa"),
    "SD": (29.9, 15.6, "Sudão"), "ST": (6.6, .3, "São Tomé\ne Príncipe"),
    "TZ": (34.9, -6.5, "Tanzânia"), "TG": (1, 8.7, "Togo"),
    "ZW": (29.8, -19, "Zimbábue"), "ZM": (26.2, -13.7, "Zâmbia"),
    "ZA": (24.1, -29.7, "África do Sul"),
}
EXTERNOS = {
    "SN": (-22, 17.1), "GM": (-22.2, 13.7), "GN": (-19.8, 10.2),
    "SL": (-19, 6.5), "LB": (-16.4, 2.7), "CI": (-9, -.7),
    "GH": (-3.5, -2), "TG": (1.3, -6), "BJ": (4.8, 15),
    "ST": (3.5, -11), "CG": (17.3, 1.9), "GA": (10, -6),
    "RW": (44.5, 2), "BU": (44.5, -3.1), "MW": (39.5, -12.6),
    "SZ": (39, -27), "LS": (35.8, -32.6), "KM": (50, -9.5),
    "MZ": (42, -22), "CM": (4.5, 2.5), "MD": (53.5, -19.5),
}


def desenhar(ax, geometria, cor, contorno="white", espessura=.65, zorder=2):
    if geometria.is_empty:
        return
    if geometria.geom_type != "Polygon":
        for parte in geometria.geoms:
            if parte.geom_type in ("Polygon", "MultiPolygon", "GeometryCollection"):
                desenhar(ax, parte, cor, contorno, espessura, zorder)
        return
    vertices, codigos = [], []
    poligono = orient(geometria, sign=1)
    for anel in [poligono.exterior, *poligono.interiors]:
        pontos = list(anel.coords)
        vertices.extend(pontos)
        codigos.extend([Path.MOVETO] + [Path.LINETO] * (len(pontos) - 2) + [Path.CLOSEPOLY])
    ax.add_patch(PathPatch(Path(vertices, codigos), facecolor=cor,
                           edgecolor=contorno, linewidth=espessura, zorder=zorder))


def dividir(geometria):
    """Busca o corte vertical que divide a área projetada ao meio."""
    xmin, ymin, xmax, ymax = geometria.bounds
    baixo, alto = xmin, xmax
    for _ in range(60):
        meio = (baixo + alto) / 2
        esquerda = geometria.intersection(box(xmin - 1, ymin - 1, meio, ymax + 1))
        if esquerda.area < geometria.area / 2:
            baixo = meio
        else:
            alto = meio
    corte = (baixo + alto) / 2
    esquerda = geometria.intersection(box(xmin - 1, ymin - 1, corte, ymax + 1))
    direita = geometria.intersection(box(corte, ymin - 1, xmax + 1, ymax + 1))
    assert abs(esquerda.area / geometria.area - .5) < 1e-8
    assert abs(direita.area / geometria.area - .5) < 1e-8
    assert esquerda.intersection(direita).area < 1e-8
    assert esquerda.union(direita).symmetric_difference(geometria).area / geometria.area < 1e-8
    return esquerda, direita


def intervalo(row):
    inicio, fim = int(row.ano_inicial), int(row.ano_final)
    return str(fim) if inicio == fim else f"{inicio}–{fim}"


def main():
    with sqlite3.connect((RAIZ / "saude_mulher_normalizado.db").as_uri() + "?mode=ro", uri=True) as conn:
        dados = pd.read_sql_query(SQL, conn)
        paises = {row[0] for row in conn.execute("SELECT codigo FROM Pais")}
        sem_ano = conn.execute("SELECT COUNT(*) FROM Entrevista WHERE ano IS NULL").fetchone()[0]
    assert not sem_ano, "Há entrevistas sem ano; explicitar a ausência antes de gerar o mapa."
    assert dados[["ano_inicial", "ano_final"]].notna().all().all()
    assert (dados.ano_inicial <= dados.ano_final).all()
    assert set(dados.codigo) == paises
    assert set(dados.codigo) <= ISO.keys()
    dados = dados.sort_values(["nome", "ano_inicial", "ano_final", "levantamento_id"])
    dados["iso3"] = dados.codigo.map(ISO)
    dados["ano_cor"] = dados.ano_final.astype(int)
    dados["periodo_observado"] = [intervalo(row) for row in dados.itertuples()]
    grupos = {iso: frame for iso, frame in dados.groupby("iso3")}
    assert all(1 <= len(frame) <= 2 for frame in grupos.values())
    escala = Normalize(vmin=int(dados.ano_cor.min()), vmax=int(dados.ano_cor.max()))
    fonte = json.loads((PASTA / "africa_natural_earth_50m.geojson").read_text(encoding="utf-8"))
    geometrias = {f["properties"]["ADM0_A3"]: transform(
                     shape(f["geometry"]),
                     lambda coordenadas: np.column_stack(projetar(coordenadas[:, 0], coordenadas[:, 1])))
                  for f in fonte["features"]}
    assert set(grupos) <= geometrias.keys()

    plt.rcParams.update({"font.family": "DejaVu Sans", "svg.fonttype": "none"})
    fig = plt.figure(figsize=(14, 14), facecolor="white")
    ax = fig.add_axes([.025, .19, .95, .66])
    auditoria = []
    for iso, geometria in geometrias.items():
        if iso not in grupos:
            desenhar(ax, geometria, FORA)
            continue
        frame = grupos[iso]
        partes = dividir(geometria) if len(frame) == 2 else [geometria]
        for parte, row in zip(partes, frame.itertuples()):
            desenhar(ax, parte, MARRONS(escala(row.ano_cor)))
            auditoria.append({"codigo": row.codigo, "levantamento_id": row.levantamento_id,
                              "periodo_observado": row.periodo_observado, "ano_cor": row.ano_cor,
                              "fracao_area": parte.area / geometria.area})

    for codigo, frame in dados.groupby("codigo", sort=False):
        lon, lat, nome = ROTULOS[codigo]
        xy = projetar(lon, lat)
        fora = codigo in EXTERNOS
        destino = projetar(*EXTERNOS[codigo]) if fora else xy
        cor = MARRONS(escala(frame.ano_cor.mean()))
        brilho = sum(c * p for c, p in zip(cor[:3], [.2126, .7152, .0722]))
        texto_cor = TEXTO if fora or brilho > .58 else "white"
        # Cada período tem seu rótulo na ordem esquerda → direita.
        anos = "\n".join(frame.periodo_observado)
        label = f"{nome}\n{anos}"
        if fora:
            ax.plot([xy[0], destino[0]], [xy[1], destino[1]], color="#a99a8d", lw=.65, zorder=3)
            ax.scatter(*xy, s=8, color=cor, edgecolors="white", linewidths=.35, zorder=4)
        tamanho = 7.5 if codigo in ("BF", "CM", "CF", "NG", "ML", "KE", "NI") else 8
        t = ax.text(*destino, label, ha="center", va="center", fontsize=tamanho,
                    linespacing=1.2, color=texto_cor, zorder=5)
        if fora:
            t.set_path_effects([pe.withStroke(linewidth=2.7, foreground="white")])

    ax.set(xlim=(-4900, 3900), ylim=(-4200, 4450), aspect="equal")
    ax.axis("off")
    fig.text(.075, .943, "Anos dos levantamentos observados", fontsize=25, weight="bold", color=TEXTO)
    fig.text(.075, .907, "Países incluídos na base de saúde da mulher", fontsize=14, color="#66584e")
    fig.text(.075, .875, f"{len(grupos)} países  ·  {len(dados)} levantamentos  ·  Mais escuro = ano mais recente", fontsize=11, color="#66584e")
    cax = fig.add_axes([.18, .158, .48, .014])
    barra = fig.colorbar(ScalarMappable(norm=escala, cmap=MARRONS), cax=cax, orientation="horizontal")
    barra.set_ticks(np.arange(1990, 2026, 5))
    barra.ax.tick_params(labelsize=8, length=3, color="#80756c", labelcolor=TEXTO)
    barra.outline.set_visible(False)
    barra.set_label("Ano final observado no levantamento", fontsize=9, color=TEXTO)
    fig.legend(handles=[Patch(facecolor=FORA, label="Fora do estudo")], loc="center",
               bbox_to_anchor=(.79, .163), frameon=False, fontsize=10,
               handlelength=1.8, handleheight=1.3, labelcolor=TEXTO)
    fig.text(.075, .108, "Dois levantamentos: 50% da área para cada um; mais antigo à esquerda, mais recente à direita.", fontsize=9, color="#66584e")
    fig.text(.075, .089, "Rótulos mostram o intervalo completo de anos; a cor corresponde ao último ano observado de cada levantamento.", fontsize=9, color="#66584e")
    fig.text(.075, .070, "A divisão é apenas gráfica. Inclui os levantamentos suplementares de contracepção.", fontsize=9, color="#66584e")
    fig.text(.075, .043, "Fonte: saude_mulher_normalizado.db · Entrevista.ano · Cartografia: Natural Earth 1:50m · Projeção equivalente de Lambert", fontsize=8, color="#80756c")
    for formato in ("png", "svg", "pdf"):
        fig.savefig(PASTA / f"mapa_anos_por_pais.{formato}", dpi=250, facecolor="white")
    fig.savefig(PASTA / "mapa_anos_por_pais_previa.png", dpi=110, facecolor="white")
    plt.close(fig)
    dados.to_csv(PASTA / "anos_observados_por_levantamento.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(auditoria).to_csv(PASTA / "validacao_metades_anos.csv", index=False, encoding="utf-8-sig")
    n_duplos = sum(len(frame) == 2 for frame in grupos.values())
    print(f"Validado: {len(grupos)} países, {len(dados)} levantamentos, {n_duplos} países divididos em áreas iguais.")
    print(f"Anos de cor: {int(escala.vmin)}–{int(escala.vmax)}; todas as entrevistas têm ano.")


if __name__ == "__main__":
    main()
