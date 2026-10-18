"""
⚽🏎️⚾🏀  Dashboard interactivo de estadísticas de jugadores
============================================================
App Streamlit que consume APIs deportivas públicas (multideporte), procesa todo
con Pandas y visualiza con Plotly.

Ejecutar:   streamlit run app.py
"""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd
import streamlit as st

import analitica as A
import fuentes as F
import graficos as G

# ---------------------------------------------------------------------------
# Configuración de página y estilos
# ---------------------------------------------------------------------------
st.set_page_config(page_title="Dashboard de Jugadores", page_icon="📊",
                   layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
  .block-container {padding-top: 1.6rem; padding-bottom: 2rem;}
  h1, h2, h3 {letter-spacing: -0.4px;}
  [data-testid="stMetric"] {border: 1px solid rgba(128,128,128,.28);
      border-radius: 12px; padding: 12px 14px; background: rgba(128,128,128,.06);}
  [data-testid="stMetricValue"] {font-size: 1.55rem;}
  .ficha {border: 1px solid rgba(128,128,128,.28); border-radius: 12px;
      padding: 10px 14px; background: rgba(128,128,128,.06); font-size: .84rem; line-height: 1.55;}
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Helpers de UI
# ---------------------------------------------------------------------------
# La API de ancho cambió en Streamlit 1.50 (use_container_width -> width="stretch")
_VERSION = tuple(int(x) for x in st.__version__.split(".")[:2])
_ANCHO_ESTIRADO = ({"width": "stretch"} if _VERSION >= (1, 50)
                   else {"use_container_width": True})


def mostrar(fig, key: str | None = None):
    st.plotly_chart(fig, theme=None, key=key, **_ANCHO_ESTIRADO)


def ficha_fuente(res: F.Resultado, detalle: str = ""):
    """Muestra de dónde salieron los datos con color según procedencia."""
    color = {"API en vivo": "🟢", "caché local": "🟡", "respaldo offline": "🟠"}.get(res.origen, "⚪")
    st.caption(f"{color} **{res.origen}** · descargado: {res.hora} · {len(res.df):,} filas · {detalle}")
    if res.mensaje:
        st.warning(res.mensaje)


def descargar(df: pd.DataFrame, nombre: str, etiqueta: str = "⬇️ Descargar CSV"):
    st.download_button(etiqueta, df.to_csv(index=False).encode("utf-8"),
                       file_name=f"{nombre}_{dt.date.today()}.csv", mime="text/csv")


def tabla(df: pd.DataFrame, altura: int | None = None, **kw):
    args = dict(hide_index=True, **_ANCHO_ESTIRADO, **kw)
    if altura:                       # height=None es inválido en Streamlit >= 1.5x
        args["height"] = int(altura)
    st.dataframe(df, **args)


def percentiles_por_grupo(df: pd.DataFrame, cols: list[str], grupo: str,
                          prefijo: str = "pg_") -> pd.DataFrame:
    """Percentiles calculados DENTRO de cada grupo (posición, liga, etc.)."""
    salida = df.copy()
    for c in cols:
        if c in df.columns:
            salida[prefijo + c] = (df.groupby(grupo)[c].rank(pct=True) * 100).round(1)
    return salida


def aviso_sin_datos(texto: str, icono: str = "🔍"):
    st.info(f"{icono} {texto}")


# ===========================================================================
# SECCIÓN 1 · ⚽ FÚTBOL
# ===========================================================================
def render_futbol(forzar: bool):
    st.subheader("⚽ Estadísticas ofensivas de jugadores — fútbol europeo")
    st.caption("Goles, asistencias y **goles esperados (xG/xA)** por jugador. "
               "Fuente: Understat (tiros y calidad de ocasión).")

    c1, c2, _ = st.columns([1.3, 1, 1])
    liga_nom = c1.selectbox("Liga", list(F.LIGAS_FUTBOL), key="ft_liga")
    liga = F.LIGAS_FUTBOL[liga_nom]
    temp_nom = c2.selectbox("Temporada", list(F.TEMPORADAS_FUTBOL), key="ft_temp")
    temporada = F.TEMPORADAS_FUTBOL[temp_nom]

    with st.spinner("Consultando Understat…"):
        try:
            res = F.futbol_jugadores(liga, temporada, forzar=forzar)
        except Exception as exc:                              # noqa: BLE001
            st.error(f"No se pudo cargar la liga: {exc}")
            return
    df = A.preparar_futbol(res.df)
    ficha_fuente(res, f"{liga_nom} · temporada {temp_nom}")

    # ---- Filtros (cuerpo) ----
    f1, f2, f3, f4 = st.columns([1.5, 1, 1, 1.2])
    equipos = f1.multiselect("Filtrar equipos", sorted(df["equipo"].dropna().unique()),
                             placeholder="Todos")
    posiciones = f2.multiselect("Posición", sorted(df["posicion_grupo"].unique()),
                                placeholder="Todas")
    ordenar = f3.selectbox("Ordenar ranking por", ["goles", "asistencias", "xG", "xA",
                                                   "goles+asist", "g+a_90", "tiros", "pases_clave"])
    # El umbral se adapta a la temporada: en ligas recién iniciadas no hay 600 minutos jugados
    max_min = max(90, int(df["minutos"].max() or 90))
    sugerido = 600 if max_min >= 1500 else int(round(max_min * 0.4 / 90.0) * 90)
    minimo = f4.slider("Minutos mínimos", 0, max_min, min(sugerido, max_min), step=90,
                       key="ft_min", help=f"Máximo posible en esta liga/temporada: {max_min} min")
    st.caption(f"⏱️ La temporada seleccionada tiene {int(df['partidos'].max())} jornadas disputadas "
               f"(máximo de {max_min} minutos por jugador).")
    d = df[df["minutos"] >= minimo]
    if equipos:
        d = d[d["equipo"].isin(equipos)]
    if posiciones:
        d = d[d["posicion_grupo"].isin(posiciones)]
    if d.empty:
        aviso_sin_datos("Ningún jugador cumple los filtros. Baja el umbral de minutos.")
        return

    # ---- KPIs ----
    k1, k2, k3, k4 = st.columns(4)
    goleador = d.loc[d["goles"].idxmax()]
    mejor_xg = d.loc[d["xG"].idxmax()]
    sorpresa = d.loc[d["goles_menos_xg"].idxmax()]
    asistidor = d.loc[d["asistencias"].idxmax()]
    k1.metric("🥇 Máximo goleador", goleador["jugador"], f"{goleador['goles']:.0f} goles")
    k2.metric("🎯 Mayor xG", mejor_xg["jugador"], f"{mejor_xg['xG']:.1f} xG")
    k3.metric("📈 Mejor sobre-rendimiento", sorpresa["jugador"],
              f"{sorpresa['goles_menos_xg']:+.1f} vs xG")
    k4.metric("🅰️ Más asistencias", asistidor["jugador"], f"{asistidor['asistencias']:.0f} asistencias")

    tab1, tab2, tab3, tab4 = st.tabs(["🏆 Rankings", "🔍 Comparador", "🧠 Explorador",
                                      "🗂️ Datos y descarga"])

    # -------- Rankings --------
    with tab1:
        cs, ct = st.columns([1, 2])
        top = cs.slider("Tamaño del ranking", 5, 30, 15, key="ft_top")
        etiquetas_scatter = ct.toggle("Mostrar nombres en los gráficos de dispersión",
                                      value=False, key="ft_etiquetas",
                                      help="Recomendado solo si hay pocos jugadores (máx. 70).")
        col1, col2 = st.columns(2)
        etiqueta_orden = {"goles": "Goles", "asistencias": "Asistencias", "xG": "xG",
                          "xA": "xA", "goles+asist": "Goles + asistencias",
                          "g+a_90": "G+A por 90 min", "tiros": "Tiros",
                          "pases_clave": "Pases clave"}[ordenar]
        with col1:
            mostrar(G.barras_top(d, "jugador", ordenar, f"Top {top} · {etiqueta_orden}", top),
                    key="ft_bar_top")
        with col2:
            mostrar(G.burbujas(d, "xG", "goles", "tiros", "xg_90",
                               ["jugador", "equipo", "minutos", "asistencias"],
                               "Goles vs. xG — tamaño = tiros, color = xG/90", alto=460,
                               etiquetas=etiquetas_scatter), key="ft_scatter_goles")

        st.markdown("##### Eficiencia por posición (distribución de G+A por 90 minutos)")
        mostrar(G.box_por_grupo(d, "posicion_grupo", "g+a_90",
                                "Producción por posición", alto=430), key="ft_box")

        st.markdown("##### Sobre/sub-rendimiento: goles − xG (quién define por encima de lo esperado)")
        mostrar(G.barras_divergentes(d, "jugador", "goles_menos_xg",
                                     "Diferencia goles − xG", top=12), key="ft_div")

        st.markdown("##### Tabla de líderes")
        cols_tabla = ["jugador", "equipo", "posicion", "partidos", "minutos", "goles",
                      "asistencias", "goles+asist", "xG", "xA", "goles_menos_xg",
                      "conversion_%", "tiros", "pases_clave", "goles_90", "g+a_90"]
        tabla(d.nlargest(top, ordenar)[[c for c in cols_tabla if c in d.columns]]
              .style.format({"conversion_%": "{:.1f}", "goles_menos_xg": "{:+.1f}",
                             "goles_90": "{:.2f}", "g+a_90": "{:.2f}", "xG": "{:.1f}",
                             "xA": "{:.1f}"}, na_rep="—"))

    # -------- Comparador --------
    with tab2:
        st.markdown("Elige entre 2 y 5 jugadores para comparar su perfil ofensivo.")
        candidatos = d.nlargest(120, "minutos")
        base = candidatos.rename(columns={"jugador": "Jugador"})
        seleccion = st.multiselect("Jugadores",
                                   options=base["Jugador"].tolist(),
                                   default=base["Jugador"].head(3).tolist(), key="ft_comp")
        if len(seleccion) < 2:
            aviso_sin_datos("Selecciona al menos 2 jugadores.", "🧩")
        else:
            sub = candidatos[candidatos["jugador"].isin(seleccion)].copy()
            metr = ["goles", "asistencias", "goles+asist", "xG", "xA", "tiros",
                    "pases_clave", "goles_90", "g+a_90", "conversion_%", "goles_menos_xg"]
            comparacion = A.tabla_comparacion(sub, "jugador", seleccion, metr)
            cc1, cc2 = st.columns([1, 1])
            with cc1:
                st.markdown("##### Números absolutos")
                tabla(comparacion.rename_axis("Métrica"), altura=min(140 + 38 * len(metr), 700))
                descargar(comparacion, "comparacion_futbol", "⬇️ Descargar comparación")
            with cc2:
                st.markdown("##### Perfil (percentiles dentro de la liga filtrada)")
                metr_pct = ["goles_90", "asist_90", "xg_90", "xa_90", "tiros_90", "pases_clave_90"]
                etiquetas = ["Goles/90", "Asist/90", "xG/90", "xA/90", "Tiros/90", "Pases clave/90"]
                valores = [sub.set_index("jugador")[m].reindex(seleccion).tolist() for m in metr_pct]
                mostrar(G.radar(etiquetas, valores, seleccion,
                                "Radar de percentiles (0-100)"), key="ft_radar")
            st.markdown("##### Producción por 90 minutos")
            mostrar(G.barras_agrupadas(sub.melt(id_vars=["jugador"],
                                                value_vars=["goles_90", "asist_90", "xg_90"]),
                                       "jugador", "value", "variable",
                                       "Goles, asistencias y xG por 90 minutos", alto=420),
                    key="ft_agrup")

    # -------- Explorador --------
    with tab3:
        st.markdown("Explora relaciones entre métricas y detecta qué tan bien "
                    "los **goles esperados** explican los goles reales.")
        e1, e2, e3, e4 = st.columns(4)
        ejes = [c for c in ["goles", "asistencias", "xG", "xA", "tiros", "pases_clave",
                            "minutos", "goles_90", "g+a_90", "conversion_%"] if c in d.columns]
        x = e1.selectbox("Eje X", ejes, index=2, key="ft_ex")
        y = e2.selectbox("Eje Y", ejes, index=0, key="ft_ey")
        tam = e3.selectbox("Tamaño de burbuja", ["minutos", "tiros", "pases_clave", "partidos"], key="ft_et")
        col = e4.selectbox("Color", ["posicion_grupo", "xg_90", "g+a_90", "conversion_%"], key="ft_ec")
        mostrar(G.burbujas(d, x, y, tam, col, ["jugador", "equipo", "goles", "xG", "minutos"],
                           f"{y} vs. {x}", alto=520,
                           etiquetas=st.toggle("Mostrar nombres", value=False, key="ft_exp_et")),
                key="ft_ex_scatter")

        c1, c2 = st.columns([1.2, 1])
        with c1:
            st.markdown("##### Matriz de correlación (métricas ofensivas)")
            corr = A.matriz_correlacion(d, ["goles", "asistencias", "xG", "xA", "tiros",
                                            "pases_clave", "minutos", "goles_90", "g+a_90"])
            mostrar(G.heatmap_correlacion(corr, "Coeficiente de Pearson", alto=520), key="ft_corr")
        with c2:
            st.markdown("##### Distribución de la métrica elegida")
            metrica_hist = st.selectbox("Métrica", ejes, index=0, key="ft_hist")
            mostrar(G.histograma(d, metrica_hist, f"Histograma de {metrica_hist}",
                                 alto=430, color="posicion_grupo"), key="ft_hist_fig")
            st.markdown("##### Reparto de goles por equipo (top 10)")
            por_equipo = (d.groupby("equipo", as_index=False)["goles"].sum()
                            .nlargest(10, "goles"))
            mostrar(G.dona(por_equipo, "equipo", "goles", "Goles acumulados", alto=380),
                    key="ft_dona")

    # -------- Datos --------
    with tab4:
        st.markdown("##### Dataset completo (listo para exportar a Excel / Parquet)")
        st.caption("Tipos de datos y valores nulos: " +
                   f"**{int(df.isna().sum().sum())}** celdas vacías en {df.shape[1]} columnas.")
        tabla(d.drop(columns=[c for c in d.columns if c.startswith("pct_")])
              .sort_values(ordenar, ascending=False), altura=520)
        descargar(d, f"futbol_{liga}_{temporada}", "⬇️ Descargar dataset filtrado")
        with st.expander("🗺️ Diccionario de variables"):
            st.markdown("""
| Variable | Significado |
|---|---|
| `goles`, `asistencias` | Totales de la temporada |
| `xG` / `xA` | Goles/asistencias **esperados** según calidad de las ocasiones |
| `goles_menos_xg` | > 0 = define mejor de lo esperado; < 0 = desperdicia ocasiones |
| `goles_90`, `asist_90`, `xa_90` | Métricas normalizadas por 90 minutos jugados |
| `conversion_%` | Goles ÷ tiros × 100 |
| `posicion_grupo` | Agrupación: Arquero / Defensa / Mediocampista / Delantero |
| `pct_*` | Percentil (0–100) del jugador dentro de la liga cargada |
""")
        if liga == "Bundesliga":
            st.markdown("##### Contraste con la fuente oficial de la Bundesliga (OpenLigaDB)")
            try:
                res_of = F.bundesliga_goleadores(temporada, forzar=forzar)
                contraste = (res_of.df.merge(df[["jugador", "goles", "xG"]], on="jugador", how="inner")
                             .assign(diferencia=lambda t: t["goles_oficiales"] - t["goles"])
                             .sort_values("goles_oficiales", ascending=False).head(15))
                tabla(contraste)
            except Exception as exc:                          # noqa: BLE001
                st.caption(f"(No se pudo cargar el contraste: {exc})")


# ===========================================================================
# SECCIÓN 2 · ⚾ BÉISBOL MLB
# ===========================================================================
def render_mlb(forzar: bool):
    st.subheader("⚾ Estadísticas de jugadores — MLB")
    st.caption("Estadísticas oficiales de la **MLB StatsAPI**: bateo y pitcheo. "
               "Métricas derivadas (ISO, BABIP, K%, FIP) calculadas con Pandas.")

    c1, c2, c3 = st.columns(3)
    temporada = c1.selectbox("Temporada", list(range(dt.date.today().year, 2019, -1)), key="mlb_temp")
    grupo = c2.radio("Grupo de estadísticas", ["Bateo (hitting)", "Pitcheo (pitching)"],
                     horizontal=True, key="mlb_grupo")
    grupo_api = "hitting" if grupo.startswith("Bateo") else "pitching"
    minimo = c3.slider("Umbral mínimo de participación", 0, 400,
                       100 if grupo_api == "hitting" else 40,
                       step=10, help="Turnos al bate (bateo) o innings lanzados (pitcheo)",
                       key="mlb_min")

    with st.spinner("Consultando MLB StatsAPI…"):
        try:
            res = F.mlb_jugadores(temporada, grupo_api, forzar=forzar)
        except Exception as exc:                              # noqa: BLE001
            st.error(f"No se pudo cargar MLB: {exc}")
            return

    if grupo_api == "hitting":
        df = A.preparar_mlb_bateo(res.df)
        d = df[df["AP"].fillna(0) >= minimo]
        ficha_fuente(res, f"temporada {temporada} · bateadores con ≥ {minimo} apariciones al plato")
    else:
        df = A.preparar_mlb_pitcheo(res.df)
        d = df[df["IP"].fillna(0) >= minimo]
        ficha_fuente(res, f"temporada {temporada} · pitchers con ≥ {minimo} innings lanzados")

    if d.empty:
        aviso_sin_datos("Ningún jugador cumple el umbral. Redúcelo.")
        return

    ligas = st.multiselect("Liga", sorted(d["liga"].dropna().unique()), placeholder="Ambas (AL y NL)")

    # ---- KPIs del primer líder de cada uno ----
    if grupo_api == "hitting":
        lider_hr = d.loc[d["HR"].idxmax()]
        lider_avg = d[d["AP"] >= 250].loc[d[d["AP"] >= 250]["AVG"].idxmax()] if (d["AP"] >= 250).any() else d.loc[d["AVG"].idxmax()]
        lider_ops = d[d["AP"] >= 250].loc[d[d["AP"] >= 250]["OPS"].idxmax()] if (d["AP"] >= 250).any() else d.loc[d["OPS"].idxmax()]
        lider_br = d.loc[d["BR"].idxmax()]
        k = st.columns(4)
        k[0].metric("💥 Líder en jonrones", lider_hr["jugador"], f"{lider_hr['HR']:.0f} HR")
        k[1].metric("🏏 Mejor AVG", lider_avg["jugador"], f"{lider_avg['AVG']:.3f}")
        k[2].metric("⭐ Mejor OPS", lider_ops["jugador"], f"{lider_ops['OPS']:.3f}")
        k[3].metric("🏃 Líder en robos", lider_br["jugador"], f"{lider_br['BR']:.0f} SB")
    else:
        pool = d[d["IP"] >= 60]
        k = st.columns(4)
        k[0].metric("🔥 Mejor ERA", pool.loc[pool["ERA"].idxmin()]["jugador"],
                    f"{pool['ERA'].min():.2f}")
        k[1].metric("🎯 Líder en ponches", d.loc[d["K"].idxmax()]["jugador"],
                    f"{d['K'].max():.0f} K")
        k[2].metric("🥇 Más victorias", d.loc[d["W"].idxmax()]["jugador"],
                    f"{d['W'].max():.0f} W")
        k[3].metric("🧱 Mejor WHIP", pool.loc[pool["WHIP"].idxmin()]["jugador"],
                    f"{pool['WHIP'].min():.2f}")

    tab1, tab2, tab3, tab4 = st.tabs(["🏆 Rankings", "🔍 Comparador", "🧠 Explorador", "🗂️ Datos y descarga"])

    with tab1:
        if grupo_api == "hitting":
            metricas = {"HR": "Jonrones", "OPS": "OPS", "AVG": "Promedio de bateo",
                        "CI": "Carreras impulsadas", "BR": "Bases robadas", "H": "Hits",
                        "ISO": "Poder aislado (ISO)", "HR_600": "HR por 600 apariciones"}
        else:
            metricas = {"ERA": "ERA (menor es mejor)", "K": "Ponches", "W": "Victorias",
                        "WHIP": "WHIP (menor es mejor)", "K/9": "Ponches por 9 innings",
                        "SV": "Salvamentos", "FIP_aprox": "FIP aproximado"}
        m1, m2 = st.columns([1, 1])
        metrica = m1.selectbox("Métrica del ranking", list(metricas), key="mlb_met")
        n_top = m2.slider("Tamaño", 5, 30, 15, key="mlb_top")
        menor_mejor = metrica in ("ERA", "WHIP")
        datos_eje = d.sort_values(metrica, ascending=menor_mejor).head(n_top)

        c1, c2 = st.columns(2)
        with c1:
            mostrar(G.barras_top(d, "jugador", metrica, f"Top {n_top} · {metricas[metrica]}",
                                 n_top, color="liga", ascendente=menor_mejor),
                    key="mlb_bar")
        with c2:
            if grupo_api == "hitting":
                mostrar(G.burbujas(d, "AVG", "HR", "AP", "OPS",
                                   ["jugador", "equipo", "OPS", "CI"],
                                   "Jonrones vs. promedio — tamaño = apariciones, color = OPS",
                                   alto=460), key="mlb_scatter")
            else:
                mostrar(G.burbujas(d[d["IP"] >= 20], "K/9", "ERA", "IP", "WHIP",
                                   ["jugador", "equipo", "WHIP", "K"],
                                   "Ponches/9 vs. ERA — tamaño = innings, color = WHIP",
                                   alto=460), key="mlb_scatter_p")

        if grupo_api == "hitting":
            st.markdown("##### Distribución del OPS por equipo (top 8 con más jugadores)")
            equipos_top = d["equipo"].value_counts().head(8).index
            mostrar(G.box_por_grupo(d[d["equipo"].isin(equipos_top)], "equipo", "OPS",
                                    "OPS por equipo", alto=470), key="mlb_box")
        else:
            st.markdown("##### Relación ERA ↔ WHIP (los mejores pitchers arriba-izquierda)")
            mostrar(G.dispersion_simple(d[d["IP"] >= 40], "WHIP", "ERA", "liga",
                                        "ERA vs WHIP", alto=470), key="mlb_disp")

        st.markdown("##### Tabla de líderes")
        cols = (["jugador", "equipo", "liga", "posicion", "PJ", "AP", "AVG", "OBP", "SLG",
                 "OPS", "H", "HR", "CI", "C", "BR", "BB", "K", "K_%", "BB_%", "ISO", "HR_600"]
                if grupo_api == "hitting" else
                ["jugador", "equipo", "liga", "PJ", "GS", "IP", "ERA", "WHIP", "W", "L", "SV",
                 "K", "BB", "K/9", "BB/9", "HR/9", "K-BB", "FIP_aprox"])
        tabla(datos_eje[[c for c in cols if c in datos_eje.columns]]
              .style.format({"AVG": "{:.3f}", "OBP": "{:.3f}", "SLG": "{:.3f}", "OPS": "{:.3f}",
                             "ERA": "{:.2f}", "WHIP": "{:.2f}", "K/9": "{:.1f}", "BB/9": "{:.1f}",
                             "HR/9": "{:.2f}", "K-BB": "{:.1f}", "ISO": "{:.3f}",
                             "K_%": "{:.1f}", "BB_%": "{:.1f}", "FIP_aprox": "{:.2f}",
                             "HR_600": "{:.1f}", "IP": "{:.1f}"}, na_rep="—"))

    with tab2:
        umbral_comp = d[d["AP"] >= 200] if grupo_api == "hitting" else d[d["IP"] >= 50]
        pool = umbral_comp if len(umbral_comp) > 5 else d
        seleccion = st.multiselect("Jugadores (2 a 6)", pool["jugador"].tolist(),
                                   default=pool.nlargest(3, "K" if grupo_api == "pitching" else "HR")["jugador"].tolist(),
                                   key="mlb_comp")
        if len(seleccion) < 2:
            aviso_sin_datos("Selecciona al menos 2 jugadores.", "🧩")
        else:
            sub = pool[pool["jugador"].isin(seleccion)]
            if grupo_api == "hitting":
                metr = ["PJ", "AP", "AVG", "OBP", "SLG", "OPS", "HR", "CI", "BR", "K_%", "BB_%", "ISO"]
                pct_cols = ["AVG", "OBP", "SLG", "OPS", "HR_600", "BR", "BB_%"]
                etiquetas = ["AVG", "OBP", "SLG", "OPS", "HR/600", "Robos", "BB%"]
            else:
                metr = ["PJ", "GS", "IP", "ERA", "WHIP", "W", "SV", "K", "K/9", "BB/9", "K-BB"]
                pct_cols = ["ERA", "WHIP", "K/9", "BB/9", "K-BB"]
                etiquetas = ["ERA↓", "WHIP↓", "K/9", "BB/9↓", "K−BB"]
            sub_pct = percentiles_por_grupo(pool, pct_cols, "liga")
            sub_pct = sub_pct[sub_pct["jugador"].isin(seleccion)]
            c1, c2 = st.columns([1, 1.1])
            with c1:
                st.markdown("##### Comparación directa")
                comp = A.tabla_comparacion(sub, "jugador", seleccion,
                                           [c for c in metr if c in sub.columns])
                tabla(comp.rename_axis("Métrica"), altura=min(140 + 40 * len(metr), 760))
                descargar(comp, f"comparacion_mlb_{grupo_api}")
            with c2:
                st.markdown("##### Perfil vs. el resto de la liga (percentiles)")
                vals = []
                for col_db, inverso in zip(["pg_" + c for c in pct_cols],
                                           [False] * len(pct_cols)):
                    serie = sub_pct.set_index("jugador")[col_db].reindex(seleccion)
                    if col_db.endswith(("ERA", "WHIP", "BB/9")):
                        serie = 100 - serie            # invertimos: menor ERA = mejor
                    vals.append(serie.tolist())
                mostrar(G.radar(etiquetas, vals, seleccion, "Radar (100 = élite)"), key="mlb_radar")
            st.markdown("##### Distribución de la métrica clave por jugador")
            metrica_clave = "OPS" if grupo_api == "hitting" else "ERA"
            st.caption("Comparación de barras con el promedio de la liga como referencia.")
            prom_liga = pd.to_numeric(pool[metrica_clave], errors="coerce").mean()
            st.markdown(f"Promedio de la liga ({metrica_clave}): **{prom_liga:.3f}**"
                        if grupo_api == "hitting" else
                        f"Promedio de la liga ({metrica_clave}): **{prom_liga:.2f}**")
            mostrar(G.barras_agrupadas(sub.melt(id_vars=["jugador"], value_vars=[metrica_clave]),
                                       "jugador", "value", "variable",
                                       f"{metrica_clave} comparado", alto=380), key="mlb_comp_bar")

    with tab3:
        if grupo_api == "hitting":
            ejes = ["AVG", "OBP", "SLG", "OPS", "HR", "CI", "BR", "K_%", "BB_%", "ISO", "HR_600", "AP"]
        else:
            ejes = ["ERA", "WHIP", "K/9", "BB/9", "HR/9", "K-BB", "IP", "W", "SV", "K"]
        e1, e2, e3, e4 = st.columns(4)
        x = e1.selectbox("Eje X", ejes, index=0, key="mlb_ex")
        y = e2.selectbox("Eje Y", ejes, index=min(3, len(ejes) - 1), key="mlb_ey")
        tam = e3.selectbox("Tamaño", ["AP", "IP", "PJ", "H"], key="mlb_et")
        col = e4.selectbox("Color", ["liga", "posicion", "equipo"] + ejes, key="mlb_ec")
        mostrar(G.burbujas(d, x, y, tam, col,
                           ["jugador", "equipo", "liga"] + [c for c in ejes if c not in (x, y)][:4],
                           f"{y} vs. {x}", alto=520), key="mlb_expl")
        c1, c2 = st.columns([1.15, 1])
        with c1:
            st.markdown("##### Matriz de correlación")
            mostrar(G.heatmap_correlacion(A.matriz_correlacion(d, ejes),
                                          "Correlaciones de Pearson", alto=540), key="mlb_corr")
        with c2:
            st.markdown("##### Distribución")
            metrica_hist = st.selectbox("Métrica", ejes, key="mlb_hist_m")
            mostrar(G.histograma(d, metrica_hist, f"Distribución de {metrica_hist}",
                                 alto=420, color="liga"), key="mlb_hist")
            st.markdown("##### Líderes por categoría oficial")
            try:
                res_lid = F.mlb_lideres(temporada, grupo_api, 8, forzar=forzar)
                cat = st.selectbox("Categoría", sorted(res_lid.df["categoria"].unique()), key="mlb_cat")
                tabla(res_lid.df[res_lid.df["categoria"] == cat][["rank", "jugador", "equipo", "valor"]])
            except Exception as exc:                          # noqa: BLE001
                st.caption(f"(No disponible: {exc})")

    with tab4:
        tabla(d.sort_values("OPS" if grupo_api == "hitting" else "ERA",
                            ascending=grupo_api != "hitting"), altura=520)
        descargar(d, f"mlb_{grupo_api}_{temporada}")
        with st.expander("📋 Reporte de calidad de datos (nulos y tipos)"):
            tabla(A.resumen_nulos(d))


# ===========================================================================
# SECCIÓN 3 · 🏎️ FÓRMULA 1
# ===========================================================================
def render_f1(forzar: bool):
    st.subheader("🏎️ Rendimiento de pilotos — Fórmula 1")
    st.caption("Resultados carrera por carrera y clasificación de pilotos. "
               "Fuente: Jolpica-F1 (API comunitaria sucesora de Ergast).")

    temporada = st.selectbox("Temporada", [dt.date.today().year, dt.date.today().year - 1,
                                           dt.date.today().year - 2], key="f1_temp")
    with st.spinner("Consultando Jolpica-F1…"):
        try:
            res_res = F.f1_resultados(temporada, forzar=forzar)
            res_std = F.f1_standings(temporada, forzar=forzar)
        except Exception as exc:                              # noqa: BLE001
            st.error(f"No se pudo cargar la temporada {temporada}: {exc}")
            return

    std, acum = A.preparar_f1_resultados(res_res.df)
    tabla_pil = res_std.df.copy()

    # Métricas agregadas por piloto (Pandas)
    agg = (std.groupby(["code", "piloto", "equipo"])
             .agg(carreras=("ronda", "count"), victorias=("gano", "sum"),
                  podios=("podio", "sum"), top10=("top10", "sum"),
                  retiros=("termino", lambda s: int((s == 0).sum())),
                  vueltas=("vueltas", "sum"),
                  pos_media=("posicion", "mean"), parrilla_media=("parrilla", "mean"),
                  ganancia_puestos=("puestos_ganados", "mean"),
                  mejor_resultado=("posicion", "min"))
             .reset_index())
    agg["podios_%"] = agg["podios"] / agg["carreras"].replace(0, np.nan) * 100
    # 'outer' conserva a los pilotos que solo aparecen en uno de los dos conjuntos
    agg_calc = agg.rename(columns={"equipo": "equipo_calc", "victorias": "victorias_calc"})
    tabla_pil = tabla_pil.merge(agg_calc, on=["code", "piloto"], how="outer")
    tabla_pil["equipo"] = tabla_pil["equipo"].fillna(tabla_pil["equipo_calc"])
    tabla_pil["victorias"] = tabla_pil["victorias"].fillna(tabla_pil["victorias_calc"]).fillna(0)
    tabla_pil["podios"] = tabla_pil["podios"].fillna(0)
    tabla_pil["puntos_por_carrera"] = tabla_pil["puntos"] / tabla_pil["carreras"].replace(0, np.nan)
    tabla_pil["consistencia"] = 100 - tabla_pil["retiros"].fillna(0) / tabla_pil["carreras"].replace(0, np.nan) * 100

    ficha_fuente(res_res, f"{temporada} · {int(std['ronda'].max())} rondas disputadas")
    if res_std.origen != "API en vivo":
        st.caption(f"Clasificación desde {res_std.origen} ({res_std.hora}).")

    k = st.columns(4)
    puntero = tabla_pil.sort_values("puntos", ascending=False).iloc[0]
    k[0].metric("🏆 Líder del campeonato", puntero["piloto"], f"{puntero['puntos']:.0f} pts")
    max_vic = tabla_pil.sort_values("victorias", ascending=False).iloc[0]
    k[1].metric("🥇 Más victorias", max_vic["piloto"], f"{max_vic['victorias']:.0f} victorias")
    mejor_pm = tabla_pil[tabla_pil["carreras"] >= 5].sort_values("pos_media").iloc[0]
    k[2].metric("📊 Mejor posición media", mejor_pm["piloto"], f"P{mejor_pm['pos_media']:.1f}")
    mejor_gan = tabla_pil[tabla_pil["carreras"] >= 5].sort_values("ganancia_puestos", ascending=False).iloc[0]
    k[3].metric("🚀 Más puestos ganados", mejor_gan["piloto"], f"{mejor_gan['ganancia_puestos']:+.1f} por carrera")

    tab1, tab2, tab3, tab4 = st.tabs(["🏆 Rankings", "📈 Evolución del campeonato",
                                      "🔍 Comparador de pilotos", "🗂️ Datos y descarga"])

    with tab1:
        c1, c2 = st.columns(2)
        with c1:
            mostrar(G.barras_top(tabla_pil.dropna(subset=["puntos"]), "piloto", "puntos",
                                 "Puntos del campeonato", 20, color="equipo"), key="f1_bar_puntos")
        with c2:
            mostrar(G.burbujas(tabla_pil.dropna(subset=["pos_media"]), "parrilla_media", "pos_media",
                               "carreras", "ganancia_puestos",
                               ["piloto", "equipo", "victorias", "podios"],
                               "Clasificación vs. posición final — color = puestos ganados",
                               alto=470), key="f1_scatter_pos")
        c3, c4 = st.columns(2)
        with c3:
            mostrar(G.barras_apiladas(agg.sort_values("podios", ascending=False).head(12),
                                      "piloto", "valor", "tipo",
                                      "Podios y victorias (top 12)",
                                      ) if False else
                    G.barras_agrupadas(agg.nlargest(12, "victorias").melt(
                        id_vars=["piloto"], value_vars=["victorias", "podios"]),
                        "piloto", "value", "variable", "Victorias y podios (top 12)",
                        alto=470), key="f1_agrup")
        with c4:
            mostrar(G.histograma(std.dropna(subset=["posicion"]), "posicion",
                                 "Distribución de posiciones de llegada", nbins=20,
                                 color="equipo", alto=470), key="f1_hist")
        st.markdown("##### Clasificación general")
        cols = ["posicion_final", "piloto", "equipo", "puntos", "victorias", "podios",
                "carreras", "retiros", "pos_media", "puntos_por_carrera", "consistencia"]
        tabla(tabla_pil[[c for c in cols if c in tabla_pil.columns]]
              .sort_values("puntos", ascending=False)
              .style.format({"puntos_por_carrera": "{:.2f}", "pos_media": "{:.1f}",
                             "consistencia": "{:.0f}%", "parrilla_media": "{:.1f}"}, na_rep="—"))

    with tab2:
        top_pilotos = st.slider("Pilotos en el gráfico", 3, 15, 8, key="f1_top_lineas")
        lideres = tabla_pil.nlargest(top_pilotos, "puntos")["code"].tolist()
        mostrar(G.lineas_acumuladas(acum[acum["code"].isin(lideres)], "ronda",
                                    "puntos_acumulados", "piloto",
                                    "Evolución de puntos por ronda", alto=540), key="f1_lineas")
        c1, c2 = st.columns([1, 1])
        with c1:
            st.markdown("##### Puntos por ronda de cada piloto (top 8)")
            mostrar(G.heatmap_pistas(std[std["code"].isin(lideres)], "piloto", "ronda", "puntos",
                                     "Puntos obtenidos por ronda", alto=470), key="f1_heat")
        with c2:
            st.markdown("##### Resultados por carrera (posición final)")
            carreras = sorted(std["ronda"].unique())
            rango = st.select_slider("Rondas", options=carreras,
                                     value=(carreras[max(0, len(carreras) - 8)], carreras[-1]),
                                     key="f1_rango")
            sub_c = std[(std["ronda"] >= rango[0]) & (std["ronda"] <= rango[1])]
            mostrar(G.heatmap_pistas(sub_c[sub_c["code"].isin(lideres)], "piloto", "ronda",
                                     "posicion", "Posición final (1 = ganó)", alto=470),
                    key="f1_heat_pos")

    with tab3:
        seleccion = st.multiselect("Pilotos a comparar (2 a 5)",
                                   tabla_pil["piloto"].tolist(),
                                   default=tabla_pil.nlargest(3, "puntos")["piloto"].tolist(),
                                   key="f1_comp")
        if len(seleccion) < 2:
            aviso_sin_datos("Selecciona al menos 2 pilotos.", "🧩")
        else:
            sub = tabla_pil[tabla_pil["piloto"].isin(seleccion)].copy()
            metr = ["puntos", "victorias", "podios", "carreras", "top10", "retiros",
                    "pos_media", "parrilla_media", "ganancia_puestos", "mejor_resultado",
                    "puntos_por_carrera", "consistencia"]
            comp = A.tabla_comparacion(sub, "piloto", seleccion, [m for m in metr if m in sub.columns])
            c1, c2 = st.columns([1, 1])
            with c1:
                st.markdown("##### Comparación directa")
                tabla(comp.rename_axis("Métrica"), altura=min(140 + 40 * len(metr), 780))
                descargar(comp, "comparacion_f1")
                st.markdown("##### Detalle por carrera")
                tabla(std[std["piloto"].isin(seleccion)][
                    ["ronda", "carrera", "piloto", "parrilla", "posicion", "puestos_ganados",
                     "puntos", "estado"]].sort_values(["ronda", "posicion"]), altura=360)
            with c2:
                st.markdown("##### Métricas clave por piloto")
                largo = sub.melt(id_vars=["piloto"],
                                 value_vars=[m for m in ["victorias", "podios", "top10", "retiros"] if m in sub.columns])
                mostrar(G.barras_agrupadas(largo, "piloto", "value", "variable",
                                           "Conteos de la temporada", alto=430), key="f1_comp_bar")
                mostrar(G.barras_agrupadas(sub.melt(id_vars=["piloto"],
                                                    value_vars=["pos_media", "parrilla_media"]),
                                           "piloto", "value", "variable",
                                           "Posición media: final vs. parrilla (menor = mejor)",
                                           alto=430), key="f1_comp_bar2")

    with tab4:
        tabla(tabla_pil.drop(columns=[c for c in tabla_pil.columns if c.endswith("_calc")])
              .sort_values("puntos", ascending=False), altura=460)
        descargar(tabla_pil, f"f1_pilotos_{temporada}", "⬇️ Descargar tabla de pilotos")
        st.markdown("##### Todos los resultados carrera por carrera")
        tabla(std.sort_values(["ronda", "posicion"])[
            ["temporada", "ronda", "carrera", "fecha", "pais", "piloto", "equipo",
             "parrilla", "posicion", "puntos", "vueltas", "estado"]], altura=480)
        descargar(std, f"f1_resultados_{temporada}", "⬇️ Descargar resultados completos")


# ===========================================================================
# SECCIÓN 4 · 🏀 NBA
# ===========================================================================
def render_nba(forzar: bool):
    st.subheader("🏀 Promedios de temporada — NBA")
    st.caption("Fuente: **balldontlie v2**, que requiere una API key gratuita "
               "(la API pública de NBA bloquea consultas automatizadas).")

    ruta_key = F.RAIZ / "data" / ".api_key_nba"
    guardada = ruta_key.read_text().strip() if ruta_key.exists() else ""
    clave = st.text_input("API key de balldontlie", value=guardada, type="password",
                          help="Se guarda localmente en data/.api_key_nba (no se envía a ningún sitio).")
    c1, c2, c3 = st.columns([1, 1, 2])
    temporada = c1.selectbox("Temporada (año de inicio)", list(range(dt.date.today().year, 2017, -1)),
                             key="nba_temp")
    if c2.button("💾 Guardar key localmente") and clave:
        ruta_key.write_text(clave.strip())
        st.success("Key guardada en data/.api_key_nba")
    if c3.button("ℹ️ ¿Cómo obtengo una key gratis?") or not clave:
        with st.expander("Cómo conseguir la API key de balldontlie (2 minutos)", expanded=not clave):
            st.markdown("""
1. Entra a **https://www.balldontlie.io** y pulsa *Sign up / Get API key* (plan **free**: datos de temporadas anteriores y endpoints básicos).
2. Copia la key y pégala arriba, o guárdala en un archivo `data/.api_key_nba`.
3. Alternativa sin registro: define `NBA_API_KEY` como variable de entorno.

> ⚠️ Nota honesta: el plan gratuito de balldontlie no cubre temporadas muy recientes en
> todos los planes. Si la consulta devuelve error, prueba `temporada 2024` o `2023`.
> Las otras tres secciones del dashboard (fútbol, MLB y F1) funcionan sin ninguna key.
""")
    if not clave:
        aviso_sin_datos("Introduce tu API key para cargar los promedios de la NBA.", "🔑")
        return

    with st.spinner("Consultando balldontlie…"):
        try:
            res = F.nba_promedios(clave, temporada, forzar=forzar)
        except Exception as exc:                              # noqa: BLE001
            st.error(f"No se pudo cargar la NBA: {exc}")
            st.info("Consejo: el plan gratuito de balldontlie no siempre cubre la temporada "
                    "más reciente. Prueba con un año anterior (por ejemplo 2024 o 2023), "
                    "que sí suele estar disponible en el plan free.")
            return
    df = A.preparar_nba(res.df)
    ficha_fuente(res, f"temporada {temporada}")
    if df.empty:
        aviso_sin_datos("La API no devolvió registros para esa temporada.")
        return

    min_pj = st.slider("Mínimo de partidos jugados (aprox.)", 0, 82, 20, key="nba_pj")
    d = df
    if "gp" in df.columns:
        d = df[pd.to_numeric(df["gp"], errors="coerce").fillna(0) >= min_pj]

    k = st.columns(4)
    k[0].metric("🔥 Más puntos", d.loc[d["pts"].idxmax()]["jugador"], f"{d['pts'].max():.1f} por partido")
    k[1].metric("💪 Más rebotes", d.loc[d["reb"].idxmax()]["jugador"], f"{d['reb'].max():.1f}")
    k[2].metric("🎯 Más asistencias", d.loc[d["ast"].idxmax()]["jugador"], f"{d['ast'].max():.1f}")
    k[3].metric("⭐ Mejor TS%", d.loc[d["TS_%"].idxmax()]["jugador"], f"{d['TS_%'].max():.1f}%")

    tab1, tab2, tab3 = st.tabs(["🏆 Rankings", "🔍 Comparador", "🗂️ Datos"])
    with tab1:
        c1, c2 = st.columns(2)
        with c1:
            mostrar(G.barras_top(d, "jugador", "pts", "Máximos anotadores", 20, color="equipo"),
                    key="nba_bar")
        with c2:
            mostrar(G.burbujas(d, "pts", "ast", "reb", "TS_%",
                               ["jugador", "equipo", "PTS+REB+AST"],
                               "Puntos vs. asistencias — tamaño = rebotes, color = TS%",
                               alto=470), key="nba_scatter")
        mostrar(G.heatmap_correlacion(A.matriz_correlacion(d, ["pts", "reb", "ast", "stl",
                                                               "blk", "TS_%", "eFG_%"]),
                                      "Correlaciones", alto=480), key="nba_corr")
    with tab2:
        seleccion = st.multiselect("Jugadores (2 a 5)", d["jugador"].tolist(),
                                   default=d.nlargest(3, "pts")["jugador"].tolist(), key="nba_comp")
        if len(seleccion) >= 2:
            sub = d[d["jugador"].isin(seleccion)]
            metr = ["pts", "reb", "ast", "stl", "blk", "TS_%", "eFG_%", "PTS+REB+AST"]
            tabla(A.tabla_comparacion(sub, "jugador", seleccion, metr).rename_axis("Métrica"))
        else:
            aviso_sin_datos("Selecciona al menos 2 jugadores.", "🧩")
    with tab3:
        tabla(d, altura=520)
        descargar(d, f"nba_promedios_{temporada}")


# ===========================================================================
# ESTRUCTURA PRINCIPAL
# ===========================================================================
def main():
    st.sidebar.title("⚙️ Panel de control")
    st.sidebar.caption("Elige el deporte y ajusta la visualización.")

    deporte = st.sidebar.radio("Deporte", ["⚽ Fútbol", "⚾ Béisbol (MLB)",
                                           "🏎️ Fórmula 1", "🏀 NBA"], key="dep")
    st.sidebar.divider()
    oscuro = st.sidebar.toggle("Gráficos en tema oscuro", value=True, key="tema_oscuro")
    G.configurar_tema(oscuro)
    forzar = st.sidebar.button("🔄 Actualizar datos desde la API",
                               help="Ignora la caché local y vuelve a consultar las APIs.")
    if forzar:
        st.cache_data.clear()

    with st.sidebar.expander("🛰️ Estado de las fuentes"):
        if st.button("Probar conexión", key="ping"):
            with st.spinner("Comprobando…"):
                for nombre, estado in F.probar_conexion().items():
                    st.write(("✅ " if estado is True else "⚠️ ") + f"{nombre}: {estado}")
        st.caption("Las respuestas se guardan en caché local (3 h) para no saturar las APIs. "
                   "Si una API cae, el dashboard usa el último snapshot guardado.")

    st.sidebar.divider()
    st.sidebar.markdown(
        "<div class='ficha'><b>Stack del proyecto</b><br>"
        "🐍 Python + <b>Pandas</b> (transformación, métricas derivadas, percentiles)<br>"
        "🌐 <b>APIs</b>: Understat · MLB StatsAPI · Jolpica-F1 · balldontlie<br>"
        "📊 <b>Plotly</b> (gráficos) + <b>Streamlit</b> (interfaz)</div>",
        unsafe_allow_html=True)

    st.title("📊 Dashboard interactivo de estadísticas de jugadores")
    st.markdown("Datos **en vivo desde APIs públicas**, procesados con Pandas y visualizados "
                "con Plotly. Usa los filtros para explorar, comparar jugadores y descargar los datos.")

    if deporte == "⚽ Fútbol":
        render_futbol(forzar)
    elif deporte == "⚾ Béisbol (MLB)":
        render_mlb(forzar)
    elif deporte == "🏎️ Fórmula 1":
        render_f1(forzar)
    else:
        render_nba(forzar)

    st.divider()
    st.caption("⚠️ Datos con fines demostrativos/analíticos. Se respeta la caché local para no "
               "saturar las APIs públicas. Proyecto: `dashboard_jugadores/` — `app.py` (interfaz), "
               "`fuentes.py` (APIs), `analitica.py` (Pandas), `graficos.py` (Plotly).")


if __name__ == "__main__":
    main()
