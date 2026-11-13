"""Mapa da cobertura efetiva de entrevistas femininas no estudo.

Execute da raiz: python output/mapas/gerar_mapa.py
Contagem de mulheres com entrevista, sem ponderação amostral, por país.
Geometria: Natural Earth 1:50m (arquivo local, sem acesso à rede).
"""

import json
import sqlite3
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patheffects as pe
import numpy as np
import pandas as pd
from matplotlib.patches import Patch, PathPatch
from matplotlib.path import Path as MplPath
from matplotlib.colors import LinearSegmentedColormap, Normalize
from matplotlib.cm import ScalarMappable
from matplotlib.ticker import FuncFormatter

PASTA = Path(__file__).resolve().parent
RAIZ = PASTA.parents[1]
MARROM = LinearSegmentedColormap.from_list("marrons", ["#f0dcc2", "#b8834f", "#572e18"])
FORA = "#e8e8e5"
TEXTO = "#392c24"

# Os códigos DHS não são necessariamente os códigos ISO (por exemplo, NI = Níger).
ISO = dict(
    AO="AGO", BJ="BEN", BF="BFA", BU="BDI", CM="CMR", TD="TCD",
    KM="COM", CG="COG", CD="COD", CI="CIV", SZ="SWZ", ET="ETH",
    GA="GAB", GH="GHA", GN="GIN", GM="GMB", LS="LSO", LB="LBR",
    MD="MDG", MW="MWI", ML="MLI", MZ="MOZ", NM="NAM", NG="NGA",
    NI="NER", KE="KEN", CF="CAF", RW="RWA", SN="SEN", SL="SLE",
    SD="SDN", ST="STP", TZ="TZA", TG="TGO", ZW="ZWE", ZM="ZMB",
    ZA="ZAF",
)

SQL = """
SELECT p.codigo, p.nome, l.id AS levantamento_id, l.fase,
       MIN(e.ano) AS ano_inicial, MAX(e.ano) AS ano_final,
       COUNT(*) AS entrevistas
FROM Entrevista e
JOIN Mulher m ON m.id = e.mulher_id
JOIN Domicilio d ON d.id = m.domicilio_id
JOIN Levantamento l ON l.id = d.levantamento_id
JOIN Pais p ON p.codigo = l.pais_codigo
GROUP BY p.codigo, p.nome, l.id, l.fase
ORDER BY p.nome, l.id
"""


def projetar(lon, lat):
    """Lambert azimutal equivalente, centrada na África (20°E, 2°N)."""
    lam, phi = np.radians(lon), np.radians(lat)
    lam0, phi0 = np.radians(20), np.radians(2)
    k = np.sqrt(2 / (1 + np.sin(phi0) * np.sin(phi)
                     + np.cos(phi0) * np.cos(phi) * np.cos(lam - lam0)))
    x = k * np.cos(phi) * np.sin(lam - lam0)
    y = k * (np.cos(phi0) * np.sin(phi)
             - np.sin(phi0) * np.cos(phi) * np.cos(lam - lam0))
    return np.asarray(x) * 6371, np.asarray(y) * 6371


def desenhar_geometria(ax, geometria, cor):
    poligonos = (geometria["coordinates"] if geometria["type"] == "MultiPolygon"
                 else [geometria["coordinates"]])
    for poligono in poligonos:
        vertices, codigos = [], []
        for anel in poligono:
            pontos = np.array(anel)
            x, y = projetar(pontos[:, 0], pontos[:, 1])
            vertices.extend(zip(x, y))
            codigos.extend([MplPath.MOVETO] + [MplPath.LINETO] * (len(anel) - 2)
                           + [MplPath.CLOSEPOLY])
        ax.add_patch(PathPatch(MplPath(vertices, codigos), facecolor=cor,
                               edgecolor="white", linewidth=.65, zorder=2))


