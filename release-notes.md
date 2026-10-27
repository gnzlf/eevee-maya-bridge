Edición de luces con menos trabajo repetido y diagnóstico desde Maya.

- Se conservan las colecciones de light linking y shadow linking al mover una luz o cambiar intensidad, cono o penumbra si sus miembros siguen iguales. Los cambios de vínculos, listas vacías, luces nuevas y reconstrucciones de escena mantienen su actualización.
- Se evitan escrituras repetidas de visibilidad cuando las luces ya tienen el estado solicitado. Se conservan los modos nativos de luces seleccionadas, predeterminadas, iluminación plana y sin luces.
- Eevee > Guardar diagnóstico de rendimiento guarda resolución efectiva, muestras, fotogramas nuevos, tiempos y modo de interacción o captura. No cuenta redibujos repetidos como nuevos fotogramas; señala mezclas de calidad y distingue el tiempo de envío a dibujo de la latencia completa del usuario.
- Eevee > Revisar materiales (solo lectura) detecta familias sin traductor específico, conexiones no traducidas, texturas ausentes y canales aproximados. La ventana muestra nombres locales; el informe exportado usa alias y omite rutas de texturas. No modifica materiales ni certifica equivalencia con Arnold.
- Se incluye DEFICIENCIAS_Y_MEJORAS.md con limitaciones, evidencia y prioridades de desarrollo.

En una prueba sintética de 400 mallas, la mediana de sincronización de luces pasó de aproximadamente 1,94 a 0,25 ms. Doce casos dieron imágenes idénticas entre la ruta anterior y la optimizada. Es una medición de esa función, no una garantía de FPS ni de 30 FPS Full HD en producción. Se conservan las muestras, resolución y efectos seleccionados.

Validación: 77 pruebas automatizadas, incluida instalación/actualización conservando preferencias y rechazo de paquetes corruptos. Se verificaron carga y descarga del plugin instalado, ambas DLL, menús gráficos, playblast PNG/AVI Full HD y coincidencia entre captura en frío y en caliente. También se comprobó una escena de producción de 566 mallas en Maya independiente, con cambio de fotograma y captura Full HD sin modificar el archivo original.

Actualiza desde Eevee > Buscar actualizaciones y reinicia Maya después de guardar tu trabajo. La versión nueva se activa en el siguiente inicio; el instalador conserva las preferencias y la versión anterior.
