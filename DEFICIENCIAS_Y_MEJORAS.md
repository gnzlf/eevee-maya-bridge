# Eevee Maya Bridge: deficiencias y plan de mejora

**Actualizado:** 27 de octubre de 2026. **Base revisada:** bridge 0.6.13, Maya 2024 y Blender 5.2.0 en Windows.

Este informe describe el estado del código y las verificaciones disponibles. Distingue funciones implementadas, compatibilidad parcial y propuestas pendientes. Las metas de rendimiento son objetivos de desarrollo, no resultados ya alcanzados.

### Primera etapa aplicada: cambios de bajo impacto — 27 de octubre de 2026

La versión 0.6.12 añade diagnóstico manual de rendimiento y revisión de materiales en modo lectura desde el menú Eevee. El informe utiliza solicitudes y dibujos identificados, muestra resolución efectiva, separa captura de interacción y evita contar redibujos como imágenes nuevas. La revisión detecta conexiones sin traducción y archivos que el exportador no puede leer. Sus informes exportados omiten nombres de materiales y rutas de texturas.

Esta etapa no cambia el render, los shaders, las conversiones de luces ni el comportamiento del desenfoque. Todavía no optimiza esos subsistemas ni demuestra 30 FPS. La validación de materiales se ejecuta sobre una escena genérica en un proceso independiente de Maya. Se incluye en el instalador 0.6.12.

La interfaz se verificó después en una sesión gráfica dedicada de Maya: doce comprobaciones satisfactorias, incluidos botones reales de menú, ventana visible, exportación, cancelación y fotogramas GPU. Se inspeccionó una captura de la ventana. La revisión de materiales pasó además siete comprobaciones en Maya 2024 independiente.

### Segunda etapa aplicada: sincronización de vínculos de luces — 27 de octubre de 2026

Se omite la reasignación de colecciones de light linking y shadow linking al editar una luz si los receptores y bloqueadores siguen iguales. Las luces nuevas, cambios de miembros, listas vacías y reconstrucciones de escena mantienen la inicialización o invalidación correspondiente. La optimización incluye las luces auxiliares usadas para aproximar el dropoff de Spot y conserva la calidad de render.

También se evitan escrituras de visibilidad cuando las luces y la luz predeterminada ya tienen el estado solicitado. En una escena sintética de 400 mallas, doce comparaciones entre la ruta optimizada y la anterior dieron diferencia máxima de píxeles cero. Se incluyeron movimiento/intensidad, receptores parciales y vacíos, exclusión de bloqueadores, recreación de luces auxiliares y modos de iluminación seleccionada, predeterminada, plana y sin luces. Otros controles exigen iluminación visible y cambios reales en la imagen al modificar los vínculos. La mediana de la función `sync_lights` bajó de 1,94 a 0,25 ms en esa prueba, con 50 muestras por ruta después de calentamiento. No es una medición de FPS ni una certificación de rendimiento en escenas de producción.

La validación incluye pruebas automatizadas, doce comprobaciones de interfaz gráfica, siete de revisión de materiales, cinco de vínculos nativos de Maya con Undo/Redo y comparaciones de sincronización/render en Blender. Las comprobaciones del instalador se ejecutan sobre directorios de prueba, sin sustituir la instalación de la sesión del usuario. Las dos etapas forman parte de 0.6.12.

Para la distribución 0.6.12 pasaron las 77 pruebas automatizadas con la prueba de instalación activada, además de ocho comprobaciones del plugin instalado y sus DLL. Se verificaron captura PNG/AVI a 1920 × 1080, captura en frío y una escena de producción de 566 mallas en un proceso de Maya dedicado. La prueba de producción conserva el archivo original; sigue sin certificar 30 FPS.

## 1. Diagnóstico principal

**Corrección de registro en 0.6.13:** antes se omitía el registro del renderer en DirectX 11 y no se reintentaba si Viewport 2.0 aún no estaba listo. Ahora se registra una entrada de compatibilidad visible en DirectX, con aviso nativo y configuración explícita de OpenGL para el siguiente inicio. No utiliza el transporte OpenGL desde DirectX. Se añaden reintentos acotados y una opción manual para restaurar el registro. La prueba gráfica comprueba catorce condiciones con DirectX real y ocho con OpenGL tras reiniciar el perfil de prueba. Los registros por proceso evitan confundir los diagnósticos de las pruebas batch con los del Maya del usuario.

