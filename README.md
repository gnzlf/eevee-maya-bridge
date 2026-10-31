# Eevee Maya Bridge

Viewport experimental de **Blender Eevee dentro de un panel de Maya 2024** en Windows de 64 bits. Maya conserva la escena, cámaras, rigs y deformadores; un proceso Blender dibuja las mallas evaluadas y comparte color/profundidad por GPU con el panel.

## Instalar en otra máquina

**0.6.23 — respuesta al editar:** mover objetos, deformar o cambiar visibilidad activa correctamente la calidad interactiva. **Ajustes > Viewport > Ancho temporal al mover objetos o luces** permite elegir 640/960/1280/1920; al detenerse vuelve al ancho final y el playblast conserva sus dimensiones. El motor reutiliza buffers de hasta tres tamaños y evita reconfigurar una cámara o ajustes de Eevee que no cambiaron. Conserva AA, efectos y materiales. La caché consume memoria adicional para reducir las pausas al alternar resolución; no garantiza 30 FPS.

**0.6.22 — materiales y color:** recupera redes 2D de Maya como layeredTexture, rampas y ruido mediante muestreo UV de Maya con caché EXR flotante. Conserva los canales RGB/alpha de las imágenes, corrige la escala del bump y amplía los mapas de specular, base, coat y transmisión. El transporte GPU entrega color lineal a Maya: la vista, exposición y gamma nativas se aplican una sola vez. La pestaña HDRI añade un detalle mínimo de reflejos de 2048 por defecto, con opción 4096 o Nativo. La primera evaluación de una red procedural tiene coste de preparación; navegar y deformar reutiliza la caché. No equivale a ejecutar todos los shaders de Arnold.

