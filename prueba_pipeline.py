"""
prueba_pipeline.py — Verificación end-to-end (sin interfaz).

Descarga datos reales de las APIs, aplica las transformaciones de Pandas,
construye TODAS las figuras de Plotly y reporta el resultado.

Ejecutar:  python prueba_pipeline.py
"""
from __future__ import annotations

import traceback

import numpy as np
import pandas as pd

import analitica as A
import fuentes as F
import graficos as G

pd.set_option("display.width", 160)
pd.set_option("display.max_columns", 40)

fallos: list[str] = []
ok: list[str] = []


def _demo_evolucion():
    """Evolución de goles por jornada (para validar el gráfico de líneas)."""
    demo = pd.DataFrame({"ronda": np.tile(range(1, 6), 3),
                         "jugador": np.repeat(["A", "B", "C"], 5),
                         "goles": [1, 0, 2, 1, 0, 0, 1, 1, 0, 2, 2, 2, 1, 0, 1]})
    demo["acumulado"] = demo.groupby("jugador")["goles"].cumsum()
    return demo


def revisar(nombre: str, fn):
    try:
        valor = fn()
        ok.append(f"✅ {nombre}")
        return valor
    except Exception as exc:                                  # noqa: BLE001
        fallos.append(f"❌ {nombre}: {type(exc).__name__}: {exc}")
        traceback.print_exc()
        return None


print("=" * 78)
print("PRUEBA 1 · ⚽ FÚTBOL (Understat) — temporadas 2025 y 2026")
print("=" * 78)
res_ft = revisar("descarga fútbol EPL 2026", lambda: F.futbol_jugadores("EPL", "2026"))
res_ft25 = revisar("descarga fútbol EPL 2025", lambda: F.futbol_jugadores("EPL", "2025"))
res_bun = revisar("descarga Bundesliga 2025", lambda: F.futbol_jugadores("Bundesliga", "2025"))
if res_ft:
    ft = A.preparar_futbol(res_ft.df)
    print(f"\n   origen: {res_ft.origen} · {res_ft.hora} · {len(ft)} filas, {ft.shape[1]} columnas")
    print("\n   Top 6 goleadores:")
    print(ft.nlargest(6, "goles")[["jugador", "equipo", "posicion_grupo", "partidos", "minutos",
                                   "goles", "asistencias", "xG", "goles_menos_xg", "goles_90",
                                   "conversion_%"]].to_string(index=False))
    print("\n   Control de calidad:")
    print(f"     · Goles totales de la liga: {ft['goles'].sum():.0f}")
    print(f"     · Correlación goles–xG: {ft['goles'].corr(ft['xG']):.3f}")
    print(f"     · Nulos en métricas clave: "
          f"{ft[['goles','xG','goles_90','conversion_%']].isna().sum().to_dict()}")
    mejor = ft.loc[ft['goles_menos_xg'].idxmax()]
    print(f"     · Mayor sobre-rendimiento: {mejor['jugador']} "
          f"({mejor['goles']:.0f} goles vs {mejor['xG']:.1f} xG)")

if res_bun:
    bun = A.preparar_futbol(res_bun.df)
    try:
        res_of = F.bundesliga_goleadores("2025")
        cruz = res_of.df.merge(bun[["jugador", "goles", "xG"]], on="jugador", how="inner")
        print(f"\n   Contraste OpenLigaDB ↔ Understat (Bundesliga 2025): {len(cruz)} goleadores cruzados")
        print(cruz.nlargest(5, "goles_oficiales").to_string(index=False))
    except Exception as exc:                                  # noqa: BLE001
        fallos.append(f"❌ contraste Bundesliga: {exc}")

print("\n" + "=" * 78)
print("PRUEBA 2 · ⚾ BÉISBOL (MLB StatsAPI) — temporada 2026")
print("=" * 78)
res_bat = revisar("descarga MLB bateo 2026", lambda: F.mlb_jugadores(2026, "hitting"))
res_pit = revisar("descarga MLB pitcheo 2026", lambda: F.mlb_jugadores(2026, "pitching"))
if res_bat:
    bat = A.preparar_mlb_bateo(res_bat.df)
    print(f"\n   bateo: {res_bat.origen} · {res_bat.hora} · {len(bat)} jugadores, {bat.shape[1]} columnas")
    print(bat.nlargest(6, "HR")[["jugador", "equipo", "liga", "PJ", "AP", "AVG", "OBP", "SLG",
                                 "OPS", "HR", "CI", "BR", "K_%", "ISO"]].to_string(index=False))
    print(f"   · duplicados de jugador: {bat['jugador'].duplicated().sum()}")