El bridge ya integra Eevee en el menú Renderer de Maya, pero todavía no ofrece equivalencia completa con los materiales, cámaras y luces de Maya/Arnold, ni ha demostrado 30 FPS sostenidos a 1920 × 1080 con todos los efectos en una escena grande.

Las principales deficiencias que se pueden corregir están en la traducción de materiales, los efectos de pantalla, la sincronización incremental y el tiempo entre una edición y su presentación. Instalar más bibliotecas de Blender no resuelve esos problemas: hace falta mejorar el código que conecta ambos programas.

“Sentirse nativo” requiere varias cosas a la vez: controles coherentes, respuesta rápida, imagen estable, selección y manipuladores correctos, captura fiable y recuperación de errores. La integración del menú ya está resuelta; la equivalencia visual y la latencia necesitan más trabajo.

## 2. Cómo funciona actualmente

```text
Maya evalúa escena, rigs y deformadores
    ↓
Bridge extrae geometría evaluada, cámara, luces y materiales
    ↓ memoria compartida y mensajes de control
Blender mantiene una copia de la escena y renderiza con Eevee
    ↓ color y profundidad compartidos por GPU
MRenderOverride presenta la imagen y los elementos de interfaz de Maya
```

Blender se ejecuta en un proceso separado. El color y la profundidad utilizan transporte por GPU; la evaluación del rig y parte de la preparación y sincronización siguen consumiendo CPU. El bridge no ejecuta skinClusters ni redes de Arnold dentro de Eevee.

