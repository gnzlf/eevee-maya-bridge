Eevee Maya Bridge 0.6.23 mejora la respuesta al mover objetos y luces con el viewport configurado en 1920.

- Corrige la calidad interactiva para movimientos de objetos, deformaciones y visibilidad. Antes podía permanecer en 1920 durante el arrastre aunque la calidad adaptativa estuviera activa.
- Añade Ajustes > Viewport > Ancho temporal al mover objetos o luces: 640, 960, 1280 o 1920. Conserva el antialiasing y los efectos, recupera la resolución final al detenerse y mantiene la resolución exacta del playblast.
- Reutiliza framebuffers y texturas GPU de hasta tres tamaños para reducir pausas al alternar entre previa y calidad completa. Mantiene vivas las generaciones pendientes de importación y evita sobrescribirlas antes de la confirmación de Maya.
- Evita reconfigurar la cámara y propiedades de Eevee que no cambiaron. Conserva la sincronización de geometría y luces.

La caché retiene memoria GPU adicional entre tamaños. La calidad adaptativa reduce temporalmente la resolución durante el movimiento; puede desactivarse o configurarse en 1920 para conservar el tamaño completo. No se certifican 30 FPS sostenidos con todos los efectos en todas las escenas.

Validación: 112 pruebas de distribución, 48 ediciones de objetos y luces en una escena de producción, captura exacta a 1920×1080, 9 comprobaciones de importación y reutilización GPU, 30 comprobaciones del playblast de Prism y 8 comprobaciones del plugin instalado. En la prueba de movimiento de objetos, la mediana del render pasó de 45 a 31 ms al corregir la previa adaptativa de 960 píxeles; esta medida no representa la latencia total de Maya.

Guarda tu trabajo y reinicia Maya después de instalar la actualización.
