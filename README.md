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
- Traducción parcial de standardSurface/aiStandardSurface y Lambert/Blinn/Phong, mapas file directos, UDIM y normales/bump directos. Ambient Color e Incandescence de materiales clásicos.
- Luces Point, Spot, Directional y Area; intensidad, exposición, cono, penumbra, sombras y participación volumétrica por luz.
- Light linking por objeto y vínculos de sombras desde las relaciones de Maya; editor nativo accesible desde Ajustes > Luz.
- Controles reales del modelEditor para luces, sombras, AA, AO, texturas, material por defecto, wireframe y DOF Preview.
- Ajustes de cámara con Focus Distance, F Stop y Focal Length, más **Enfocar la selección**. El DOF requiere activar Depth of Field de la cámara y DOF Preview del panel.
- Atmósfera Eevee finita con densidad, color, anisotropía y alcance automático/manual. Bloom de pantalla.

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

Con `mayapy` también puedes ejecutar `tests/distribution/probe_scene_changes.py`: crea una escena temporal de prueba y verifica cambios de nombres, jerarquía y avisos durante reproducción, sin acceder a otra sesión de Maya.

Los artefactos quedan en `dist/`. Para publicar una nueva actualización:

1. Modifica el código y aumenta `__version__` en `scripts/eevee_maya/__init__.py`.
2. Ejecuta las pruebas correspondientes y confirma los cambios en Git.
3. Con GitHub CLI autenticado, publica una versión nueva con sus notas:

```powershell
./tools/publish_release.ps1 -Version 0.6.3 -NotesFile ./release-notes.md
```

El script construye los artefactos, sube `main` y crea el release. No reemplaza versiones ya publicadas. Los usuarios recibirán la oferta al volver a cargar Maya o al pulsar Buscar actualizaciones. También existe el workflow manual **Publicar versión** en GitHub Actions. Cada release conserva ZIP, instalador y SHA256SUMS.txt.