if res_pit:
    pit = A.preparar_mlb_pitcheo(res_pit.df)
    print(f"\n   pitcheo: {res_pit.origen} · {len(pit)} lanzadores")
    print(pit[pit["IP"] >= 60].nsmallest(6, "ERA")[
        ["jugador", "equipo", "IP", "ERA", "WHIP", "W", "K", "K/9", "BB/9", "FIP_aprox"]
    ].to_string(index=False))
try:
    lid = F.mlb_lideres(2026, "hitting", 5)
    print(f"\n   líderes oficiales por categoría ({lid.origen}):")
    print(lid.df.groupby("categoria").head(3).to_string(index=False))
except Exception as exc:                                      # noqa: BLE001
    fallos.append(f"❌ líderes MLB: {exc}")

print("\n" + "=" * 78)
print("PRUEBA 3 · 🏎️ FÓRMULA 1 (Jolpica) — 2026 y 2025")
print("=" * 78)
tabla_pil = None
res_f1 = revisar("descarga resultados F1 2026", lambda: F.f1_resultados(2026))
res_std = revisar("descarga standings F1 2026", lambda: F.f1_standings(2026))
if res_f1 and res_std:
    std, acum = A.preparar_f1_resultados(res_f1.df)
    print(f"\n   {res_f1.origen} · {res_f1.hora} · {len(std)} resultados en "
          f"{std['ronda'].nunique()} rondas")
    print(f"   · acumulado: {len(acum)} filas (piloto × ronda)")
    agg = (std.groupby(["code", "piloto", "equipo"])
             .agg(carreras=("ronda", "count"), victorias=("gano", "sum"),
                  podios=("podio", "sum"), top10=("top10", "sum"),
                  retiros=("termino", lambda s: int((s == 0).sum())),
                  pos_media=("posicion", "mean"), parrilla_media=("parrilla", "mean"),
                  ganancia_puestos=("puestos_ganados", "mean"),
                  mejor_resultado=("posicion", "min")).reset_index())
    tabla_pil = res_std.df.merge(agg.drop(columns=["victorias", "equipo"]),
                                 on=["code", "piloto"], how="outer")
    tabla_pil["puntos_por_carrera"] = tabla_pil["puntos"] / tabla_pil["carreras"]
    tabla_pil["consistencia"] = 100 - tabla_pil["retiros"].fillna(0) / tabla_pil["carreras"] * 100
    print("\n   Top 8 del campeonato:")
    print(tabla_pil.sort_values("puntos", ascending=False).head(8)[
        ["posicion_final", "piloto", "equipo", "puntos", "victorias", "podios", "retiros",
         "pos_media", "parrilla_media", "ganancia_puestos", "puntos_por_carrera", "consistencia"]
    ].to_string(index=False))
    print(f"   · puntos totales repartidos: {std['puntos'].sum():.0f} "
          f"| suma de standings: {tabla_pil['puntos'].sum():.0f}")
    print(f"   · victorias en resultados: {int(std['gano'].sum())} "
          f"| en standings: {int(tabla_pil['victorias'].sum())}")
try:
    cal = F.f1_calendario(2026)
    print(f"\n   calendario 2026: {len(cal)} carreras · última: {cal.iloc[-1]['carrera']} ({cal.iloc[-1]['fecha']})")
except Exception as exc:                                      # noqa: BLE001
    fallos.append(f"❌ calendario F1: {exc}")

