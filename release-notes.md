Eevee Maya Bridge 0.6.16 corrige el cambio de encuadre al alternar entre Eevee y Viewport 2.0.

- El viewport GPU utiliza la proyección real de Maya. Antes se reconstruía desde el FOV sin aplicar overscan y se omitían transformaciones de película.
- Conserva overscan, film fit, offsets, pan/zoom, film roll, post scale y cámaras ortográficas con escala. No escribe ni cambia el lente, la posición o la transformación de la cámara de Maya.
- Color y profundidad comparten la proyección. El playblast obtiene la proyección del destino real, incluso cuando su relación de aspecto difiere del panel visible.
- La sincronización de captura ocurre antes del dibujo de la imagen, con el contexto de cámara de ese fotograma. Los fallos tardíos se marcan en rojo para impedir capturas que parezcan válidas con una imagen anterior.

Verificación: comparación de siluetas entre VP2 y Eevee en doce configuraciones de cámara y cambio de renderer en el mismo panel; atributos y matriz mundial intactos. Incluye lentes de 18 y 85 mm, overscan 1.3, film fit vertical, offsets y squeeze, pan/zoom, roll, gate, post scale y ortográficas escaladas. Estas pruebas corresponden al viewport GPU; el backend de imagen separado conserva su aproximación de frustum.

Actualiza desde Eevee > Buscar actualizaciones, guarda tu trabajo y reinicia Maya para cargar el código nuevo.
