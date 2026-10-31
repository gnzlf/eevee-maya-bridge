Eevee Maya Bridge 0.6.24 acerca la intensidad de las luces a Viewport 2.0 sin editar sus atributos en Maya.

- Añade Ajustes > Luz > Intensidad de las luces > Aproximar Viewport 2.0, activado por defecto. Conversión anterior de Eevee permite recuperar la iluminación previa.
- Calibra Point, Spot, Directional, Area y Ambient contra cartas de Lambert, Standard Surface y aiStandardSurface. Distingue sus convenciones de intensidad y corrige normalize/legacyIntensity de Area.
- No Decay y Linear se aproximan a una distancia representativa de receptores visibles y enlazados. La mezcla de familias de materiales se mantiene estable al cambiar qué objeto está más cerca.
- Conserva la potencia volumétrica previa mediante una compensación independiente. Mantiene los controles de volumen, selección, sombras y color.
- El modo se guarda como preferencia de Maya. La conversión también se aplica al playblast; no cambia HDRI, exposición ni gestión de color.

La coincidencia es aproximada. Eevee conserva caída cuadrática: varios receptores a distancias diferentes, límites de objetos amplios o mezclas de materiales pueden diferir de VP2. No certifica equivalencia por cara, igualdad con Arnold ni mejoras de FPS. Las escenas iluminadas antes pueden cambiar de aspecto con el modo nuevo; utiliza Conversión anterior de Eevee para conservar su conversión.

Validación: 118 pruebas de distribución y 8 comprobaciones del plugin instalado; 35 comparaciones de luces, intensidades y distancias con un error máximo de 2 niveles sobre 255 en pantalla y captura; 15 cartas con Lambert/Standard Surface/aiStandardSurface; 14 casos de escala y normalización de Area nativa y Arnold. También pasaron 96 comprobaciones de volumen y cambio de modo, 33 de sombras y 9 de mezcla de receptores y compatibilidad. Las mediciones corresponden a escenas genéricas controladas.

Guarda tu trabajo y reinicia Maya después de instalar la actualización.