print("\n" + "=" * 78)
print("PRUEBA 4 · 📊 FIGURAS DE PLOTLY (se construyen todas las del dashboard)")
print("=" * 78)
if res_ft:
    ft = A.preparar_futbol(res_ft.df)
    d = ft[ft["minutos"] >= max(1, int(ft["minutos"].max() * 0.4))]
    ruta = "/tmp/figs_futbol.html"
    figs = {
        "barras_top": G.barras_top(d, "jugador", "goles", "Top goleadores", 15),
        "burbujas": G.burbujas(d, "xG", "goles", "tiros", "xg_90", ["jugador", "equipo", "minutos"],
                              "Goles vs xG"),
        "box": G.box_por_grupo(d, "posicion_grupo", "g+a_90", "Producción por posición"),
        "divergentes": G.barras_divergentes(d, "jugador", "goles_menos_xg", "Goles − xG"),
        "radar": G.radar(["Goles/90", "Asist/90", "xG/90", "xA/90", "Tiros/90", "Pases/90"],
                         [d["pct_goles_90"].head(3).tolist(), d["pct_asist_90"].head(3).tolist(),
                          d["pct_xg_90"].head(3).tolist(), d["pct_xa_90"].head(3).tolist(),
                          d["pct_tiros_90"].head(3).tolist(), d["pct_pases_clave_90"].head(3).tolist()],
                         ["A", "B", "C"]),
        "heatmap": G.heatmap_correlacion(A.matriz_correlacion(d, ["goles", "xG", "tiros", "xA", "pases_clave"])),
        "histograma": G.histograma(d, "goles", "Distribución de goles", color="posicion_grupo"),
        "dona": G.dona(d.groupby("equipo", as_index=False)["goles"].sum().nlargest(10, "goles"),
                       "equipo", "goles", "Goles por equipo"),
        "lineas": G.lineas_acumuladas(_demo_evolucion(), "ronda", "acumulado", "jugador",
                                      "Evolución acumulada (demo)"),
        "tabla_heatmap": G.tabla_heatmap_puntos(d.head(8), "jugador", ["pct_goles_90", "pct_xg_90"]),
        "apiladas": G.barras_apiladas(d.head(5), "jugador", "goles", "posicion_grupo", "Apiladas"),
        "dispersion": G.dispersion_simple(d, "minutos", "goles", "posicion_grupo", "Dispersión"),
        "caja_evolucion": G.caja_evolucion(d, "posicion_grupo", "goles", "equipo", "Cajas"),
        "heatmap_pistas": G.heatmap_pistas(d.head(20), "posicion_grupo", "equipo", "goles", "Pistas"),
        "linea_tendencia": G.linea_tendencia(d.head(30).sort_values("minutos"),
                                             "minutos", "goles", "Tendencia", 5),
        "agrupadas": G.barras_agrupadas(d.head(6).melt(id_vars=["jugador"],
                                                       value_vars=["goles", "asistencias"]),
                                        "jugador", "value", "variable", "Agrupadas"),
    }
    for nombre, fig in figs.items():
        revisar(f"figura fútbol: {nombre}", lambda f=fig: len(f.to_html(include_plotlyjs="cdn")) > 100)
    with open(ruta, "w", encoding="utf-8") as fh:      # muestra combinada para revisar
        fh.write("<h2>Figuras de prueba — fútbol</h2>")
        for nombre, fig in figs.items():
            fh.write(f"<h3>{nombre}</h3>" + fig.to_html(include_plotlyjs="cdn", full_html=False))
    print(f"   → muestra de figuras guardada en {ruta}")

if res_bat:
    bat = A.preparar_mlb_bateo(res_bat.df)
    d = bat[bat["AP"] >= 100]
    revisar("figura MLB: barras top AVG (ascendente ERA)",
            lambda: G.barras_top(A.preparar_mlb_pitcheo(res_pit.df), "jugador", "ERA",
                                 "Mejor ERA", 12, ascendente=True))
    for nombre, fn in {
        "barras": lambda: G.barras_top(d, "jugador", "HR", "Jonrones", 15, color="liga"),
        "burbujas": lambda: G.burbujas(d, "AVG", "HR", "AP", "OPS", ["jugador", "equipo"], "AVG vs HR"),
    }.items():
        revisar(f"figura MLB: {nombre}", fn)

if res_f1:
    std, acum = A.preparar_f1_resultados(res_f1.df)
    lideres = tabla_pil.nlargest(8, "puntos")["code"].tolist()
    for nombre, fn in {
        "lineas_acumuladas": lambda: G.lineas_acumuladas(acum[acum["code"].isin(lideres)],
                                                         "ronda", "puntos_acumulados", "piloto", "Evolución"),
        "heatmap_pistas": lambda: G.heatmap_pistas(std[std["code"].isin(lideres)],
                                                   "piloto", "ronda", "posicion", "Posiciones"),
        "barras puntos": lambda: G.barras_top(tabla_pil, "piloto", "puntos", "Puntos", 20, color="equipo"),
    }.items():
        revisar(f"figura F1: {nombre}", fn)

print("\n" + "=" * 78)
print("RESULTADO FINAL")
print("=" * 78)
print(f"Pruebas exitosas: {len(ok)}")
for o in ok:
    print("  " + o)
if fallos:
    print(f"\nFallos: {len(fallos)}")
    for f_ in fallos:
        print("  " + f_)
else:
    print("\n🎉 Todo el pipeline funciona con datos reales.")
print("\nArchivos en caché local:")
for p in sorted(F.DIR_CACHE.glob("*.parquet")):
    df = pd.read_parquet(p)
    print(f"  · {p.name:<38} {len(df):>6} filas × {df.shape[1]:>3} columnas")
