"""
analitica.py — Transformaciones con Pandas para el dashboard de estadísticas de jugadores.

Todas las funciones reciben DataFrames crudos (tal como llegan de las APIs) y
devuelven DataFrames "listos para graficar": tipos corregidos, métricas derivadas
y percentiles por posición cuando aplica.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# ----------------------------------------------------------------------------
# Utilidades genéricas
# ----------------------------------------------------------------------------

def a_numero(df: pd.DataFrame, columnas: list[str]) -> pd.DataFrame:
    """Convierte columnas (que suelen venir como str desde las APIs) a float."""
    df = df.copy()
    for c in columnas:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def por_90(df: pd.DataFrame, columna: str, minutos: str = "minutos",
           minimo_minutos: float = 1.0) -> pd.Series:
    """Normaliza una métrica acumulada a 'por 90 minutos' (o 9 innings, etc.)."""
    minutos = pd.to_numeric(df[minutos], errors="coerce").replace(0, np.nan)
    valor = pd.to_numeric(df[columna], errors="coerce")
    return (valor / minutos * 90).where(minutos >= minimo_minutos)


def percentiles(df: pd.DataFrame, columnas: list[str], prefijo: str = "pct_") -> pd.DataFrame:
    """Percentiles 0-100 para cada columna (útil para gráficos de radar/talento)."""
    df = df.copy()
    for c in columnas:
        if c not in df.columns:
            continue
        valores = pd.to_numeric(df[c], errors="coerce")
        df[prefijo + c] = (valores.rank(pct=True) * 100).round(1)
    return df


def matriz_correlacion(df: pd.DataFrame, columnas: list[str]) -> pd.DataFrame:
    cols = [c for c in columnas if c in df.columns]
    return df[cols].apply(pd.to_numeric, errors="coerce").corr(numeric_only=True).round(2)


def percentil_de(df: pd.DataFrame, columna: str, valor: float) -> float:
    """¿En qué percentil (0-100) queda un valor dentro de la población?"""
    serie = pd.to_numeric(df[columna], errors="coerce").dropna()
    if serie.empty:
        return float("nan")
    return round(float((serie <= valor).mean() * 100), 1)


# ----------------------------------------------------------------------------
# ⚽ FÚTBOL  (Understat: goles, xG, asistencias, xA, tiros, pases clave)
# ----------------------------------------------------------------------------

def preparar_futbol(df: pd.DataFrame) -> pd.DataFrame:
    num = ["games", "time", "goals", "xG", "assists", "xA", "shots", "key_passes",
           "yellow_cards", "red_cards", "npg", "npxG", "xGChain", "xGBuildup"]
    df = a_numero(df, num)
    df = df.rename(columns={
        "player_name": "jugador", "team_title": "equipo", "position": "posicion",
        "games": "partidos", "time": "minutos", "goals": "goles", "assists": "asistencias",
        "shots": "tiros", "key_passes": "pases_clave", "yellow_cards": "amarillas",
        "red_cards": "rojas", "npg": "goles_sin_penal", "npxG": "npxg",
        "xGChain": "xg_cadena", "xGBuildup": "xg_construccion",
    })
    df["posicion"] = df.get("posicion", pd.Series(dtype=str)).fillna("?").astype(str)
    df["posicion_grupo"] = df["posicion"].str.split().str[0].map(
        {"F": "Delantero", "M": "Mediocampista", "D": "Defensa", "GK": "Arquero", "S": "Delantero"}
    ).fillna("Otro")
    # Métricas por 90 minutos
    df["goles_90"] = por_90(df, "goles")
    df["asist_90"] = por_90(df, "asistencias")
    df["xg_90"] = por_90(df, "xG")
    df["xa_90"] = por_90(df, "xA")
    df["tiros_90"] = por_90(df, "tiros")
    df["pases_clave_90"] = por_90(df, "pases_clave")
    # Eficiencia
    df["conversion_%"] = np.where(df["tiros"] > 0, df["goles"] / df["tiros"] * 100, np.nan)
    df["goles_menos_xg"] = df["goles"] - df["xG"]          # sobre/sub-rendimiento
    df["asist_menos_xa"] = df["asistencias"] - df["xA"]
    df["goles+asist"] = df["goles"] + df["asistencias"]
    df["g+a_90"] = por_90(df, "goles+asist")
    df["aporta_g+a"] = df["goles_menos_xg"].fillna(0) + df["asist_menos_xa"].fillna(0)
    df = percentiles(df, ["goles_90", "asist_90", "xg_90", "xa_90", "tiros_90", "pases_clave_90"])
    return df


# ----------------------------------------------------------------------------
# ⚾ BÉISBOL (MLB StatsAPI: bateo y pitcheo)
# ----------------------------------------------------------------------------

CAMPOS_BATEO = ["avg", "obp", "slg", "ops", "hits", "doubles", "triples", "homeRuns",
                "rbi", "runs", "stolenBases", "caughtStealing", "baseOnBalls",
                "strikeOuts", "hitByPitch", "plateAppearances", "atBats", "gamesPlayed", "age"]
CAMPOS_PITCHEO = ["era", "wins", "losses", "saves", "inningsPitched", "strikeOuts",
                  "baseOnBalls", "homeRuns", "hits", "earnedRuns", "whip", "gamesStarted",
                  "gamesPlayed", "strikeoutWalkRatio", "strikeoutsPer9Inn",
                  "walksPer9Inn", "hitsPer9Inn", "homeRunsPer9", "age"]


def preparar_mlb_bateo(df: pd.DataFrame) -> pd.DataFrame:
    df = a_numero(df, CAMPOS_BATEO)
    df = df.rename(columns={
        "avg": "AVG", "obp": "OBP", "slg": "SLG", "ops": "OPS", "hits": "H",
        "doubles": "2B", "triples": "3B", "homeRuns": "HR", "rbi": "CI", "runs": "C",
        "stolenBases": "BR", "baseOnBalls": "BB", "strikeOuts": "K",
        "plateAppearances": "AP", "atBats": "VB", "gamesPlayed": "PJ", "age": "edad",
    })
    pa = pd.to_numeric(df.get("AP"), errors="coerce").replace(0, np.nan)
    df["K_%"] = pd.to_numeric(df["K"], errors="coerce") / pa * 100
    df["BB_%"] = pd.to_numeric(df["BB"], errors="coerce") / pa * 100
    df["ISO"] = df["SLG"] - df["AVG"]                       # poder aislado
    df["HR_600"] = pd.to_numeric(df["HR"], errors="coerce") / pa * 600
    df["BABIP_aprox"] = np.where(
        (df["AP"].fillna(0) - df["K"].fillna(0) - df["BB"].fillna(0)) > 0,
        (df["H"].fillna(0) - df["HR"].fillna(0)) /
        (df["AP"].fillna(0) - df["K"].fillna(0) - df["BB"].fillna(0)), np.nan)
    df["SB_%"] = np.where((df["BR"].fillna(0) + pd.to_numeric(df.get("caughtStealing"), errors="coerce").fillna(0)) > 0,
                          df["BR"] / (df["BR"] + pd.to_numeric(df.get("caughtStealing"), errors="coerce").fillna(0)) * 100, np.nan)
    df = percentiles(df, ["AVG", "OBP", "SLG", "OPS", "HR", "CI", "BR", "BB_%", "K_%", "ISO", "HR_600"])
    return df


def preparar_mlb_pitcheo(df: pd.DataFrame) -> pd.DataFrame:
    df = a_numero(df, CAMPOS_PITCHEO)
    df = df.rename(columns={
        "era": "ERA", "wins": "W", "losses": "L", "saves": "SV", "inningsPitched": "IP",
        "strikeOuts": "K", "baseOnBalls": "BB", "homeRuns": "HR_perm", "hits": "H_perm",
        "earnedRuns": "CL", "whip": "WHIP", "gamesStarted": "GS", "gamesPlayed": "PJ",
        "age": "edad",
    })
    ip = pd.to_numeric(df["IP"], errors="coerce").replace(0, np.nan)
    df["K/9"] = pd.to_numeric(df.get("strikeoutsPer9Inn"), errors="coerce").fillna(
        pd.to_numeric(df["K"], errors="coerce") / ip * 9)
    df["BB/9"] = pd.to_numeric(df.get("walksPer9Inn"), errors="coerce").fillna(
        pd.to_numeric(df["BB"], errors="coerce") / ip * 9)
    df["HR/9"] = pd.to_numeric(df.get("homeRunsPer9"), errors="coerce").fillna(
        pd.to_numeric(df["HR_perm"], errors="coerce") / ip * 9)
    df["K-BB"] = df["K/9"] - df["BB/9"]
    # FIP aproximado: (13*HR + 3*BB - 2*K)/IP + constante ≈ 3.15
    df["FIP_aprox"] = (13 * df["HR_perm"].fillna(0) + 3 * df["BB"].fillna(0)
                       - 2 * df["K"].fillna(0)) / ip + 3.15
    df["Ponches_%"] = None  # se llena si hay bateadores enfrentados
    df = percentiles(df, ["ERA", "WHIP", "K/9", "BB/9", "K-BB"])
    return df


# ----------------------------------------------------------------------------
# 🏎️ FÓRMULA 1 (Jolpica/Ergast: resultados, standings)
# ----------------------------------------------------------------------------

def preparar_f1_resultados(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Devuelve (resultados_detallados, acumulado_por_ronda).

    Criterio de 'terminó la carrera': en los datos de Ergast/Jolpica el estado es
    "Finished" o "+N Lap(s)" cuando el piloto cruzó la meta; cualquier otro texto
    (Retired, Accident, Engine…) cuenta como abandono.
    """
    df = a_numero(df, ["posicion", "parrilla", "puntos", "vueltas", "ronda", "temporada"])
    df["gano"] = (df["posicion"] == 1).astype(int)
    df["podio"] = (df["posicion"] <= 3).astype(int)
    df["top10"] = (df["posicion"] <= 10).astype(int)
    termino = df["estado"].astype(str).str.match(r"^(Finished|\+\d+ Lap)", na=False)
    df["termino"] = termino.astype(int)
    # Puestos ganados vs. la parrilla de salida (0 = salida desde boxes: se descarta)
    df["puestos_ganados"] = np.where(df["parrilla"].fillna(0) > 0,
                                     df["parrilla"] - df["posicion"], np.nan)
    df = df.sort_values(["ronda", "posicion"])
    acumulado = (df.groupby(["code", "piloto", "ronda"])["puntos"].sum()
                   .groupby(level=[0, 1]).cumsum().rename("puntos_acumulados").reset_index())
    return df, acumulado


