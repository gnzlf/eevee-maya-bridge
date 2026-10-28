Eevee Maya Bridge 0.6.18 corrige materiales negros con texturas UDIM.

- Las rutas con `<UDIM>` se resuelven contra sus tiles existentes. Antes el bridge exigía que el nombre literal existiera como archivo, descartaba el mapa y podía dejar negro el material.
- Conserva el patrón UDIM y los tiles al abrir una imagen concreta. Admite también nombres de tile concreto y conjuntos sin el tile 1001.
- El diagnóstico de materiales reconoce estos archivos y sigue avisando si el conjunto no existe.
- No modifica colores, conexiones, rutas, materiales ni archivos de la escena original.

La compatibilidad de materiales continúa siendo parcial; esta corrección cubre texturas file directas y no añade redes arbitrarias de Arnold ni secuencias de texturas animadas.

Verificación: 11 comprobaciones con capturas Full HD, incluidas dos texturas UDIM y piel/ropa en la escena de producción sin guardar cambios. Pasan 91 pruebas de distribución, 7 del diagnóstico de materiales y 8 de carga/recarga del paquete instalado. También pasan las regresiones de playblast PNG/AVI y arranque en frío.

Actualiza desde Eevee > Buscar actualizaciones, guarda tu trabajo y reinicia Maya para cargar el código nuevo.
