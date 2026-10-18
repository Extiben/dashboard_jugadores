"""
prueba_app.py — Ejecuta la app Streamlit de forma programática (streamlit.testing)
y verifica que las 4 secciones rendericen sin excepciones.

Ejecutar:  python prueba_app.py
"""
from __future__ import annotations

from streamlit.testing.v1 import AppTest

DEPORTES = ["⚽ Fútbol", "⚾ Béisbol (MLB)", "🏎️ Fórmula 1", "🏀 NBA"]
resultados: list[tuple[str, bool, str]] = []

for deporte in DEPORTES:
    print("─" * 78)
    print(f"▶ Renderizando: {deporte}")
    try:
        at = AppTest.from_file("app.py", default_timeout=180)
        at.run()
        if at.exception:
            raise RuntimeError(f"fallo en carga inicial: {[e.value for e in at.exception]}")

        at.sidebar.radio[0].set_value(deporte).run()
        if at.exception:
            raise RuntimeError(f"excepción al renderizar: {[e.value for e in at.exception]}")

        titulos = [t.value for t in at.subheader]
        metr = len(at.metric)
        dfs = len(at.dataframe)
        figs = len(at.get("plotly_chart"))
        tabs = len(at.tabs)
        descargas = len(at.get("download_button"))
        errores_ui = [e.value for e in at.error]
        avisos = [w.value for w in at.warning]

        detalle = (f"subtítulo='{titulos[0] if titulos else '—'}' · {metr} KPIs · "
                   f"{figs} gráficos Plotly · {dfs} tablas · {tabs} pestañas · "
                   f"{descargas} botones de descarga")
        print(f"   {detalle}")
        if errores_ui:
            print(f"   ⚠️ mensajes de error mostrados al usuario: {errores_ui}")
        if avisos:
            print(f"   ⚠️ avisos: {avisos[:2]}")
        assert titulos, "la sección no renderizó su subtítulo"
        if deporte.endswith("NBA"):
            # Sin API key la app debe explicar cómo obtenerla (no es un error)
            textos = " ".join(str(m.value) for m in at.info) + " ".join(str(m.value) for m in at.markdown)
            assert "balldontlie" in textos, "NBA no mostró instrucciones de API key"
            detalle += " · (sin key: muestra instrucciones, comportamiento esperado)"
        else:
            assert figs >= 1 or dfs >= 1, "no se renderizó ningún gráfico ni tabla"
        resultados.append((deporte, not errores_ui, detalle))
    except Exception as exc:                                  # noqa: BLE001
        resultados.append((deporte, False, f"{type(exc).__name__}: {exc}"))
        print(f"   ❌ {type(exc).__name__}: {exc}")

print("=" * 78)
print("RESUMEN DE PRUEBAS DE INTERFAZ")
print("=" * 78)
for deporte, ok, detalle in resultados:
    print(f"{'✅' if ok else '❌'} {deporte}: {detalle}")
print(f"\n{sum(1 for _, ok, _ in resultados if ok)}/{len(resultados)} secciones sin errores")