La presentación usa la extensión oficial `MRenderOverride` de Viewport 2.0. Esa API permite definir operaciones de dibujo y su ciclo de vida, pero no convierte automáticamente los shaders de Maya a shaders de Blender. [Referencia oficial de Autodesk](https://help.autodesk.com/cloudhelp/2024/ENU/MAYA-API-REF/cpp_ref/class_m_h_w_render_1_1_m_render_override.html).

## 3. Limitaciones del propio Eevee

Estas restricciones pertenecen al motor y no deben confundirse con errores del bridge:

| Área | Restricción del motor | Consecuencia para el bridge |
|---|---|---|
| Efectos de pantalla | Utilizan profundidad visible; faltan superficies ocultas y fuera del encuadre. | Puede haber pérdidas en bordes y oclusiones. |
| Transparencia y refracción | Hay restricciones según el modo del material; la refracción tiene aproximaciones. | No puede prometerse equivalencia óptica con Arnold. |
| Volúmenes | Dispersión simple y restricciones de participación en reflejos/refracciones. | La atmósfera tiene límites físicos y visuales. |
| Sombras | Pueden aparecer fugas con geometría delgada o solapada. | Hay que calibrar geometría y parámetros, además de resolución. |
| Materiales | Los BSDF usan aproximaciones para mantener velocidad. | Igualar valores no garantiza igual apariencia. |
| Recursos | La preparación de geometría requiere CPU; la memoria gráfica es limitada. | Compartir imágenes por GPU no elimina los demás costes. |

Fuente: [limitaciones oficiales de Eevee, manual 5.2](https://docs.blender.org/manual/en/latest/render/eevee/limitations/limitations.html), consultado en la fecha del informe. La página `latest` puede cambiar; no deben aplicarse límites de Eevee 3.x a este bridge.

Estas restricciones no significan que Eevee carezca de desenfoque, volúmenes o materiales avanzados. Parte de esas funciones existe en Blender y todavía no se aprovecha completamente en esta integración.

## 4. Deficiencias del bridge y mejoras concretas

### 4.1 Rendimiento y respuesta durante la edición

**Estado actual.** Hay sincronización incremental de geometría, transporte de imagen por GPU, callbacks de dibujo y resolución adaptativa. Durante edición se limita normalmente el ancho a 960 píxeles; al navegar manualmente, a 640 por defecto. Al detenerse se recupera la resolución configurada. Se mantienen los ajustes de AA y efectos.

**Deficiencia.** Una imagen que llega por GPU puede seguir siendo tardía si Maya evalúa lentamente, se reconstruye la escena, Blender actualiza recursos o el render tarda demasiado. Bajar temporalmente la resolución mejora la interacción, pero no demuestra rendimiento Full HD.

**Mejoras recomendadas:**

1. Medir por separado evaluación de Maya, extracción, copia de geometría, espera, actualización de Blender, render, profundidad compartida y presentación.
2. Añadir identificadores de edición, pose, cámara y recursos para conocer la antigüedad exacta de cada imagen.
3. Actualizar únicamente puntos, normales, matrices, luces o materiales que cambiaron. Una modificación de intensidad no debería reconstruir geometría.
4. Separar cambios de material de cambios estructurales: algunos eventos de materiales actualmente marcan la escena para reconstrucción.
5. Mantener recursos persistentes y agrupar transferencias. Investigar instancias y datos compartidos para escenarios repetitivos.
6. Mantener una cola corta al editar y descartar solicitudes superadas antes de renderizar. En captura, conservar cada fotograma requerido.
7. Optimizar primero las etapas medidas como dominantes. Llevar código a C++ solo cuando reduzca un coste identificado.

La API de Maya debe consultarse desde contextos compatibles con su modelo de ejecución. Añadir hilos que llamen indiscriminadamente a `cmds` o a la API no constituye una optimización segura.

**Código relevante:** `ui.py`, `engine.py`, `changes.py`, `scene_stream.py` dentro de `scripts/eevee_maya/`; `native/scene_stream.cpp`; `blender/scene_sync.py`; `blender/viewport_worker.py`.

### 4.2 Materiales de Maya y Arnold

**Estado actual.** Se traducen parcialmente Lambert, Blinn, Phong, Standard Surface y Arnold Standard Surface, con texturas file directas, UDIM y conexiones sencillas de normal/bump. Ya se corrigieron el brillo indebido de Lambert y las máscaras de color especular.

**Deficiencia.** Traducir algunos atributos no equivale a ejecutar el grafo original. Redes con mezclas, utilidades, texturas procedurales y modelos de dispersión pueden perder conexiones o cambiar de aspecto. No hay soporte completo de redes arbitrarias de Arnold, displacement o materiales especiales.

**Mejoras recomendadas:**

- Crear una representación intermedia del grafo, con registro explícito de nodos y conexiones compatibles.
- Ampliar la traducción por familias verificables: color y mezclas, remapeos, coordenadas UV, normales, emisión, capas y dispersión subsuperficial.
- Mostrar un diagnóstico por material: conexiones traducidas, aproximadas e ignoradas. Evitar que un material incompatible parezca correcto sin avisar.
- Implementar cambios incrementales de parámetros y texturas sin reconstruir toda la escena.
- Ofrecer horneado opcional para redes difíciles, indicando que no reemplaza efectos dependientes de vista, luz o tiempo.
- Comparar con referencias de Maya/Arnold usando escenas genéricas de ojos, piel, metal, vidrio y transparencias superpuestas.

**Código relevante:** `scripts/eevee_maya/exporter.py`, `scripts/eevee_maya/changes.py`, `blender/worker.py`.

### 4.3 Desenfoque y autofoco

**Estado actual.** El bridge recoge Focus Distance, F Stop y Focal Length. El autofoco utiliza la superficie evaluada visible y permite elegir un punto con un clic. En el camino interactivo, el DOF de la cámara de Blender se desactiva y se utiliza un efecto propio basado en profundidad compartida.

**Deficiencia.** Ese efecto no reproduce completamente el bokeh y la oclusión de un desenfoque óptico. Una sola capa de profundidad no describe simultáneamente córnea, iris, fondo y transparencias. Enfocar la superficie correcta tampoco garantiza por sí solo que el desenfoque aplicado sea correcto.

**Mejoras recomendadas:**

1. Validar unidades, profundidad lineal, escalas heredadas de cámara, film aperture, film fit, recorte y desplazamientos con patrones de distancias conocidas.
2. Mostrar temporalmente el punto y la distancia elegidos por el autofoco para poder comprobarlos.
3. Separar desenfoque cercano y lejano mediante círculo de confusión, con tratamiento de bordes y cobertura.
4. Evaluar varias capas de profundidad o una solución específica para transparencias.
5. Investigar el DOF de Eevee en el render interactivo y comparar calidad y coste contra el efecto actual antes de sustituirlo.
6. Mantener una referencia visual común entre interacción y playblast; documentar cualquier modo de calidad diferente.

**Código relevante:** `scripts/eevee_maya/focus.py`, `scripts/eevee_maya/exporter.py`, `blender/viewport_worker.py`, `native/gpu_bridge.cpp`, `shaders/EeveeBlit.ogsfx`.

### 4.4 Luces, conos y volumetría

**Estado actual.** Hay Point, Spot, Directional y Area, controles nativos de intensidad, exposición, cono, penumbra, sombras y participación volumétrica. Existen light linking y shadow linking por objeto. El dropoff del spot se aproxima mediante luces concéntricas adicionales; la atenuación no cuadrática se calibra a una distancia de referencia.

**Deficiencia.** Los modelos de intensidad, atenuación y distribución angular no son idénticos. Las luces auxiliares aumentan el coste y no sustituyen una distribución angular continua. No están certificados los vínculos por cara ni la exclusión volumétrica por objeto. La atmósfera no traduce cualquier red volumétrica de Arnold.

**Mejoras recomendadas:**

- Definir una conversión documentada de unidades e intensidad para cada tipo de luz.
- Verificar orientación, escala y jerarquía de luces con pruebas de Directional desde arriba, abajo y laterales.
- Calibrar cone angle, penumbra y dropoff con perfiles de iluminación medidos sobre un plano y dentro de niebla.
- Investigar un perfil de atenuación angular que reduzca la necesidad de luces auxiliares; puede requerir cambios en Blender, no solo Python.
- Revisar coherencia entre luz visible, sombra y participación en el volumen al editar parámetros.
- Conservar los modos nativos de luces seleccionadas, todas las luces y luz predeterminada; probar cambios de selección sin reconstrucción completa.
- Añadir control de calidad volumétrica y presupuesto temporal, con límites automáticos estables que no salten al mover la cámara.

**Código relevante:** `scripts/eevee_maya/exporter.py`, `scripts/eevee_maya/light_links.py`, `blender/worker.py`, `blender/scene_sync.py`.

### 4.5 Antialiasing y estabilidad temporal

**Estado actual.** Se conserva el número de muestras seleccionado en Maya durante el movimiento. La reproyección temporal de Eevee está desactivada en el camino interactivo para evitar arrastrar imágenes de estados independientes de Maya.

**Deficiencia.** Sin un historial temporal fiable, personajes, pelo representado como geometría, detalles finos y sombras pueden presentar ruido o parpadeo. Aumentar muestras mejora algunos casos, con coste de GPU.

**Mejoras recomendadas:** mantener identificadores estables de objetos, matrices y geometría anterior; investigar vectores de movimiento y rechazo de historial en zonas descubiertas. Invalidar el historial ante cortes de cámara, cambios de topología, materiales y luces. Comparar esa solución con AA espacial a coste equivalente. Activar reproyección sin resolver la validez del historial puede recuperar el ghosting.

**Código relevante:** `blender/viewport_worker.py`, `scripts/eevee_maya/native_controls.py`, `scripts/eevee_maya/quality.py`.

### 4.6 Sombras y ambient occlusion

**Estado actual.** Ya hay ajustes Baja, Media, Alta y Ultra; Alta es el valor predeterminado. Se controla resolución relativa, muestras y memoria. El AO del camino compartido por GPU utiliza profundidad de pantalla.

**Deficiencia.** La calidad visible depende también de la resolución temporal de interacción, tamaño del emisor, muestras, alcance y geometría. El AO de pantalla no sustituye iluminación indirecta completa y puede producir halos. Los ajustes nativos de sombras por luz todavía no tienen equivalencia completa.

**Mejoras recomendadas:** exponer únicamente controles con efecto real y explicar sus unidades; añadir diagnóstico de presupuesto de sombras; calibrar contactos y fugas con escenas pequeñas; mejorar AO con profundidad y normales coherentes y muestreo estable. Probar cada mejora con luces explícitas: la luz predeterminada del visor no sirve para evaluar sombras reales.

Los mapas de sombras son virtuales: subir la memoria a 2 GB no equivale a seleccionar sombras 4K ni garantiza mayor nitidez. La calidad Ultra debe ser una opción con coste visible, no una solución universal.

**Código relevante:** `scripts/eevee_maya/shadow_quality.py`, `blender/viewport_worker.py`, `native/gpu_bridge.cpp`.

### 4.7 Bloom y emisión selectiva

**Estado actual.** El bloom utiliza el brillo de la imagen de pantalla y un umbral. No identifica si ese brillo procede de emisión, iluminación o reflejos.

**Deficiencia.** Un objeto claro puede generar halo aunque no sea emisivo. No está implementada la petición de limitar el bloom exclusivamente a materiales con emisión alta.

**Mejora recomendada.** Transportar una contribución o máscara de emisión separada, aplicar el umbral en el espacio adecuado y componer el halo de forma coherente con la gestión de color. Ofrecer modos explícitos: brillo de imagen y emisión. Si se requiere brillo en HDR, comprobar que el buffer conserve esa información antes de la transformación de visualización.

**Código relevante:** `blender/viewport_worker.py`, `native/gpu_bridge.cpp`, `shaders/EeveeBlit.ogsfx`, `scripts/eevee_maya/shared_frame.py`.

### 4.8 Gestión de color y transparencia

**Estado actual.** Se siguen espacios lineales comunes de Maya: ACEScg, Rec.709 y Rec.2020. La vista ACES 1.x se aproxima mediante ACES 1.3 de Blender. Las configuraciones OCIO personalizadas no tienen equivalencia completa. La transmisión interactiva usa transparencia y reflexión Fresnel para conservar visibles, por ejemplo, iris y pupilas detrás de una córnea.

**Deficiencia.** Puede haber diferencias de contraste, exposición, saturación y reflejos. La transparencia aproximada no reproduce refracción física; las capas superpuestas y su profundidad pueden fallar.

**Mejoras recomendadas:** compartir configuración, espacio de trabajo, vista, display, exposición y transformaciones OCIO cuando sea viable; validar cartas de color y texturas con el mismo tratamiento de entrada; evitar dobles transformaciones. Para transmisión, definir un modo rápido y otro de mayor fidelidad, con límites explícitos y pruebas de objetos anidados. Revisar la profundidad por material y cobertura, no solo por objeto.

**Código relevante:** `scripts/eevee_maya/color_management.py`, `blender/worker.py`, `blender/viewport_worker.py`.

### 4.9 Escenarios grandes, rigs y cobertura de escena

Maya ya evalúa deformadores y pesos pintados antes del envío. Esto permite ver sus resultados, pero el coste del rig sigue existiendo en Maya y el envío de mallas deformadas puede ser importante.

Prioridades: compartir mallas instanciadas, evitar copias redundantes, separar topología de puntos animados, actualizar únicamente lo deformado y gestionar cachés de texturas con presupuesto. El culling debe considerar también sombras y reflejos; eliminar todo lo que queda fuera de cámara puede cambiar la iluminación.

NURBS, pelo, partículas, proxies Arnold/USD, VDB, displacement, smooth mesh preview, isolate select y motion blur no tienen soporte completo certificado. Deben incorporarse como tareas independientes, con conversión o backend definidos y pruebas de fidelidad. No son funciones que aparezcan automáticamente al instalar dependencias.

### 4.10 Integración nativa, captura y distribución

**Ya implementado en 0.6.11:** selección desde Renderer > Eevee, cuadradito nativo de opciones, ajustes sin arrancar Blender, indicador animado con etapas reales, cancelación al volver a Viewport 2.0 y errores dentro del viewport. No corresponde volver a presentar estas funciones como pendientes.

El playblast ya espera la pose e imagen correctas por fotograma y se ha verificado en PNG y AVI Full HD, incluido arranque en frío. Una captura puede tardar más que tiempo real: lo necesario es conservar todos los fotogramas correctos.

Mejoras pendientes: ampliar pruebas de layouts y varios paneles, recuperación de pérdida de contexto gráfico, suspensión, GPU híbrida y cambios de tamaño. Añadir diagnóstico de compatibilidad antes de activar y reportes exportables sin información sensible de las escenas.

El transporte actual requiere interoperabilidad WGL/D3D11 y Maya en OpenGL/OpenGL Core Profile. No requiere CUDA ni núcleos RTX, pero solo se ha certificado esta ruta en la GPU/controlador de pruebas NVIDIA RTX 3070. No debe anunciarse compatibilidad universal con cualquier GPU. Otras versiones de Maya requieren compilar y validar el componente nativo con su SDK.

El instalador y las actualizaciones desde GitHub ya existen. Conviene ampliar la matriz de máquinas, comprobar rollback y firma de código, y mantener versiones de Blender y DLL compatibles. Una instalación correcta no certifica fidelidad visual ni rendimiento.

## 5. Qué rendimiento está realmente demostrado

El registro local `diagnostics/camera_navigation_controlled.json` contiene esta comparación de la versión 0.6.8, con 420 mallas, la misma pose y AA de 8 muestras:

| Ruta de interacción | Ancho real durante movimiento | Actualizaciones presentadas/s | Latencia mediana | Latencia p95 |
|---|---:|---:|---:|---:|
| Temporizador Qt | 960 px | 11,17 | 82,09 ms | 156,57 ms |
| Callback nativo de navegación | 640 px | 13,18 | 88,07 ms | 110,10 ms |

La segunda ruta mejora la frecuencia de actualización y la cola de latencia p95 en esa prueba; la mediana no mejora. También cambia la resolución, por lo que no permite atribuir toda la diferencia al callback. Aunque el ancho solicitado fuera 1920, estos resultados corresponden a previews reducidos. No certifican 30 FPS ni Full HD, ni constituyen un benchmark completo de la versión 0.6.11.

En ese registro, el render de color del worker ocupa aproximadamente 60–67 ms de media, por encima del presupuesto completo de 33,3 ms para 30 FPS. Por tanto, reducir únicamente la comunicación entre procesos no bastaría para alcanzar esa meta en esa configuración. Hay que medir nuevamente las versiones actuales antes de decidir la siguiente optimización.

El informe local `diagnostics/verification_0_6_11.json` registra 48 pruebas unitarias y de instalador, además de comprobaciones satisfactorias de interfaz nativa, arranque, captura, ciclo de panel y actualización. Son evidencia de esas rutas concretas; no certifican todas las escenas, materiales o GPU. Los diagnósticos locales pueden no distribuirse en el paquete público.

## 6. Plan de trabajo por prioridad

| Prioridad | Trabajo | Resultado verificable |
|---|---|---|
| P0 | Instrumentación de latencia y estado de recursos | Cada imagen se asocia con pose, cámara y resolución reales; se identifica el coste dominante. |
| P0 | Diagnóstico y actualización incremental de materiales | Se detectan conexiones incompatibles y se evita reconstruir geometría por un cambio de shader. |
| P0 | Calibración de cámara, DOF y transparencia | Patrones a distancias conocidas quedan enfocados con los valores de Maya, sin ajuste compensatorio manual. |
| P0 | Calibración de luces y perfiles Spot | Intensidad, orientación, cono y volumen responden de forma continua y reproducible. |
| P1 | Optimización de render y sincronización basada en perfiles | Mejora medible a resolución y calidad constantes. |
| P1 | Historial temporal válido y AA estable | Menos parpadeo sin rastros en personajes, sombras ni cortes de cámara. |
| P1 | Bloom por emisión y pipeline de color coherente | Los materiales no emisivos quedan fuera del modo de emisión; exposición y vista tienen comportamiento definido. |
| P1 | Instancias, cachés y presupuestos de memoria | Escenarios repetitivos crecen sin duplicar innecesariamente geometría y texturas. |
| P2 | Nodos y tipos de escena adicionales | Cada nueva familia dispone de pruebas y límites documentados. |
| P2 | Certificación de plataformas y robustez de paneles | Matriz publicada de Maya, Blender, GPU y controlador realmente verificados. |

No conviene reescribir todo el bridge de inmediato. Mantener la arquitectura persistente permite comparar mejoras aisladas y conservar lo que ya funciona. Una integración interna del motor de Blender exigiría investigar sus dependencias y contextos de escena/render; no es una sustitución sencilla por una DLL.

## 7. Criterios de aceptación propuestos

Los siguientes criterios son metas pendientes de validar:

- **Fluidez:** al menos 30 imágenes nuevas y correctas por segundo de forma sostenida, a 1920 × 1080 reales, con lista fija de efectos, muestras y calidad. La resolución adaptativa debe estar desactivada para certificar Full HD.
- **Respuesta:** objetivo inicial de latencia de entrada a presentación p95 ≤ 66 ms, registrando también mediana y p99. Frecuencia de imagen y latencia son medidas distintas.
- **Animación:** rigs deformados, cambios de visibilidad y cámaras animadas sin saltos de pose, geometría atrasada ni imágenes mezcladas.
- **Captura:** un fotograma correcto por cada tiempo solicitado; dimensiones exactas en secuencia y vídeo; ningún indicador de carga ni imagen antigua en el resultado.
- **Luces:** pruebas separadas para luces seleccionadas, modos predeterminados, Directional desde arriba, Spot con penumbra/dropoff y light/shadow linking.
- **Cámara:** patrones de foco en primer plano, sujeto y fondo; cambios de focal y f-stop; cámaras escaladas y unidades distintas.
- **Materiales:** referencias de piel, ojos, emisión, metal y transparencias; informe legible de lo que no se tradujo.
- **Estabilidad:** sesiones prolongadas de navegación, scrub y edición sin crecimiento continuo de memoria, pérdida de contexto o procesos huérfanos.

Cada prueba debe registrar versiones, GPU/controlador, resolución efectiva, geometría, materiales, texturas, luces, efectos, muestras y memoria. Separar arranque en frío de estado estable y medir por separado navegación, edición de luces y reproducción de rigs.

Primero se validan escenas genéricas controladas; después escenas grandes autorizadas, sin modificar los originales. Para comparar dos implementaciones se mantiene idéntica la calidad, el encuadre y la pose. No se deben publicar escenas, texturas o rutas internas del cliente dentro de los informes de distribución.

## 8. Prácticas que no resuelven el problema

- Informar FPS sin indicar la resolución real o contando redibujos que repiten la misma imagen.
- Afirmar 30 FPS por reducir el preview a 640 px, apagar efectos o bajar AA silenciosamente.
- Prometer compatibilidad completa con Arnold porque existe un material con nombre equivalente.
- Aumentar muestras y memoria de todas las sombras sin identificar el cuello de botella.
- Activar acumulación temporal sin gestionar correctamente cambios de pose e historial.
- Sacrificar la sincronización exacta del playblast para acelerar su duración.
- Instalar bibliotecas adicionales esperando que traduzcan automáticamente escenas y shaders.

## 9. Referencias de implementación

Las rutas siguientes son relativas a este repositorio:

| Subsistema | Archivos principales |
|---|---|
| Control y sincronización | `scripts/eevee_maya/ui.py`, `engine.py`, `changes.py`, `scene_stream.py` |
| Exportación y color | `scripts/eevee_maya/exporter.py`, `color_management.py`, `light_links.py` |
| Foco y controles | `scripts/eevee_maya/focus.py`, `native_controls.py`, `quality.py`, `shadow_quality.py`, `settings_window.py` |
| Render y copia de escena | `blender/worker.py`, `scene_sync.py`, `viewport_worker.py` |
| GPU y presentación | `native/gpu_bridge.cpp`, `native/scene_stream.cpp`, `scripts/eevee_maya/viewport.py`, `gpu_share.py`, `shared_frame.py`, `shaders/EeveeBlit.ogsfx` |
| Captura y arranque | `scripts/eevee_maya/capture.py`, `startup.py` |
| Distribución | `packaging/InstallBridge.ps1`, `tools/build_release.py`, `tools/publish_release.ps1` |

Para instalar, actualizar o ejecutar las pruebas existentes, consultar [README.md](README.md). Las etapas marcadas como aplicadas forman parte de 0.6.12; el resto del plan sigue siendo trabajo propuesto.
