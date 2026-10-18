"""
fuentes.py — Clientes de APIs de estadísticas deportivas.

Fuentes (todas gratuitas y probadas):
  ⚽ Fútbol    : Understat (getPlayersStats) + OpenLigaDB (Bundesliga)
  ⚾ Béisbol   : MLB StatsAPI (statsapi.mlb.com)
  🏎️ Fórmula 1 : Jolpica-F1 (sucesor comunitario de la API de Ergast)
  🏀 NBA      : balldontlie v2 (requiere API key gratuita del usuario)

Cada función devuelve un `Resultado` con el DataFrame, de dónde salió el dato
y cuándo se descargó. Estrategia de resiliencia:

    1) ¿Hay datos en caché con menos de `TTL` segundos?  -> se usan (rapidísimo)
    2) Si no, se llama la API y se guarda un snapshot Parquet en data/cache/
    3) Si la API falla, se devuelve el ÚLTIMO snapshot guardado (modo respaldo)
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd
import requests

# ----------------------------------------------------------------------------
# Configuración
# ----------------------------------------------------------------------------
RAIZ = Path(__file__).resolve().parent
DIR_CACHE = RAIZ / "data" / "cache"
DIR_CACHE.mkdir(parents=True, exist_ok=True)

TTL_POR_DEFECTO = 60 * 60 * 3          # 3 horas
CABECERAS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/122.0 Safari/537.36"),
    "Accept": "application/json, text/plain, */*",
}

LIGAS_FUTBOL = {
    "Premier League (Inglaterra)": "EPL",
    "La Liga (España)": "La_liga",
    "Bundesliga (Alemania)": "Bundesliga",
    "Serie A (Italia)": "Serie_A",
    "Ligue 1 (Francia)": "Ligue_1",
    "Premier League (Rusia)": "RFPL",
}
TEMPORADAS_FUTBOL = {
    "2026/27 (en curso)": "2026",
    "2025/26": "2025",
    "2024/25": "2024",
}

CATEGORIAS_MLB_BATEO = {
    "homeRuns": "Jonrones (HR)", "battingAverage": "Promedio (AVG)",
    "rbi": "Carreras impulsadas", "ops": "OPS", "stolenBases": "Bases robadas",
    "hits": "Hits", "runs": "Carreras anotadas", "doubles": "Dobles",
}
CATEGORIAS_MLB_PITCHEO = {
    "earnedRunAverage": "ERA", "strikeouts": "Ponches (K)", "wins": "Victorias",
    "walksAndHitsPerInningPitched": "WHIP", "saves": "Salvamentos",
}


@dataclass
class Resultado:
    """Contenedor de datos + metadatos de procedencia."""
    df: pd.DataFrame
    origen: str                      # "API en vivo" | "caché local" | "respaldo offline"
    momento: float = 0.0             # timestamp unix de la descarga
    mensaje: str = ""
    extra: dict = field(default_factory=dict)

    @property
    def hora(self) -> str:
        return time.strftime("%Y-%m-%d %H:%M", time.localtime(self.momento)) if self.momento else "—"

    @property
    def es_en_vivo(self) -> bool:
        return self.origen == "API en vivo"


# ----------------------------------------------------------------------------
# Motor de caché
# ----------------------------------------------------------------------------
def _rutas(nombre: str) -> tuple[Path, Path]:
    return DIR_CACHE / f"{nombre}.parquet", DIR_CACHE / f"{nombre}.meta.json"


def _guardar(nombre: str, df: pd.DataFrame) -> None:
    parquet, meta = _rutas(nombre)
    try:
        df.to_parquet(parquet, index=False)
    except Exception:                       # respaldo si pyarrow no está disponible
        df.to_csv(parquet.with_suffix(".csv"), index=False)
    meta.write_text(json.dumps({"momento": time.time(), "filas": len(df),
                                "columnas": list(df.columns)}), encoding="utf-8")


def _leer(nombre: str) -> tuple[pd.DataFrame | None, float]:
    parquet, meta = _rutas(nombre)
    if parquet.exists():
        try:
            df = pd.read_parquet(parquet)
        except Exception:
            csv = parquet.with_suffix(".csv")
            df = pd.read_csv(csv) if csv.exists() else None
        if df is not None:
            ts = json.loads(meta.read_text(encoding="utf-8"))["momento"] if meta.exists() else 0.0
            return df, ts
    return None, 0.0


def con_cache(nombre: str, constructor, ttl: int = TTL_POR_DEFECTO,
              forzar: bool = False) -> Resultado:
    """Ejecuta `constructor()` respetando caché en disco y degradando con gracia."""
    df_cache, ts = _leer(nombre)
    if df_cache is not None and not forzar and (time.time() - ts) < ttl:
        return Resultado(df_cache, "caché local", ts)

    try:
        df = constructor()
        if df is None or len(df) == 0:
            raise ValueError("la fuente devolvió un conjunto vacío")
        _guardar(nombre, df)
        return Resultado(df, "API en vivo", time.time())
    except Exception as exc:                                  # noqa: BLE001
        mensaje = f"{type(exc).__name__}: {exc}"
        if df_cache is not None:
            return Resultado(df_cache, "respaldo offline", ts,
                             mensaje=f"API no disponible ({mensaje}). Se muestran los últimos datos guardados.")
        raise RuntimeError(f"No se pudo obtener '{nombre}' y no hay respaldo local. Detalle: {mensaje}") from exc


def _json(url: str, params: dict | None = None, *, post: dict | None = None,
          cabeceras: dict | None = None, intentos: int = 3) -> dict:
    cab = {**CABECERAS, **(cabeceras or {})}
    ultimo_error: Exception | None = None
    for n in range(intentos):
        try:
            if post is not None:
                r = requests.post(url, data=post, headers=cab, timeout=30)
            else:
                r = requests.get(url, params=params, headers=cab, timeout=30)
            r.raise_for_status()
            return r.json()
        except Exception as exc:                              # noqa: BLE001
            ultimo_error = exc
            time.sleep(0.8 * (n + 1))
    raise ultimo_error if ultimo_error else RuntimeError("fallo de red desconocido")


# ============================================================================
# ⚽ FÚTBOL — Understat
# ============================================================================
def _futbol_jugadores(liga: str, temporada: str) -> pd.DataFrame:
    datos = _json("https://understat.com/main/getPlayersStats/",
                  post={"league": liga, "season": temporada},
                  cabeceras={"X-Requested-With": "XMLHttpRequest",
                             "Referer": "https://understat.com/"})
    jugadores = datos.get("players") or []
    if not jugadores:
        raise ValueError(f"Understat no devolvió jugadores para {liga} {temporada}")
    return pd.DataFrame(jugadores)


def futbol_jugadores(liga: str, temporada: str, forzar: bool = False) -> Resultado:
    """Estadísticas ofensivas por jugador: goles, asistencias, xG, xA, tiros…"""
    return con_cache(f"futbol_{liga}_{temporada}", lambda: _futbol_jugadores(liga, temporada),
                     forzar=forzar)


def _bundesliga_extra(temporada: str) -> pd.DataFrame:
    """Goleadores oficiales (OpenLigaDB) para contrastar con los xG de Understat."""
    datos = _json(f"https://api.openligadb.de/getgoalgetters/bl1/{temporada}")
    df = pd.DataFrame(datos).rename(columns={"goalGetterName": "jugador",
                                             "goalCount": "goles_oficiales"})
    return df[["jugador", "goles_oficiales"]]


def bundesliga_goleadores(temporada: str, forzar: bool = False) -> Resultado:
    return con_cache(f"bundesliga_goleadores_{temporada}",
                     lambda: _bundesliga_extra(temporada), forzar=forzar)


# ============================================================================
# ⚾ BÉISBOL — MLB StatsAPI
# ============================================================================
def _abrev_pos(pos) -> str:
    """La API devuelve la posición como dict o como texto, según el endpoint."""
    if isinstance(pos, dict):
        return pos.get("abbreviation") or pos.get("name") or "—"
    return str(pos) if pos else "—"


def _mlb_jugadores(temporada: int, grupo: str) -> pd.DataFrame:
    datos = _json("https://statsapi.mlb.com/api/v1/stats",
                  params={"stats": "season", "group": grupo, "season": temporada,
                          "sportId": 1, "playerPool": "All", "limit": 1500,
                          "sortStat": "homeRuns" if grupo == "hitting" else "strikeOuts",
                          "order": "desc"})
    splits = datos["stats"][0]["splits"]
    filas = []
    for s in splits:
        fila = {"id_jugador": s["player"]["id"], "jugador": s["player"]["fullName"],
                "equipo": s.get("team", {}).get("name", "—"),
                "liga": s.get("league", {}).get("name", "—"),
                "posicion": _abrev_pos(s.get("position")),
                "equipos_en_temporada": s.get("numTeams", 1), **s["stat"]}
        filas.append(fila)
    df = pd.DataFrame(filas)
    # Jugadores traspasados a mitad de temporada: nos quedamos con el registro de totales
    if "id_jugador" in df.columns:
        df = (df.sort_values("gamesPlayed", ascending=False)
                .drop_duplicates("id_jugador", keep="first"))
    return df.reset_index(drop=True)


def mlb_jugadores(temporada: int, grupo: str = "hitting", forzar: bool = False) -> Resultado:
    grupo = "hitting" if grupo not in ("hitting", "pitching") else grupo
    return con_cache(f"mlb_{grupo}_{temporada}", lambda: _mlb_jugadores(temporada, grupo),
                     forzar=forzar)


def _mlb_lideres(temporada: int, categorias: dict[str, str], limite: int = 10) -> pd.DataFrame:
    filas = []
    for cat, etiqueta in categorias.items():
        grupo = "pitching" if cat in CATEGORIAS_MLB_PITCHEO else "hitting"
        datos = _json("https://statsapi.mlb.com/api/v1/stats/leaders",
                      params={"leaderCategories": cat, "season": temporada,
                              "sportId": 1, "statGroup": grupo, "limit": limite})
        for bloque in datos.get("leagueLeaders", []):
            for l in bloque.get("leaders", []):
                filas.append({"categoria": etiqueta, "jugador": l["person"]["fullName"],
                              "equipo": l.get("team", {}).get("name", "—"),
                              "valor": pd.to_numeric(l["value"], errors="coerce"),
                              "rank": l.get("rank")})
    return pd.DataFrame(filas).drop_duplicates(["categoria", "jugador"])


def mlb_lideres(temporada: int, grupo: str = "hitting", limite: int = 10,
                forzar: bool = False) -> Resultado:
    cats = CATEGORIAS_MLB_BATEO if grupo == "hitting" else CATEGORIAS_MLB_PITCHEO
    return con_cache(f"mlb_lideres_{grupo}_{temporada}_{limite}",
                     lambda: _mlb_lideres(temporada, cats, limite), forzar=forzar)


def mlb_buscar_jugador(nombre: str) -> pd.DataFrame:
    """Búsqueda de jugadores por nombre (sin caché: consulta puntual)."""
    datos = _json("https://statsapi.mlb.com/api/v1/people/search", params={"names": nombre})
    return pd.DataFrame(datos.get("people", []))


# ============================================================================
# 🏎️ FÓRMULA 1 — Jolpica (Ergast)
# ============================================================================
F1_BASE = "https://api.jolpi.ca/ergast/f1"


def _f1_resultados(temporada: int) -> pd.DataFrame:
    """Todos los resultados de la temporada (paginado: la API limita a 100 filas)."""
    filas, offset, total = [], 0, None
    while True:
        datos = _json(f"{F1_BASE}/{temporada}/results/",
                      params={"limit": 100, "offset": offset})["MRData"]
        total = int(datos["total"])
        carreras = datos["RaceTable"]["Races"]
        if not carreras:
            break
        for c in carreras:
            for res in c["Results"]:
                filas.append({
                    "temporada": int(c["season"]), "ronda": int(c["round"]),
                    "carrera": c["raceName"], "fecha": c.get("date"),
                    "pais": c.get("Circuit", {}).get("Location", {}).get("country"),
                    "circuito": c.get("Circuit", {}).get("circuitName"),
                    "code": res["Driver"].get("code", "?"),
                    "piloto": f"{res['Driver']['givenName']} {res['Driver']['familyName']}",
                    "nacionalidad": res["Driver"].get("nationality"),
                    "equipo": res["Constructor"]["name"],
                    "posicion": pd.to_numeric(res.get("position"), errors="coerce"),
                    "puntos": pd.to_numeric(res.get("points"), errors="coerce"),
                    "parrilla": pd.to_numeric(res.get("grid"), errors="coerce"),
                    "vueltas": pd.to_numeric(res.get("laps"), errors="coerce"),
                    "estado": res.get("status"),
                })
        offset += 100
        if offset >= total:
            break
    df = pd.DataFrame(filas)
    if df.empty:
        raise ValueError(f"sin resultados para la temporada {temporada}")
    return df.drop_duplicates(["ronda", "code"])


def f1_resultados(temporada: int, forzar: bool = False) -> Resultado:
    return con_cache(f"f1_resultados_{temporada}", lambda: _f1_resultados(temporada), forzar=forzar)


def _f1_standings(temporada: int) -> pd.DataFrame:
    datos = _json(f"{F1_BASE}/{temporada}/driverstandings/",
                  params={"limit": 60})["MRData"]["StandingsTable"]["StandingsLists"]
    if not datos:
        raise ValueError(f"sin clasificación para {temporada}")
    filas = []
    for st in datos[0]["DriverStandings"]:
        filas.append({
            "code": st["Driver"].get("code", "?"),
            "piloto": f"{st['Driver']['givenName']} {st['Driver']['familyName']}",
            "nacionalidad": st["Driver"].get("nationality"),
            "numero": st["Driver"].get("permanentNumber"),
            "posicion_final": pd.to_numeric(st["position"], errors="coerce"),
            "puntos": pd.to_numeric(st["points"], errors="coerce"),
            "victorias": pd.to_numeric(st["wins"], errors="coerce"),
            "equipo": ", ".join(c["name"] for c in st.get("Constructors", [])),
        })
    return pd.DataFrame(filas)


def f1_standings(temporada: int, forzar: bool = False) -> Resultado:
    return con_cache(f"f1_standings_{temporada}", lambda: _f1_standings(temporada), forzar=forzar)


def f1_calendario(temporada: int) -> pd.DataFrame:
    datos = _json(f"{F1_BASE}/{temporada}/races/", params={"limit": 30})["MRData"]["RaceTable"]["Races"]
    return pd.DataFrame([{"ronda": int(r["round"]), "carrera": r["raceName"],
                          "fecha": r.get("date")} for r in datos])


# ============================================================================
# 🏀 NBA — balldontlie v2 (requiere API key gratuita: https://www.balldontlie.io)
# ============================================================================
def _nba_promedios(api_key: str, temporada: int) -> pd.DataFrame:
    cab = {"Authorization": api_key.strip(), "Accept": "application/json"}
    datos = _json("https://api.balldontlie.io/v1/season_averages",
                  params={"season": temporada, "season_type": "regular"}, cabeceras=cab)
    registros = datos.get("data") or []
    if not registros:
        raise ValueError("balldontlie no devolvió promedios (¿key o temporada inválida?)")
    df = pd.DataFrame(registros)
    jug = df.get("player")
    if jug is not None:
        df["jugador"] = jug.apply(lambda p: f"{p.get('first_name','')} {p.get('last_name','')}".strip())
        df["equipo"] = jug.apply(lambda p: (p.get("team") or {}).get("full_name", "—"))
        df["posicion"] = jug.apply(lambda p: p.get("position", "—"))
    return df


def nba_promedios(api_key: str, temporada: int, forzar: bool = False) -> Resultado:
    return con_cache(f"nba_promedios_{temporada}",
                     lambda: _nba_promedios(api_key, temporada), forzar=forzar)


# ============================================================================
# Informe de estado de conexión
# ============================================================================
def probar_conexion() -> dict:
    """Chequeo rápido de conectividad con cada API (para el panel de estado)."""
    pruebas = {
        "Understat (fútbol)": lambda: _json("https://understat.com/main/getPlayersStats/",
                                            post={"league": "EPL", "season": "2025"},
                                            cabeceras={"X-Requested-With": "XMLHttpRequest"}) is not None,
        "MLB StatsAPI (béisbol)": lambda: _json("https://statsapi.mlb.com/api/v1/sports") is not None,
        "Jolpica F1": lambda: _json(f"{F1_BASE}/2026/driverstandings/", params={"limit": 1}) is not None,
    }
    estado = {}
    for nombre, fn in pruebas.items():
        try:
            estado[nombre] = bool(fn())
        except Exception as exc:                              # noqa: BLE001
            estado[nombre] = f"error: {type(exc).__name__}"
    return estado
