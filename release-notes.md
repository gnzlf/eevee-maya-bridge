Eevee Maya Bridge 0.6.17 añade HDRI de Arnold SkyDome Light al viewport.

- Los mapas HDR/EXR lat-long conectados directamente mediante file o aiImage iluminan los materiales traducidos de Maya/Arnold y aparecen en sus reflejos, incluidos metales y superficies rugosas.
- Respeta intensidad, exposición, rotación del transform, espacio de color de la imagen, visibilidad y modos nativos Todas/Seleccionadas. Camera = 0 conserva iluminación y reflejos con el fondo oculto.
- La orientación del mapa se corrigió comparándola con una calibración renderizada en Arnold CPU. Resolution controla la sonda mundial entre 128 y 4096.
- Los cambios de intensidad, exposición y rotación reutilizan el grafo del entorno y la imagen cargada. Navegar o deformar no reconstruye el HDRI. Los recursos ausentes o fuentes no compatibles dejan un aviso.

Alcance: World de Eevee usa una sonda ambiental. No reproduce los rebotes, oclusión interior, sombras físicas, light linking por objeto ni pesos Diffuse/Specular independientes de la SkyDome de Arnold. No traduce redes procedurales/utilidades, formatos Angular/Mirrored Ball ni ajustes UV/color de los nodos de imagen. La compatibilidad de materiales continúa siendo parcial.

Verificación: 39 comprobaciones de HDRI con capturas nativas, incluidos HDR/EXR, tres materiales, fondo oculto, varias domes y Full HD; 86 pruebas de distribución, 8 de exportación y 8 de carga/recarga del paquete instalado. Regresión de playblast PNG/AVI, arranque en frío y escena de producción sin guardar cambios en el archivo original.

Actualiza desde Eevee > Buscar actualizaciones, guarda tu trabajo y reinicia Maya para cargar el código nuevo.