# ----------------------------------------------------------------------------
# 🏀 NBA (balldontlie, requiere API key gratuita)
# ----------------------------------------------------------------------------

def preparar_nba(df: pd.DataFrame) -> pd.DataFrame:
    """Promedios por partido + percentiles para el comparador de jugadores."""
    if df.empty:
        return df
    df = a_numero(df, ["pts", "reb", "ast", "stl", "blk", "turnover", "min", "fgm", "fga",
                       "fg3m", "fg3a", "ftm", "fta", "oreb", "dreb", "pf", "games_played"])
    df["TS_%"] = (df["pts"] / (2 * (df["fga"] + 0.44 * df["fta"])).replace(0, np.nan)) * 100
    df["eFG_%"] = ((df["fgm"] + 0.5 * df["fg3m"]) / df["fga"].replace(0, np.nan)) * 100
    df["PTS+REB+AST"] = df["pts"] + df["reb"] + df["ast"]
    df = percentiles(df, ["pts", "reb", "ast", "stl", "blk", "TS_%", "eFG_%", "PTS+REB+AST"])
    return df


# ----------------------------------------------------------------------------
# Comparador genérico
# ----------------------------------------------------------------------------

def tabla_comparacion(df: pd.DataFrame, clave: str, jugadores: list[str],
                      metricas: list[str]) -> pd.DataFrame:
    sub = df[df[clave].isin(jugadores)][[clave] + [m for m in metricas if m in df.columns]]
    return sub.set_index(clave).T


def resumen_nulos(df: pd.DataFrame) -> pd.DataFrame:
    """Reporte rápido de calidad de datos (nulos y tipos) — va en la pestaña 'Datos'."""
    rep = pd.DataFrame({
        "tipo": df.dtypes.astype(str),
        "no_nulos": df.notna().sum(),
        "nulos": df.isna().sum(),
        "nulos_%": (df.isna().mean() * 100).round(1),
    })
    return rep.sort_values("nulos_%", ascending=False)
