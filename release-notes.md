Eevee Maya Bridge 0.6.22 mejora los materiales y la fidelidad del color y los reflejos HDRI.

- Corrige la doble transformación de color: entrega imagen lineal a Maya y conserva sus controles nativos de vista, exposición y gamma. Blender reutiliza la configuración OCIO de Maya para interpretar las texturas mediante una copia temporal.
- Recupera layeredTexture, rampas, ruido y otras redes 2D admitidas con muestreo UV de Maya y caché EXR flotante. Conserva el cuerpo y el iris de materiales que antes perdían sus conexiones.
- Conserva canales Color/R/G/B/Alpha y espacios de entrada de imágenes directas; separa las imágenes que usan espacios diferentes. Amplía mapas de base, specular, coat y transmisión. Corrige la intensidad del bump que antes se aplicaba dos veces.
- Añade Ajustes > HDRI > Detalle mínimo de reflejos Eevee: Nativo, 1024, 2048 por defecto o 4096. No modifica la resolución nativa de Arnold. La roughness sigue regulando el desenfoque del reflejo.

La primera preparación de redes procedurales, o la edición de sus parámetros, tiene coste de muestreo; navegar y deformar reutiliza su caché. Se admiten redes 2D de UV 0..1: no se certifican procedurales animados, grafos dependientes de posición/cámara, UDIM dentro de redes, displacement ni todos los nodos de Arnold. La transmisión conserva el modo rápido transparente/Fresnel, sin equivalencia de refracción física. No se añade light linking ni pesos difuso/especular independientes al World.

Conserva la sincronización por fotograma y la integración MP4/MOV de Prism de 0.6.21. Guarda tu trabajo y reinicia Maya después de instalar la actualización.

Verificación: 105 pruebas de distribución; 15 comprobaciones gráficas de color y controles nativos; 10 comprobaciones de materiales en una escena de producción a 1920x1080; 8 de muestreo Maya y 5 de decodificación/shaders Blender; 30 de Prism con MP4/AVI/MOV, sonido, cámara y skin animados; 8 de carga, recarga y descarga del plugin instalado. No certifica equivalencia completa con Arnold ni 30 FPS.
