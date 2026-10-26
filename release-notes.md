Navegación de cámara con menos espera y resolución temporal configurable.

- El puente también consume y envía imágenes durante el dibujo nativo del panel. Evita depender exclusivamente del temporizador Qt cuando Maya está ocupado con una herramienta de navegación y evita refrescos recursivos.
- El volumen conserva una caché de los límites mundiales de las mallas. Al navegar recalcula su alcance con operaciones vectorizadas; invalida la caché ante cambios de puntos, matrices, visibilidad o reconstrucción de escena.
- Nuevo control en Ajustes > Viewport: «Navegación de cámara más rápida» y «Ancho temporal al navegar». Con calidad adaptativa activa, utiliza 640 píxeles por defecto mientras navegas y recupera la resolución configurada al detenerte. Puedes elegir 320–1920 o desactivar el modo.
- Conserva las muestras AA de Maya y los efectos. La reproducción y el scrubbing de cámaras animadas conservan su política de calidad; el playblast no utiliza esta reducción de navegación y captura cada fotograma a su tamaño solicitado.

En una comparación controlada con la misma sesión, pose y cámara de una escena de 420 mallas, AA8 y efectos activos, la navegación pasó de unas 11 a 13 actualizaciones/s. El percentil 95 de demora bajó de 157 a 110 ms; la mediana quedó similar (82 frente a 88 ms). La comparación usa sincronización por Qt y preview de 960 píxeles frente al nuevo dibujo nativo y preview de 640; ambos conservan AA y efectos. La caché volumétrica estaba activa en ambos modos. Las pruebas iniciales dieron tiempos más variables; estas cifras no garantizan mejoras iguales en todos los equipos ni equivalen a Full HD a 30 FPS. Equipo de prueba: Maya 2024.2 y RTX 3070.

Validación: pruebas de distribución e instalador; comprobación de actualizaciones mediante dibujo nativo con el temporizador Qt detenido; comparación de límites volumétricos; regresiones de controles ópticos y playblast PNG/AVI Full HD.

Instala desde Eevee > Buscar actualizaciones y reinicia Maya después de guardar tu trabajo. El viewport y su DOF continúan siendo experimentales. El instalador no tiene firma de código.
