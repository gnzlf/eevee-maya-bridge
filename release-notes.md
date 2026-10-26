Playblast por fotograma, respuesta interactiva y correcciones de cámara y luces.

- El playblast nativo espera la imagen correspondiente a cada pose evaluada de Maya. Funciona con secuencias de imágenes y vídeo; respeta las dimensiones reales de captura, sin aplicar la reducción de calidad interactiva.
- Un fallo del renderizador produce un aviso, diagnóstico y fotogramas rojos para evitar entregar imágenes antiguas como válidas. Maya puede conservar una captura parcial; la función Python `eevee_maya.capture.playblast` también lanza una excepción.
- Calidad adaptativa al editar y reproducir: hasta 960 píxeles de ancho y dos muestras mientras hay movimiento, con recuperación de calidad al detenerse. Se puede desactivar. Menos consultas a Maya mientras el renderizador trabaja y caché de light links invalidada por cambios y Undo/Redo.
- Ajustes de cámara: botones para activar los tres controles necesarios de DOF y para enfocar la selección. El estado indica si la cámara, el preview o el control global tienen desactivado el desenfoque. Conserva los parámetros nativos hasta pulsar esos botones.
- Corrige luces auxiliares de 180 grados generadas por valores altos de Dropoff: el volumen de una spotlight deja de extenderse lateralmente como una point light. Conserva el cono, la penumbra y el Dropoff de Maya.
- Elegir Eevee en el menú Renderer del viewport activa su controlador; corrige el caso de panel seleccionado con imagen congelada.

Validación: pruebas de distribución e instalación del EXE en Maya 2024.2; PNG y AVI Full HD con retrasos deliberados del renderizador; 12 fotogramas consecutivos por formato en una escena de producción de 420 mallas con rigs y deformadores, sin imágenes repetidas. Comprobados cono, penumbra, volumen, DOF y light linking. Pruebas GPU realizadas con RTX 3070; el Acer Nitro 5/RTX 3060 requiere comprobarse en ese equipo.

Para capturar a 1920×1080, usa 100 % y Render offscreen en las opciones nativas de Playblast. Instala la versión y reinicia Maya después de guardar tu trabajo. La captura espera lo necesario; no exige reproducción a tiempo real.

El viewport continúa siendo experimental. La mejora interactiva usa calidad temporal reducida; no garantiza 30 FPS a resolución completa ni paridad completa con Arnold. DOF y bloom siguen siendo previews del puente. Requiere Maya 2024 y OpenGL/OpenGL Core Profile. El instalador no tiene firma de código.
