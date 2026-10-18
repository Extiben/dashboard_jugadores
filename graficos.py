"""
graficos.py — Fábrica de gráficos Plotly del dashboard.

Todas las funciones devuelven `plotly.graph_objects.Figure` listas para Streamlit.
El estilo (tema claro/oscuro) se controla con la variable `TEMPLATE`.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

TEMPLATE = "plotly_dark"
PALETA = px.colors.qualitative.Vivid


def configurar_tema(oscuro: bool = True) -> None:
    global TEMPLATE
    TEMPLATE = "plotly_dark" if oscuro else "plotly_white"


def _estilo(fig: go.Figure, titulo: str = "", x: str = "", y: str = "",
            alto: int = 430, leyenda: bool = True) -> go.Figure:
    fig.update_layout(
        template=TEMPLATE, title=titulo, height=alto,
        margin=dict(l=10, r=10, t=50 if titulo else 20, b=10),
        xaxis_title=x, yaxis_title=y,
        showlegend=leyenda,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
        hoverlabel=dict(namelength=-1),
    )
    return fig


# ---------------------------------------------------------------------------
# Comparaciones y rankings
# ---------------------------------------------------------------------------
def barras_top(df: pd.DataFrame, x: str, y: str, titulo: str = "", top: int = 15,
               horizontal: bool = True, color: str | None = None,
               texto: str | None = None, alto: int = 460,
               ascendente: bool = False) -> go.Figure:
    """ascendente=True sirve para métricas donde menos es mejor (ERA, WHIP, posiciones)."""
    limpio = df.dropna(subset=[y])
    datos = limpio.nsmallest(top, y) if ascendente else limpio.nlargest(top, y)
    datos = datos.sort_values(y, ascending=not horizontal)
    serie = pd.to_numeric(datos[y], errors="coerce").dropna()
    formato = ":.0f" if not serie.empty and (serie.round(0) == serie).all() else ":.2f"
    fig = px.bar(datos, x=y if horizontal else x, y=x if horizontal else y,
                 orientation="h" if horizontal else "v", color=color,
                 text=texto or y, color_discrete_sequence=PALETA)
    fig.update_traces(texttemplate="%{text:" + formato + "}", textposition="outside",
                      cliponaxis=False)
    return _estilo(fig, titulo, x=y if horizontal else x, y=x if horizontal else y,
                   alto=alto, leyenda=color is not None)


def barras_agrupadas(df: pd.DataFrame, x: str, y: str, color: str,
                     titulo: str = "", horizontal: bool = False, alto: int = 430) -> go.Figure:
    fig = px.bar(df, x=x, y=y, color=color, barmode="group",
                 orientation="h" if horizontal else "v",
                 color_discrete_sequence=PALETA)
    fig.update_traces(texttemplate="%{y:.1f}" if not horizontal else "%{x:.1f}",
                      textposition="outside", cliponaxis=False)
    return _estilo(fig, titulo, x if not horizontal else y, y if not horizontal else x, alto)


def burbujas(df: pd.DataFrame, x: str, y: str, tamano: str | None = None,
             color: str | None = None, hover: list[str] | None = None,
             titulo: str = "", etiquetas: bool = True, alto: int = 500,
             tamano_max: int = 42, umbral_etiquetas: int = 70) -> go.Figure:
    """Dispersión de burbujas. Si hay demasiados puntos, se omiten las etiquetas
    para no saturar el gráfico (los nombres siguen disponibles al pasar el cursor)."""
    datos = df.dropna(subset=[c for c in (x, y) if c in df.columns]).copy()
    usa_tamano = bool(tamano) and tamano in datos.columns
    usa_color = bool(color) and color in datos.columns
    con_etiquetas = etiquetas and len(datos) <= umbral_etiquetas
    if con_etiquetas:
        primera = datos.columns[0]
        datos["_etiqueta"] = (datos[primera].astype(str)
                              if datos[primera].dtype == object else datos.index.astype(str))
    fig = px.scatter(
        datos, x=x, y=y,
        size=tamano if usa_tamano else None,
        color=color if usa_color else None,
        hover_name=hover[0] if hover and hover[0] in datos.columns else None,
        hover_data=[c for c in (hover[1:] if hover and len(hover) > 1 else []) if c in datos.columns] or None,
        text="_etiqueta" if con_etiquetas else None,
        size_max=tamano_max, color_discrete_sequence=PALETA,
        color_continuous_scale="Turbo",
    )
    if con_etiquetas:
        fig.update_traces(textposition="top center", textfont=dict(size=10))
    if usa_color and pd.api.types.is_numeric_dtype(datos[color]):
        fig.update_coloraxes(colorbar=dict(title=color, thickness=12))
    # líneas de referencia en la media
    for eje, nombre in (("x", x), ("y", y)):
        media = pd.to_numeric(datos[nombre], errors="coerce").mean()
        if pd.notna(media):
            fig.add_vline(x=media, line_dash="dot", line_width=1, opacity=.45) \
                if eje == "x" else fig.add_hline(y=media, line_dash="dot", line_width=1, opacity=.45)
    return _estilo(fig, titulo, x, y, alto)


def dispersion_simple(df: pd.DataFrame, x: str, y: str, color: str | None = None,
                      titulo: str = "", alto: int = 470) -> go.Figure:
    """Dispersión con recta de tendencia calculada con NumPy (sin statsmodels)."""
    datos = df.dropna(subset=[x, y])
    fig = px.scatter(datos, x=x, y=y, color=color if color in datos.columns else None,
                     color_discrete_sequence=PALETA, opacity=.8)
    xs, ys = pd.to_numeric(datos[x], errors="coerce"), pd.to_numeric(datos[y], errors="coerce")
    if len(datos) > 2 and xs.notna().all() and ys.notna().all() and xs.nunique() > 1:
        pendiente, intercepto = np.polyfit(xs, ys, 1)
        r2 = xs.corr(ys) ** 2
        linea_x = np.linspace(xs.min(), xs.max(), 50)
        fig.add_trace(go.Scatter(x=linea_x, y=pendiente * linea_x + intercepto, mode="lines",
                                 name=f"tendencia (R² = {r2:.2f})",
                                 line=dict(dash="dash", width=2, color="#9aa0a6")))
    return _estilo(fig, titulo, x, y, alto)


# ---------------------------------------------------------------------------
# Evolución temporal
# ---------------------------------------------------------------------------
def lineas_acumuladas(df: pd.DataFrame, x: str, y: str, color: str,
                      titulo: str = "", etiquetar_final: bool = True,
                      alto: int = 520) -> go.Figure:
    fig = px.line(df, x=x, y=y, color=color, markers=False,
                  color_discrete_sequence=PALETA)
    if etiquetar_final and not df.empty:
        ultimo = df.sort_values(x).groupby(color, as_index=False).last()
        for _, fila in ultimo.iterrows():
            fig.add_annotation(x=fila[x], y=fila[y], text=str(fila[color]),
                               showarrow=False, xanchor="left", xshift=6,
                               font=dict(size=10))
        fig.update_xaxes(range=[df[x].min(), df[x].max() * 1.09])
    return _estilo(fig, titulo, x, y, alto)


def linea_tendencia(df: pd.DataFrame, x: str, y: str, titulo: str = "",
                    media_movil: int | None = None, alto: int = 420) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df[x], y=df[y], mode="lines+markers", name=y))
    if media_movil and len(df) > media_movil:
        fig.add_trace(go.Scatter(x=df[x], y=df[y].rolling(media_movil).mean(),
                                 mode="lines", name=f"media móvil ({media_movil})",
                                 line=dict(width=3, dash="dash")))
    return _estilo(fig, titulo, x, y, alto)


def radar(etiquetas: list[str], valores: list[float], nombres: list[str],
          titulo: str = "", alto: int = 520) -> go.Figure:
    fig = go.Figure()
    for i, nombre in enumerate(nombres):
        bruta = list(valores[i]) if i < len(valores) else []
        serie = [0 if (v is None or (isinstance(v, float) and np.isnan(v)) or pd.isna(v)) else float(v)
                 for v in bruta]
        if len(serie) < len(etiquetas):                    # rellena huecos con 0
            serie += [0] * (len(etiquetas) - len(serie))
        if not serie:
            continue
        fig.add_trace(go.Scatterpolar(
            r=serie + [serie[0]], theta=etiquetas + [etiquetas[0]],
            name=nombre, fill="toself", opacity=.55,
            line=dict(color=PALETA[i % len(PALETA)])))
    fig.update_layout(template=TEMPLATE, title=titulo, height=alto,
                      polar=dict(radialaxis=dict(visible=True, range=[0, 100])),
                      legend=dict(orientation="h", yanchor="bottom", y=1.08, x=0))
    return fig


# ---------------------------------------------------------------------------
# Distribuciones y relaciones
# ---------------------------------------------------------------------------
def heatmap_correlacion(corr: pd.DataFrame, titulo: str = "", alto: int = 560) -> go.Figure:
    texto = corr.round(2).astype(str).values
    fig = go.Figure(go.Heatmap(
        z=corr.values, x=corr.columns, y=corr.index, text=texto, texttemplate="%{text}",
        colorscale="RdBu", zmid=0, zmin=-1, zmax=1, colorbar=dict(thickness=12)))
    fig.update_layout(template=TEMPLATE, title=titulo, height=alto, xaxis=dict(tickangle=-45))
    return fig


def histograma(df: pd.DataFrame, col: str, titulo: str = "", nbins: int = 30,
               color: str | None = None, alto: int = 420) -> go.Figure:
    datos = df.dropna(subset=[col])
    fig = px.histogram(datos, x=col, nbins=nbins, color=color if color in datos.columns else None,
                       marginal="box", opacity=.85, color_discrete_sequence=PALETA)
    return _estilo(fig, titulo, col, "Jugadores", alto)


def box_por_grupo(df: pd.DataFrame, x: str, y: str, titulo: str = "",
                  puntos: bool = True, alto: int = 460) -> go.Figure:
    datos = df.dropna(subset=[y])
    fig = px.box(datos, x=x, y=y, color=x, points="all" if puntos else False,
                 color_discrete_sequence=PALETA)
    fig.update_traces(marker=dict(size=4, opacity=.5))
    return _estilo(fig, titulo, "", y, alto, leyenda=False)


def dona(df: pd.DataFrame, nombres: str, valores: str, titulo: str = "",
         hueco: float = .45, alto: int = 430) -> go.Figure:
    fig = px.pie(df, names=nombres, values=valores, hole=hueco,
                 color_discrete_sequence=PALETA)
    fig.update_traces(textposition="inside", textinfo="percent+label")
    fig.update_layout(template=TEMPLATE, title=titulo, height=alto)
    return fig


def barras_divergentes(df: pd.DataFrame, etiqueta: str, valor: str, titulo: str = "",
                       top: int = 15, alto: int = 460) -> go.Figure:
    """Para métricas con signo (p. ej. goles – xG): verde por encima, rojo por debajo."""
    datos = df.dropna(subset=[valor]).nlargest(top, valor, keep="all")
    datos = pd.concat([datos, df.dropna(subset=[valor]).nsmallest(top, valor)]).drop_duplicates()
    datos = datos.sort_values(valor)
    colores = ["#2ecc71" if v >= 0 else "#e74c3c" for v in datos[valor]]
    fig = go.Figure(go.Bar(x=datos[valor], y=datos[etiqueta], orientation="h",
                           marker_color=colores,
                           hovertemplate="%{y}: %{x:.2f}<extra></extra>"))
    fig.add_vline(x=0, line_width=1, line_color="gray")
    return _estilo(fig, titulo, valor, "", alto, leyenda=False)


def tabla_heatmap_puntos(df: pd.DataFrame, indice: str, columnas: list[str],
                         titulo: str = "", colormap: str = "Viridis",
                         alto: int = 520, inverso: bool = False) -> go.Figure:
    """Heatmap de métricas normalizadas (0-100) por jugador — ideal para comparar varios."""
    datos = df.set_index(indice)[columnas]
    fig = go.Figure(go.Heatmap(
        z=datos.values, x=columnas, y=datos.index, colorscale=colormap,
        reversescale=inverso, colorbar=dict(thickness=12),
        hovertemplate="%{y}<br>%{x}: %{z:.0f}<extra></extra>"))
    fig.update_layout(template=TEMPLATE, title=titulo, height=alto, yaxis=dict(autorange="reversed"))
    return fig


def barras_apiladas(df: pd.DataFrame, x: str, y: str, color: str,
                    titulo: str = "", horizontal: bool = True, alto: int = 470) -> go.Figure:
    fig = px.bar(df, x=y if horizontal else x, y=x if horizontal else y, color=color,
                 orientation="h" if horizontal else "v", barmode="stack",
                 color_discrete_sequence=PALETA)
    return _estilo(fig, titulo, "", "", alto)


def caja_evolucion(df: pd.DataFrame, x: str, y: str, color: str, titulo: str = "",
                   alto: int = 460) -> go.Figure:
    fig = px.box(df, x=x, y=y, color=color, color_discrete_sequence=PALETA)
    return _estilo(fig, titulo, x, y, alto)


def heatmap_pistas(df: pd.DataFrame, indice: str, columnas: str, valor: str,
                   titulo: str = "", alto: int = 500) -> go.Figure:
    pivote = df.pivot_table(index=indice, columns=columnas, values=valor, aggfunc="mean")
    fig = go.Figure(go.Heatmap(z=pivote.values, x=pivote.columns, y=pivote.index,
                               colorscale="Tealgrn", colorbar=dict(thickness=12)))
    fig.update_layout(template=TEMPLATE, title=titulo, height=alto)
    return fig