1. Instala **Autodesk Maya 2024 de 64 bits** con su licencia.
2. Descarga el archivo `EeveeMayaBridge-<versión>-maya2024-win64-Setup.exe` desde [la última versión publicada](https://github.com/gnzlf/eevee-maya-bridge/releases/latest).
3. Ejecuta el instalador y pulsa **Instalar / actualizar**. Detecta Blender 5.2 existente o descarga Blender 5.2.0 portátil desde blender.org, verificando su SHA-256. No requiere pip, compiladores ni permisos de administrador.
4. Reinicia Maya. En **Windows > Settings/Preferences > Plug-in Manager**, carga `eeveeBridge.py`. Autoriza su ubicación si Maya lo pide; **Auto load** es opcional.
5. En el propio viewport, elige **Renderer > Eevee**. El cuadradito a su derecha abre los ajustes, incluso antes de iniciar el motor. Para salir, selecciona **Renderer > Viewport 2.0**.

El render de Eevee requiere OpenGL/OpenGL Core Profile. Desde 0.6.13, **Renderer > Eevee permanece visible también en DirectX 11**: muestra un aviso nativo y el cuadradito abre una ventana para configurar OpenGL Core Profile para el próximo inicio. Pulsa el botón, guarda tu trabajo y reinicia Maya. No cambia el contexto gráfico ni cierra la sesión automáticamente. Esta entrada de compatibilidad no renderiza Eevee con DirectX. Si una variable `MAYA_VP2_DEVICE_OVERRIDE` fuerza DirectX, la ventana indica que debe retirarse del lanzador o de Maya.env; no modifica esa variable automáticamente. [Configuración de Autodesk](https://help.autodesk.com/cloudhelp/2023/ENU/Maya-Rendering/files/GUID-EE108A86-9830-455E-BF2F-64A4075E8303.htm).

Probado con Maya 2024.2, Blender 5.2.0 LTS y RTX 3070. No utiliza CUDA ni núcleos RTX; el transporte actual requiere interoperabilidad WGL/D3D11 y solo se ha certificado en esta GPU/controlador NVIDIA. Otras versiones de Maya requieren recompilar y validar `eevee_scene.dll` con su SDK.

Si Eevee no aparece en Renderer, comprueba que `eeveeBridge.py` esté **Loaded** en Plug-in Manager. **Auto load** conserva la carga en próximos inicios. Con el plugin cargado puedes usar **Eevee > Restaurar opción Renderer > Eevee**; registra la opción sin arrancar Blender ni modificar la escena. El arranque automático también reintenta el registro si Viewport 2.0 todavía no está listo.

El instalador se entrega sin firma de código. Blender conserva sus avisos originales; consulta [componentes externos](THIRD_PARTY_NOTICES.md).

Si la versión 0.6.2 muestra `Unexpected Internal Failure` al descargar/cargar el plug-in, cierra Maya después de guardar tu trabajo, instala 0.6.3 o posterior y vuelve a iniciarlo. Se corrigió la limpieza de comandos tras fallos de Viewport 2.0 y se separó la carga del plug-in del registro gráfico en Maya. No es necesario borrar las preferencias de Maya.

Los errores detallados se guardan en `%LOCALAPPDATA%\EeveeMayaBridge\diagnostics\plugin_load.<PID>.json`, uno por proceso. Se conserva `plugin_load.json` para compatibilidad con diagnósticos anteriores; las pruebas batch ya no sustituyen ese último estado gráfico. Para obtener información de GPU y versión de Maya, arrastra `DIAGNOSTICO_EN_MAYA.py` desde la carpeta de la versión instalada a un viewport. Prefiere el registro del proceso actual y guarda `installation_report.json` en esa misma carpeta de diagnóstico; no abre ni guarda escenas.

## Actualizar

Maya consulta GitHub en segundo plano al cargar el menú Eevee. Si hay un release posterior, el menú muestra **Nueva versión X disponible…**. También puedes pulsar **Buscar actualizaciones…**.

Pulsa **Descargar e instalar**: el puente descarga el instalador del repositorio configurado, comprueba tamaño y SHA-256 informado por GitHub e inicia la instalación automáticamente mostrando su progreso. La instalación usa una carpeta por versión; **la nueva versión se activa al reiniciar Maya**. No sobrescribe las DLL de la sesión abierta ni cierra o guarda escenas. La versión anterior se conserva para poder volver a ella.

La instalación por usuario está en `%LOCALAPPDATA%\EeveeMayaBridge`. La configuración compartida permanece en `config.json`, fuera de `versions`, y se conserva al actualizar. El módulo de Maya se registra en Documents\maya\2024\modules. Si existía un módulo anterior, se conserva una copia antes de sustituirlo. Para volver manualmente a una versión anterior, apunta `EeveeMayaBridge.mod` a su carpeta en `versions`; se aplicará al siguiente inicio de Maya.

Para desinstalar, cierra Maya y Blender y usa **Aplicaciones instaladas de Windows > Eevee Maya Bridge**. Se retiran las versiones y el Blender portátil propio; no se elimina un Blender instalado por otro medio. Se conserva la configuración y se restaura el módulo previo cuando existe.

## Funciones

### Diagnóstico de bajo impacto (0.6.12)

- **Eevee > Guardar diagnóstico de rendimiento…** guarda los últimos 10 segundos de imágenes nuevas presentadas por GPU: resolución efectiva, muestras, modo de navegación/reproducción/playblast, distribución de tiempos y latencia desde el envío hasta el dibujo. No cuenta redibujos repetidos como imágenes nuevas. La latencia empieza después de evaluar y extraer la escena; no equivale a la latencia completa del usuario ni a la del monitor. El informe identifica muestras con resoluciones o calidades mezcladas y distingue frecuencia dentro de la muestra de frecuencia en la ventana completa. Sin imágenes nuevas no inventa FPS.
- **Eevee > Revisar materiales (solo lectura)…** muestra los materiales de la escena, incluidos los no asignados, y detecta familias sin traductor, conexiones no traducidas, texturas que el exportador no puede leer y canales aproximados. Los nombres aparecen en la ventana local; el JSON exportado conserva alias, sin nombres de materiales ni rutas de texturas. La revisión es limitada: ausencia de incidencias no certifica equivalencia con Arnold.

Estas herramientas se ejecutan al solicitarlas. El registro de solicitudes usa una cola limitada de metadatos y no conserva copias de geometría. No cambian parámetros de materiales, cámara, luces ni calidad de render y no activan Blender para revisar materiales. Para comparar rendimiento, mantén la misma escena y calidad, separa captura de interacción y desactiva la resolución adaptativa si quieres medir Full HD real. Se incluyen en el instalador 0.6.12.

El plan completo está en [DEFICIENCIAS_Y_MEJORAS.md](DEFICIENCIAS_Y_MEJORAS.md).

### Actualización de luces sin trabajo redundante (0.6.12)

Mover una luz o cambiar intensidad, cono o penumbra conserva sus colecciones de light linking y shadow linking cuando sus miembros siguen siendo iguales. Los vínculos se inicializan para luces nuevas y se actualizan al cambiar receptores, bloqueadores o reconstruir la escena. Esto también evita repetir el trabajo en las luces auxiliares del dropoff de Spot. No cambia muestras, resolución ni modelo de iluminación.

También se evita escribir de nuevo la visibilidad de luces y de la luz predeterminada cuando ya tienen el estado solicitado. Se conservan los modos nativos de luces seleccionadas, predeterminadas, iluminación plana y sin luces.

Se compararon doce casos contra la ruta anterior con imágenes idénticas, incluidos receptores vacíos, vínculos de sombras, eliminación/recreación de luces auxiliares y modos nativos de iluminación. La prueba también exige que los cambios reales de vínculos alteren la imagen. En una escena sintética de 400 mallas, la mediana de `sync_lights` pasó de aproximadamente 1,94 a 0,25 ms, con 50 muestras por ruta tras calentamiento. Es una medición de esa función en Blender; no certifica una mejora equivalente de FPS ni 30 FPS en producción.

### Estado del viewport

- Desde 0.6.21, el playblast sincroniza Eevee también cuando Maya utiliza otro panel interno para dibujar la captura offscreen. Antes podía reutilizar el último fotograma o escribir negro aunque el contador avanzara. Se valida que la cámara de captura corresponda al panel Eevee.
- Compatibilidad opcional con Prism: al cargar ambos plugins se adapta únicamente su operación de playblast para usar el panel Eevee y verificar todos los fotogramas. Conserva los nombres, versiones y conversión MP4 de Prism; no modifica los archivos de Prism. La opción QuickTime de Prism genera un MOV H.264/AAC mediante su FFmpeg, a partir de la captura AVI de Maya con audio, sin requerir QuickTime antiguo. La redirección de `cmds.playblast` se limita a esa operación y se restaura incluso si falla. Fuera de Eevee se conserva el comportamiento original de Prism.
- Desde 0.6.20, se conserva el par de matrices de vista/proyección de Maya sin introducir la compensación de vista dentro de la proyección. Esa compensación podía dejar un residuo numérico que hacía que Eevee tratara una cámara perspectiva como ortográfica y descartara iluminación Spot/Point por regiones. Se conserva el encuadre, incluidos gates y cámaras con escala heredada, y no se editan los atributos de la cámara.
- Spot y Point usan un alcance finito calculado desde sus receptores visibles y la atmósfera, independiente de la intensidad. Evita que el umbral automático de Eevee apague luces tenues antes de llegar a una superficie. No cambia la energía ni elimina la aproximación del decaimiento de Maya: los modos distintos del cuadrático siguen calibrados en Center of Illumination.
- Integración en el menú Renderer de Maya con su cuadradito de opciones. Los ajustes pueden abrirse sin arrancar Blender y permanecen abiertos al activar o desactivar Eevee. El menú superior Eevee conserva ajustes, recarga y actualizaciones; ya no ofrece los dos modos de apertura de panel.
- Desde 0.6.19, **Ajustes > HDRI** permite elegir una SkyDome existente, crear una con imagen o reemplazar su HDRI. Incluye Mostrar imagen de fondo, visibilidad del fondo, intensidad, exposición, rotación X/Y/Z, resolución de reflejos y espacio de color del nodo de imagen. Ocultar el fondo conserva iluminación y reflejos. Los campos editan los atributos nativos de Maya, admiten Undo/animación y respetan bloqueos; se guardan con la escena. La creación usa las reglas de color de Maya. Reemplazar una imagen compartida crea un nodo para la luz elegida y conserva las demás conexiones. Para iluminar con las SkyDome usa Todas las luces, o selecciónalas en el modo correspondiente.
- También se corrige `OpenSharedResource (0x80070057)` causado por liberar recursos durante cambios de resolución. Blender conserva cada generación anterior hasta que Maya confirma que ya no necesita sus fotogramas; después libera esa memoria. La prueba fuerza cuatro cambios de tamaño con importación demorada de las texturas y verifica su liberación posterior. No cambia la selección de GPU ni certifica otros fallos del controlador.
- Indicador animado dentro del viewport hasta recibir la primera imagen: muestra inicio, lectura de escena, materiales, geometría y preparación de shaders, con contadores reales cuando están disponibles y tiempo transcurrido. No estima un porcentaje ni tiempo restante. Cambiar a Viewport 2.0 cancela el arranque; los fallos muestran un mensaje en el viewport.
- Mallas evaluadas de Maya, cambios de puntos, normales, matrices y visibilidad. Maya ejecuta skinClusters, blendShapes, rigs y pesos pintados.
- Desde 0.6.16, el viewport GPU utiliza la **proyección real de Viewport 2.0**, en lugar de reconstruir el lente solo desde el FOV. Cambiar entre Renderer > Eevee y Viewport 2.0 conserva el encuadre sin escribir distancia focal ni transformación en la cámara de Maya. Incluye overscan, film fit, offsets, pan/zoom, film roll, post scale y cámara ortográfica con escala heredada. El color y la profundidad comparten esa proyección. El playblast toma la proyección de su destino real, que puede tener otra relación de aspecto que el panel visible.
- Desde 0.6.14, **Smooth Mesh Preview con 1 / 2 / 3**: Eevee recibe `outSmoothMesh` de Maya cuando el preview está activo. Respeta el nivel de subdivisión, UV, materiales por cara y creases de esa salida, también sobre deformaciones animadas. 1 vuelve a la malla base; 2 y 3 muestran la superficie suavizada. No añade nodos ni aplica un Smooth permanente. Cambiar el nivel o sus reglas reconstruye la geometría; la animación conserva los deltas de puntos. Más subdivisiones aumentan el coste de evaluación, transferencia y memoria.
- Sincronización de rutas al renombrar mallas, grupos o materiales y al cambiar la jerarquía. Espera y recuperación cuando Maya reconstruye la vista de un panel.
- Si un panel permanece sin vista gráfica durante tres segundos, su proceso Blender se cierra para liberar la escena de la GPU. El puente reconstruye el renderizador cuando vuelve el panel, conservando sus ajustes.
- Traducción parcial de standardSurface/aiStandardSurface y Lambert/Blinn/Phong, mapas file directos, UDIM y normales/bump directos. Ambient Color e Incandescence de materiales clásicos.
- Desde 0.6.18, las rutas de texturas con `<UDIM>` se resuelven contra sus tiles reales antes de comprobar el archivo. Antes se descartaba el mapa si el nombre contenía el token, dejando negros materiales cuyo color viene de esa textura. También se admiten rutas a un tile concreto y conjuntos cuyo primer tile existente es 1002. El diagnóstico comparte la misma lectura; los conjuntos vacíos continúan marcándose como ausentes. No se editan rutas ni materiales de Maya.
- Luces Point, Spot, Directional y Area; intensidad, exposición, cono, penumbra, sombras y participación volumétrica por luz.
- Desde 0.6.15 se detectan también **Area Light de Arnold (`aiAreaLight`) y Ambient Light de Maya**. Las áreas respetan dimensiones, Normalize y Legacy Intensity; las áreas de Arnold añaden exposición, apertura y disco/elipse. Su selección nativa y light linking utilizan los nombres originales de Maya.
- Ambient Light añade iluminación difusa por objeto, con color, intensidad y light linking. Ambient Shade mezcla un componente uniforme con una aproximación puntual desde la posición de la luz; al apagar la luz o excluir su receptor desaparece su contribución, sin encender una luz predeterminada ni modificar el fondo. El componente uniforme no reproduce las sombras de rayos ni la iluminación volumétrica de una ambient de Maya. Las áreas cilíndricas de Arnold se aproximan como rectángulos; no hay equivalencia fotométrica completa con Arnold.
- Desde 0.6.17, **Arnold SkyDome Light con HDRI lat-long** ilumina materiales y aparece en sus reflejos. Conecta un `.hdr` o `.exr` mediante un nodo `file` o `aiImage` directamente a Color de la SkyDome. El bridge utiliza el espacio de color del nodo; conserva el rango HDR, la intensidad, exposición y rotación del transform. Camera = 0 oculta el fondo y conserva iluminación/reflejos. Funciona con los materiales traducidos de Maya y Arnold, incluidas superficies metálicas y rugosas; no ejecuta el shader original de Arnold.
- La SkyDome respeta visibilidad y los modos nativos de luces del panel: Todas y Seleccionadas la utilizan; Predeterminadas, Sin luces e Iluminación plana la excluyen. Resolution de la SkyDome elige la resolución de la sonda mundial, redondeada hacia arriba entre 128 y 4096; varias domes usan la mayor. Mayor resolución consume más GPU/VRAM. Intensidad, exposición y rotación reutilizan el grafo y la imagen cargada; navegar y deformar no reconstruyen el entorno.
- En 0.6.22, **Ajustes > HDRI > Detalle mínimo de reflejos Eevee** permite aumentar esa resolución sin editar la SkyDome ni su resolución de Arnold. 2048 es el mínimo por defecto; 4096 aumenta el detalle en superficies pulidas. Nativo utiliza únicamente la resolución de las domes. Una roughness alta sigue desenfocando físicamente el reflejo aunque se aumente la resolución.
- El HDRI utiliza la sonda mundial de Eevee: no reproduce la oclusión interior, rebotes, sombras físicas, light linking por objeto ni pesos Diffuse/Specular independientes de una SkyDome de Arnold. No se traducen formatos Angular/Mirrored Ball, redes procedurales, utilidades ni ajustes UV/color de la textura como Color Gain, Offset o Flip. Usa la rotación del transform de la SkyDome para orientar el mapa. Los archivos ausentes, fuentes/formato no compatibles y espacios de color no disponibles dejan un aviso en el estado y diagnóstico del bridge. Las luces locales conservan su light linking.
- La caché nativa reutiliza puntos y normales de mallas que no se ensuciaron y pospone la evaluación de geometría oculta hasta mostrarla. Conserva los cambios de matrices y visibilidad. En una comparación de 14 poses de producción con 566 mallas (391 visibles), la mediana de extracción pasó de 62,4 a 43,3 ms; solo 41 mallas visibles necesitaron evaluar geometría por pose. Se alternó el orden de ambas rutas: posiciones idénticas, diferencia máxima en normales de 4,2e-7. Es una medición de extracción, no de FPS del viewport completo.
- Materiales Lambert mates y mapas de `specularColor` para Standard Surface, Arnold Standard Surface, Blinn y Phong. El mapa especular conserva las zonas oscuras de pupilas y otras superficies en lugar de reflejar blanco en toda la superficie.
- La transmisión del viewport usa una aproximación de transparencia con reflexión Fresnel para dejar visibles los objetos detrás de córneas o cristales. No simula la refracción óptica completa de Arnold. El backend de render separado conserva su BSDF de transmisión.
- El espacio lineal del render sigue ACEScg, Rec.709 o Rec.2020 de Maya, tanto para colores constantes como para texturas. La vista ACES 1.x de Maya se aproxima con ACES 1.3 de Blender; Un-tone-mapped usa Standard. Las configuraciones y vistas OCIO personalizadas todavía pueden diferir.
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

DOF y bloom son previews del puente, con posibles halos, no el bokeh/compositor completo de Blender. Los espacios y vistas de color comunes se traducen como se indica arriba, sin paridad completa con configuraciones OCIO personalizadas. Dropoff se aproxima mediante luces concéntricas adicionales; los modos de decaimiento no cuadráticos se calibran a una distancia de referencia. No se certifican vínculos por cara ni aislamiento volumétrico por objeto. No hay soporte completo para NURBS, pelo, partículas, proxies Arnold/USD, VDB, redes arbitrarias de Arnold, displacement, isolate select o motion blur. Smooth Mesh Preview utiliza el nivel de viewport; no sustituye el displacement ni el nivel de subdivisión de render de Arnold.

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

`probe_material_translation.py` también se ejecuta en el Maya gráfico dedicado de pruebas: comprueba Lambert, máscaras especulares, transmisión, material por defecto y colores por cara con una escena genérica.

`probe_native_startup.py` comprueba el menú Renderer y su cuadradito, la animación, cancelación y errores de inicio. `probe_startup_playblast.py` compara una captura pedida antes de terminar el arranque con la misma captura del motor ya iniciado.

`probe_material_audit.py` se ejecuta con `mayapy` en un proceso independiente. Crea una escena genérica temporal y comprueba detección de conexiones, texturas y canales, además de que la revisión conserva selección, tiempo, estado de modificación y Undo. No se conecta al Maya abierto del usuario.

`probe_diagnostics_gui.py` verifica las acciones reales del menú, la ventana y exportación de diagnósticos, y la presentación GPU en un perfil gráfico dedicado. Requiere `MAYA_APP_DIR` apuntando a un perfil nuevo llamado `diagnostics_regression_profile` y `EEVEE_DIAGNOSTICS_PROBE` a su carpeta padre. No se debe ejecutar dentro de una sesión de trabajo.

`probe_light_link_updates.py` se ejecuta con Blender en background. Compara el resultado de los vínculos antes y después de la optimización con renders de una escena genérica, y mide únicamente el coste de sincronizar luces.

`probe_release_gui.py` requiere un perfil gráfico nuevo `release_regression_profile`, `EEVEE_RELEASE_PROBE` apuntando a su carpeta padre y `EEVEE_PRODUCTION_SCENE` al archivo autorizado de prueba. Comprueba PNG/AVI Full HD, captura en frío y poses/captura de la escena suministrada sin guardarla ni ejecutar sus script nodes. No se ejecuta en la sesión de trabajo del usuario.

`probe_renderer_visibility_gui.py` usa un perfil nuevo `renderer_regression_profile`, `EEVEE_RENDERER_PROBE` con su carpeta padre y `EEVEE_RENDERER_PROBE_MODE=dx` o `gl`. Comprueba el registro diferido real, el menú nativo, el aviso DirectX sin iniciar Blender, el cambio explícito de preferencia y la activación con OpenGL tras reiniciar la sesión de prueba. Para forzar el backend DX en la prueba puede usarse `MAYA_VP2_DEVICE_OVERRIDE=VirtualDeviceDx11`; debe retirarse para la fase OpenGL. No se ejecuta en la sesión de trabajo del usuario.

Los artefactos quedan en `dist/`. Para publicar una nueva actualización:

1. Modifica el código y aumenta `__version__` en `scripts/eevee_maya/__init__.py`.
2. Ejecuta las pruebas correspondientes y confirma los cambios en Git.
3. Con GitHub CLI autenticado, publica una versión nueva con sus notas:

```powershell
./tools/publish_release.ps1 -Version 0.6.19 -NotesFile ./release-notes.md
```

El script construye los artefactos, sube `main` y crea el release. No reemplaza versiones ya publicadas. Los usuarios recibirán la oferta al volver a cargar Maya o al pulsar Buscar actualizaciones. También existe el workflow manual **Publicar versión** en GitHub Actions. Cada release conserva ZIP, instalador y SHA256SUMS.txt.
