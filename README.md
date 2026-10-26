# Eevee Maya Bridge

Viewport experimental de **Blender Eevee dentro de un panel de Maya 2024** en Windows de 64 bits. Maya conserva la escena, cámaras, rigs y deformadores; un proceso Blender dibuja las mallas evaluadas y comparte color/profundidad por GPU con el panel.

## Instalar en otra máquina

1. Instala **Autodesk Maya 2024 de 64 bits** con su licencia.
2. Descarga el archivo `EeveeMayaBridge-<versión>-maya2024-win64-Setup.exe` desde [la última versión publicada](https://github.com/gnzlf/eevee-maya-bridge/releases/latest).
3. Ejecuta el instalador y pulsa **Instalar / actualizar**. Detecta Blender 5.2 existente o descarga Blender 5.2.0 portátil desde blender.org, verificando su SHA-256. No requiere pip, compiladores ni permisos de administrador.
4. Reinicia Maya. En **Windows > Settings/Preferences > Plug-in Manager**, carga `eeveeBridge.py`. Autoriza su ubicación si Maya lo pide; **Auto load** es opcional.
5. Usa **Eevee > Activar en viewport actual**.

Maya debe utilizar OpenGL/OpenGL Core Profile. Si usa DirectX 11, cambia el motor en Preferences > Display y reinicia Maya. Probado con Maya 2024.2, Blender 5.2.0 LTS y RTX 3070. No utiliza CUDA ni núcleos RTX; el transporte actual requiere interoperabilidad WGL/D3D11 y solo se ha certificado en esta GPU/controlador NVIDIA. Otras versiones de Maya requieren recompilar y validar `eevee_scene.dll` con su SDK.

El instalador se entrega sin firma de código. Blender conserva sus avisos originales; consulta [componentes externos](THIRD_PARTY_NOTICES.md).

Si la versión 0.6.2 muestra `Unexpected Internal Failure` al descargar/cargar el plug-in, cierra Maya después de guardar tu trabajo, instala 0.6.3 o posterior y vuelve a iniciarlo. Se corrigió la limpieza de comandos tras fallos de Viewport 2.0 y se separó la carga del plug-in del registro gráfico en Maya. No es necesario borrar las preferencias de Maya.

Los errores detallados se guardan en `%LOCALAPPDATA%\EeveeMayaBridge\diagnostics\plugin_load.json`. Para obtener información de GPU y versión de Maya, arrastra `DIAGNOSTICO_EN_MAYA.py` desde la carpeta de la versión instalada a un viewport. Guarda `installation_report.json` en esa misma carpeta de diagnóstico; no abre ni guarda escenas.

## Actualizar

Maya consulta GitHub en segundo plano al cargar el menú Eevee. Si hay un release posterior, el menú muestra **Nueva versión X disponible…**. También puedes pulsar **Buscar actualizaciones…**.

Pulsa **Descargar e instalar**: el puente descarga el instalador del repositorio configurado, comprueba tamaño y SHA-256 informado por GitHub e inicia la instalación automáticamente mostrando su progreso. La instalación usa una carpeta por versión; **la nueva versión se activa al reiniciar Maya**. No sobrescribe las DLL de la sesión abierta ni cierra o guarda escenas. La versión anterior se conserva para poder volver a ella.

La instalación por usuario está en `%LOCALAPPDATA%\EeveeMayaBridge`. La configuración compartida permanece en `config.json`, fuera de `versions`, y se conserva al actualizar. El módulo de Maya se registra en Documents\maya\2024\modules. Si existía un módulo anterior, se conserva una copia antes de sustituirlo. Para volver manualmente a una versión anterior, apunta `EeveeMayaBridge.mod` a su carpeta en `versions`; se aplicará al siguiente inicio de Maya.

Para desinstalar, cierra Maya y Blender y usa **Aplicaciones instaladas de Windows > Eevee Maya Bridge**. Se retiran las versiones y el Blender portátil propio; no se elimina un Blender instalado por otro medio. Se conserva la configuración y se restaura el módulo previo cuando existe.

## Funciones

- Mallas evaluadas de Maya, cambios de puntos, normales, matrices y visibilidad. Maya ejecuta skinClusters, blendShapes, rigs y pesos pintados.
- Sincronización de rutas al renombrar mallas, grupos o materiales y al cambiar la jerarquía. Espera y recuperación cuando Maya reconstruye la vista de un panel.
- Si un panel permanece sin vista gráfica durante tres segundos, su proceso Blender se cierra para liberar la escena de la GPU. El puente reconstruye el renderizador cuando vuelve el panel, conservando sus ajustes.
- Traducción parcial de standardSurface/aiStandardSurface y Lambert/Blinn/Phong, mapas file directos, UDIM y normales/bump directos. Ambient Color e Incandescence de materiales clásicos.
- Luces Point, Spot, Directional y Area; intensidad, exposición, cono, penumbra, sombras y participación volumétrica por luz.
- Light linking por objeto y vínculos de sombras desde las relaciones de Maya; editor nativo accesible desde Ajustes > Luz.
- Controles reales del modelEditor para luces, sombras, AA, AO, texturas, material por defecto, wireframe y DOF Preview.
- **Ajustes > Sombras** permite elegir Baja (25%), Media (50%), Alta (100%, predeterminada) o Ultra (100% con más muestras de sombras suaves). Antes el visor estaba fijo al 50% y 128 MB. La memoria automática usa 128 / 256 / 512 / 1024 MB según el nivel; también puedes elegir 128–2048 MB manualmente para escenas con muchas luces. Eevee usa mapas virtuales: estos porcentajes no equivalen a un tamaño fijo de 2K/4K. Más memoria por sí sola no afila los bordes. Más calidad cuesta GPU y VRAM.
- La calidad de sombras se conserva durante la navegación y el playblast. El ancho temporal del preview todavía limita el detalle visible durante el movimiento. Los ajustes de sombras se guardan en las preferencias de Maya. El ángulo de sombra de Directional y el radio de Point/Spot controlan la suavidad desde Ajustes > Luz; el botón nativo de sombras y los interruptores por luz conservan el control de activación.
- Ajustes de cámara con Focus Distance, F Stop y Focal Length. **Enfocar la selección y activar DOF** enfoca la superficie visible de la malla seleccionada y activa los controles nativos necesarios. Los componentes conservan su profundidad seleccionada. **Enfocar un punto con un clic en el viewport** permite elegir un ojo o cualquier punto preciso; vuelve a la herramienta anterior después del clic. Q permite salir sin enfocar. Estos cambios admiten Undo.
- Atmósfera Eevee finita con densidad, color, anisotropía y alcance automático/manual. Bloom de pantalla.
- Playblast nativo sincronizado por fotograma, tanto para secuencias de imágenes como para vídeo: espera la pose evaluada y su imagen antes de capturar, aunque tarde más que el tiempo real. Probado en PNG y AVI a 1920×1080.
- Calidad adaptativa durante edición, navegación y reproducción: reduce temporalmente el ancho a 960 píxeles y conserva las muestras AA seleccionadas en Maya, incluido AA apagado. Al detenerse recupera la resolución configurada; el playblast usa siempre las dimensiones y calidad de captura. Se puede desactivar en Ajustes. Conservar más muestras durante el movimiento tiene coste de GPU.
- Navegación rápida de cámara: con calidad adaptativa activa, usa temporalmente 640 píxeles por defecto al navegar manualmente. **Ajustes > Viewport > Ancho temporal al navegar** permite elegir 320–1920 o desactivar este modo. Conserva AA y efectos; recupera la resolución al detenerse. La animación y el scrubbing no activan este modo de navegación.
- La sincronización también se ejecuta en el dibujo nativo del panel, sin esperar exclusivamente a eventos de Qt. El volumen reutiliza los límites de las mallas durante movimientos de cámara y los invalida ante cambios de geometría, transformaciones o visibilidad.
- Activación del puente al elegir Eevee directamente desde el menú Renderer del viewport.

Para un playblast Full HD, configura 1920×1080 y 100 % en las opciones nativas; activa **Render offscreen** si el panel visible es menor. El tamaño configurado en los ajustes interactivos no limita la captura. Si el renderizador falla o supera 120 segundos por fotograma, el puente muestra un aviso, marca los fotogramas fallidos en rojo y registra el error en `playblast.json` dentro de la sesión de diagnóstico. Maya puede conservar un archivo parcial: esa captura no es válida. Para automatizar y recibir también una excepción de Python, usa `from eevee_maya.capture import playblast` en lugar de `cmds.playblast`.

**Sigue siendo experimental. No reproduce todas las funciones de Eevee, Maya ni Arnold y no garantiza 30 FPS.** La prueba de producción de aproximadamente un millón de vértices dio 13.8 actualizaciones/s a 640×409 y 13.1 a 1920×1227 con AO, AA de 2 muestras, sombras, DOF, bloom y volumen. La evaluación y sincronización de deformaciones todavía tienen coste de CPU.

DOF y bloom son previews del puente, con posibles halos, no el bokeh/compositor completo de Blender. Se usa AgX, sin paridad OCIO con Maya. Dropoff se aproxima mediante luces concéntricas adicionales; los modos de decaimiento no cuadráticos se calibran a una distancia de referencia. No se certifican vínculos por cara ni aislamiento volumétrico por objeto. No hay soporte completo para NURBS, pelo, partículas, proxies Arnold/USD, VDB, redes arbitrarias de Arnold, displacement, smooth mesh preview, isolate select o motion blur.

## Desarrollar y publicar desde esta carpeta

El código propio está en `scripts/`, `blender/`, `plug-ins/` y `native/`. Los dos DLL necesarios para Maya 2024 se incluyen en `bin/`; no se distribuye el SDK de Autodesk. Para recompilarlos, usa Visual Studio 2022, Windows SDK, CMake y los headers/libs de tu instalación Maya 2024:

```powershell
cmake -S native -B native/build -A x64 -DMAYA_ROOT="C:/Program Files/Autodesk/Maya2024"
cmake --build native/build --config Release
```

Para probar el código de la carpeta sin instalar una distribución, ejecuta `install.ps1`. Para empaquetar un ZIP y el instalador EXE, Windows debe tener .NET Framework 4.x y Python 3.10 o posterior:

```powershell
python -m unittest discover -s tests/distribution -v
python tools/build_release.py
```

Con `mayapy` también puedes ejecutar `tests/distribution/probe_scene_changes.py`, `probe_light_links.py` y `probe_focus.py`: crean escenas temporales para verificar jerarquía, vínculos y enfoque de superficies, incluidas deformaciones, unidades y escala de cámara. `probe_native_playblast.py`, `probe_focus_gui.py`, `probe_navigation_callback.py` y `probe_shadow_quality.py` se ejecutan dentro de una sesión gráfica de Maya dedicada a pruebas; crean escenas temporales para comprobar captura, enfoque, calidad de sombras y sincronización por dibujo nativo con el temporizador Qt detenido. No los ejecutes en una sesión con trabajo sin guardar. `probe_volume_bounds.py` se ejecuta con Blender en background para comprobar el cálculo de límites de la atmósfera.

Los artefactos quedan en `dist/`. Para publicar una nueva actualización:

1. Modifica el código y aumenta `__version__` en `scripts/eevee_maya/__init__.py`.
2. Ejecuta las pruebas correspondientes y confirma los cambios en Git.
3. Con GitHub CLI autenticado, publica una versión nueva con sus notas:

```powershell
./tools/publish_release.ps1 -Version 0.6.9 -NotesFile ./release-notes.md
```

El script construye los artefactos, sube `main` y crea el release. No reemplaza versiones ya publicadas. Los usuarios recibirán la oferta al volver a cargar Maya o al pulsar Buscar actualizaciones. También existe el workflow manual **Publicar versión** en GitHub Actions. Cada release conserva ZIP, instalador y SHA256SUMS.txt.