def main():
    db = RAIZ / "saude_mulher_normalizado.db"
    with sqlite3.connect(db.as_uri() + "?mode=ro", uri=True) as conn:
        periodos = pd.read_sql_query(SQL, conn)
        paises_db = {r[0] for r in conn.execute("SELECT codigo FROM Pais")}
        total, unicas = conn.execute("SELECT COUNT(*), COUNT(DISTINCT mulher_id) FROM Entrevista").fetchone()
        assert total == unicas == int(periodos.entrevistas.sum()), "Contagem de mulheres inconsistente."
    cobertura = periodos.groupby(["codigo", "nome"], as_index=False).agg(
        periodos=("levantamento_id", "nunique"), entrevistas=("entrevistas", "sum"))
    assert set(cobertura.codigo) == paises_db, "País do estudo sem cobertura de entrevistas."
    assert set(cobertura.codigo) <= ISO.keys(), "Código DHS sem correspondência cartográfica."
    cobertura["iso3"] = cobertura.codigo.map(ISO)
    geometria = json.loads((PASTA / "africa_natural_earth_50m.geojson").read_text(encoding="utf-8"))
    formas = {f["properties"]["ADM0_A3"]: f for f in geometria["features"]}
    assert set(cobertura.iso3) <= formas.keys(), "País do estudo ausente do mapa."
    assert (cobertura.entrevistas > 0).all(), "País sem mulheres pesquisadas."
    contagens = dict(zip(cobertura.iso3, cobertura.entrevistas))
    limite = math.ceil(cobertura.entrevistas.max() / 10000) * 10000
    escala = Normalize(vmin=0, vmax=limite)
    cobertura.to_csv(PASTA / "cobertura_por_pais.csv", index=False, encoding="utf-8-sig")
    periodos.to_csv(PASTA / "periodos_de_entrevista.csv", index=False, encoding="utf-8-sig")

    plt.rcParams.update({"font.family": "DejaVu Sans", "svg.fonttype": "none"})
    fig = plt.figure(figsize=(13, 13), facecolor="white")
    ax = fig.add_axes([.025, .16, .95, .69])
    for f in geometria["features"]:
        iso = f["properties"]["ADM0_A3"]
        cor = MARROM(escala(contagens[iso])) if iso in contagens else FORA
        desenhar_geometria(ax, f["geometry"], cor)

    # Posições geográficas de rótulos; linhas-guia nos países pequenos.
    rotulos = {
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
    externos = {
        "SN": (-22, 17.1), "GM": (-22.2, 13.7), "GN": (-19.8, 10.2),
        "SL": (-19, 6.8), "LB": (-16.4, 3.5), "CI": (-9, 1),
        "GH": (-3.5, -1.3), "TG": (1.3, -2.5), "BJ": (4.8, 15),
        "ST": (3.5, -7.2), "CG": (17.3, 1.9), "GA": (8, -5),
        "RW": (44, 1.5), "BU": (44, -3.3), "MW": (39, -12.6),
        "SZ": (39, -27), "LS": (35.8, -32.6), "KM": (49, -9.5),
        "MZ": (42, -22),
    }
    for row in cobertura.itertuples():
        lon, lat, nome = rotulos[row.codigo]
        xy = projetar(lon, lat)
        fora = row.codigo in externos
        destino = projetar(*externos[row.codigo]) if fora else xy
        preenchimento = MARROM(escala(row.entrevistas))
        brilho = sum(c * p for c, p in zip(preenchimento[:3], [.2126, .7152, .0722]))
        cor = TEXTO if fora or brilho > .56 else "white"
        label = f"{nome}\n{row.entrevistas:,}".replace(",", ".")
        if fora:
            ax.plot([xy[0], destino[0]], [xy[1], destino[1]], color="#9a8c80", lw=.65, zorder=3)
            ax.scatter(*xy, s=9, color=preenchimento, edgecolors="white", linewidths=.35, zorder=4)
        t = ax.text(*destino, label, ha="center", va="center", fontsize=7.8 if row.codigo == "BF" else 8.2,
                    color=cor, linespacing=1.15, zorder=5)
        if fora:
            t.set_path_effects([pe.withStroke(linewidth=3, foreground="white")])

    ax.set(xlim=(-4900, 3900), ylim=(-4200, 4450), aspect="equal")
    ax.axis("off")
    fig.text(.075, .94, "Países incluídos no estudo", fontsize=25, weight="bold", color=TEXTO)
    fig.text(.075, .905, "Número de mulheres pesquisadas por país", fontsize=14, color="#66584e")
    total_formatado = f"{total:,}".replace(",", ".")
    fig.text(.075, .872, f"{len(cobertura)} países  ·  {total_formatado} mulheres  ·  Quanto mais escuro, mais mulheres", fontsize=11, color="#66584e")
    cax = fig.add_axes([.18, .127, .48, .014])
    barra = fig.colorbar(ScalarMappable(norm=escala, cmap=MARROM), cax=cax, orientation="horizontal")
    barra.set_ticks(np.arange(0, limite + 1, 10000))
    barra.ax.xaxis.set_major_formatter(FuncFormatter(lambda x, _: f"{int(x):,}".replace(",", ".")))
    barra.ax.tick_params(labelsize=8, length=3, color="#80756c", labelcolor=TEXTO)
    barra.outline.set_visible(False)
    barra.set_label("Mulheres pesquisadas · escala linear", fontsize=9, color=TEXTO)
    fig.legend(handles=[Patch(facecolor=FORA, label="Fora do estudo")],
               loc="center", bbox_to_anchor=(.79, .133), frameon=False, fontsize=10,
               handlelength=1.8, handleheight=1.3, labelcolor=TEXTO)
    fig.text(.075, .075, "Contagem de mulheres com entrevista na base; valores absolutos, sem ponderação amostral.", fontsize=9, color="#66584e")
    fig.text(.075, .057, "Inclui todos os levantamentos do estudo e os suplementos de contracepção.", fontsize=9, color="#66584e")
    fig.text(.075, .032, "Fonte: saude_mulher_normalizado.db · Cartografia: Natural Earth 1:50m · Projeção equivalente de Lambert", fontsize=8, color="#80756c")
    for formato in ("png", "svg", "pdf"):
        fig.savefig(PASTA / f"mapa_mulheres_por_pais.{formato}", dpi=250, facecolor="white")
    plt.close(fig)
    print(f"Mapa validado: {len(cobertura)} países, {total_formatado} mulheres com entrevista, sem duplicação de mulher_id.")
    print(cobertura.sort_values("entrevistas", ascending=False)[["nome", "entrevistas"]].to_string(index=False))


if __name__ == "__main__":
    main()
