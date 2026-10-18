# 📊 Dashboard interactivo de estadísticas de jugadores

Dashboard multideporte construido con **Python + Pandas + Plotly + Streamlit**, que
consume **4 APIs públicas** de datos deportivos en vivo, calcula métricas derivadas
(xG, percentiles, ISO, FIP, consistencia…) y permite explorar, comparar y descargar
las estadísticas de los jugadores.

```
⚽ Fútbol  ·  ⚾ MLB  ·  🏎️ Fórmula 1  ·  🏀 NBA
```

---

## 🚀 Cómo ejecutarlo

```bash
# 1. Instalar dependencias
pip install -r requirements.txt

# 2. Lanzar el dashboard
cd dashboard_jugadores
streamlit run app.py
```

Se abre en `http://localhost:8501`. **No se necesita ninguna API key** para fútbol,
MLB y F1; solo la sección de NBA la pide (ver abajo).

---

## 🧱 Arquitectura del proyecto

| Archivo | Responsabilidad |
|---|---|
| `app.py` | Interfaz Streamlit: sidebar de control, 4 secciones deportivas, KPIs, pestañas, comparadores y descargas |
| `fuentes.py` | Clientes de las APIs + motor de caché (Parquet, TTL 3 h) y *fallback* a datos guardados si una API cae |
| `analitica.py` | Todo el trabajo con **Pandas**: tipos, métricas derivadas, percentiles, correlaciones, normalización por 90 min / 600 PA |
| `graficos.py` | 16 fábricas de figuras **Plotly** reutilizables (barras, burbujas, radar, heatmaps, cajas, donas, líneas acumuladas…) |
| `prueba_pipeline.py` | Verificación end-to-end: descarga real → Pandas → todas las figuras → reporte |
| `prueba_app.py` | Verificación de la interfaz con `streamlit.testing.AppTest` (las 4 secciones) |
| `data/cache/` | Snapshots Parquet de cada dataset (caché + respaldo offline) |

### Flujo de datos

```
API pública ──► fuentes.py (requests + caché Parquet + reintentos)
                     │
                     ▼
              analitica.py (Pandas: limpieza, métricas, percentiles)
                     │
                     ▼
              graficos.py (Plotly)  +  tablas y descargas CSV
                     │
                     ▼
                 app.py (Streamlit)
```

### Resiliencia (3 niveles)

1. **Caché en disco** con TTL de 3 horas → navegación instantánea y respeto por las APIs.
2. **Reintentos** con backoff si la red falla temporalmente.
3. **Modo respaldo**: si la API no responde, se usan los últimos datos guardados y se
   avisa en pantalla (🟠 amarillo/naranja en la ficha de origen).

---

## 🌐 Fuentes de datos (todas gratuitas y verificadas)

| Deporte | API | Qué aporta |
|---|---|---|
| ⚽ Fútbol | [Understat](https://understat.com) | Goles, asistencias, **xG**, **xA**, tiros, pases clave por jugador (EPL, La Liga, Bundesliga, Serie A, Ligue 1, RFPL) |
| ⚽ Bundesliga | [OpenLigaDB](https://api.openligadb.de) | Goleadores oficiales y tabla — usado para *contrastar* los datos de Understat |
| ⚾ Béisbol | [MLB StatsAPI](https://statsapi.mlb.com) | Bateo y pitcheo oficiales de la MLB (todas las temporadas), líderes por categoría |
| 🏎️ F1 | [Jolpica-F1](https://api.jolpi.ca) | Resultados carrera por carrera, clasificación de pilotos y calendario (sucesor comunitario de Ergast) |
| 🏀 NBA | [balldontlie](https://www.balldontlie.io) | Promedios por partido (requiere API key gratuita) |

> **Cómo obtener la API key de NBA (2 minutos):** regístrate en <https://www.balldontlie.io>,
> copia la key y pégala en la sección 🏀 del dashboard (se guarda en `data/.api_key_nba`).
> Si tu plan es gratuito y la temporada más reciente no está disponible, prueba 2024 o 2023.

---

## 🧭 Qué contiene cada sección

Cada deporte tiene 4 pestañas: **Rankings · Comparador · Explorador · Datos y descarga**.

- **⚽ Fútbol** — rankings por goles/xG/asistencias, gráfico de *sobre-rendimiento*
  (`goles − xG`: quién define por encima de lo esperado), radar de percentiles,
  correlaciones y contraste opcional con OpenLigaDB.
- **⚾ MLB** — bateo y pitcheo con umbral de participación ajustable, métricas derivadas
  (`ISO`, `K%`, `BB%`, `BABIP`, `HR/600`, `K/9`, `FIP` aprox.), radar por liga y
  líderes oficiales por categoría.
- **🏎️ F1** — puntos, victorias, podios, abandonos, posición media, puestos ganados
  respecto a la parrilla, evolución acumulada por ronda y heatmap piloto × circuito.
- **🏀 NBA** — máximos anotadores, `TS%`/`eFG%`, correlaciones y comparador.

Extras comunes: KPIs resumen, filtros por liga/temporada/equipo/posición, temas
claro/oscuro, botón **🔄 Actualizar datos** (ignora la caché), estado de conexión de
las APIs y descarga CSV de cualquier dataset.

---

## ✅ Validación (datos reales, 27-09-2026)

`prueba_pipeline.py` → **29/29 pruebas OK**; `prueba_app.py` → **4/4 secciones sin errores**.

| Deporte | Resultado de la verificación |
|---|---|
| ⚽ EPL 2026/27 (5 jornadas) | 421 jugadores · máximo goleador Haaland (5) · correlación goles–xG **0.764** |
| ⚽ Bundesliga 2025/26 | 499 jugadores · 67 goleadores cruzados con la fuente oficial (Luis Díaz: 15 goles ↔ 14.9 xG) |
| ⚾ MLB 2026 | 757 bateadores y 868 pitchers · líder en HR Pete Crow-Armstrong (45) · mejor ERA Louis Varland (1.27) |
| 🏎️ F1 2026 | 330 resultados en 15 rondas · líder Andrea Kimi Antonelli (302 pts, 8 victorias, 12 podios) |

Rendimiento: con caché en disco, cada sección se renderiza en **menos de 3 segundos**
(la primera consulta a las APIs tarda algo más).

---

## 🔧 Notas técnicas

- Los *datasets* se normalizan por volumen de juego (por 90 minutos en fútbol, por 600
  apariciones al plato en MLB) para evitar sesgos por minutos jugados.
- Los percentiles se calculan **dentro de la liga o posición** para comparaciones justas.
- `streamlit` ≥ 1.50 usa la nueva API de ancho (`width="stretch"`); el código se adapta
  automáticamente a versiones anteriores.
- La recta de tendencia se calcula con **NumPy** (`polyfit`, mostrando R²) para no
  depender de `statsmodels`.
- Las APIs de NBA (stats.nba.com), ESPN y SofaScore **bloquean** peticiones automatizadas
  desde servidores, por eso la sección NBA usa balldontlie con key de usuario.

## 💡 Ideas para extender

- Añadir **EuroLeague** (API XML pública, sin key) como alternativa de baloncesto.
- Programar la actualización de la caché con `cron`/Airflow y notificar cambios.
- Modelo de predicción de xG propio o de puntos por carrera con scikit-learn.
