Eevee Maya Bridge 0.6.20 corrige las spotlights que dejaban objetos negros con determinadas cámaras.

- Corrige la conversión de cámara: un residuo numérico hacía que Eevee interpretara una perspectiva como ortográfica y descartara iluminación Spot/Point en casi toda la imagen. Se conserva el par nativo de vista/proyección, el encuadre y los parámetros de cámara de Maya.
- Spot y Point usan un alcance finito basado en receptores visibles y atmósfera, evitando el recorte prematuro de luces tenues por el umbral automático de Eevee. No cambia la energía de la luz al mover la geometría.
- Conserva luz seleccionada, vínculos por objeto, sombras, controles HDRI y la corrección de recursos GPU durante cambios de resolución.

Verificado en una escena de producción suministrada por el usuario, en un Maya separado y sin guardar el archivo original: intensidad 0/1/8, sombras y cambio de fotograma a 1920 × 1080. La validación mide cobertura de superficies mediante una referencia Directional; excluye falsos positivos por iconos o pequeños parches luminosos. También se comprueban cámara trasladada/rotada, escala, lentes, film fit, offsets, gates, pan/zoom y ortográfica contra Viewport 2.0 en el mismo panel.

El decaimiento distinto del cuadrático sigue siendo una aproximación calibrada en Center of Illumination. No se certifica equivalencia fotométrica con Arnold ni 30 FPS.

Actualiza desde Eevee > Buscar actualizaciones, guarda tu trabajo y reinicia Maya. Si subiste mucho la intensidad para compensar el fallo anterior, redúcela antes de evaluar la luz corregida.
