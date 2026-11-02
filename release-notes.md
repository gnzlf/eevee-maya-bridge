Eevee Maya Bridge 0.6.28 corrige la profundidad de campo con rim lights, las volumétricas con HDRI y el texto de carga.

- Profundidad de campo: un rim light o cualquier borde muy brillante desenfocado se ve como un halo suave. Antes se cortaba en trazos y rayas verticales. El desenfoque ahora tiene en cuenta la profundidad: el fondo no se mezcla sobre lo enfocado y lo cercano desenfocado se funde con el fondo.
- Volumétricas con HDRI: los haces de luz vuelven a verse con el HDRI encendido. El HDRI ya no ilumina la niebla, igual que el `atmosphere_volume` de Arnold, que ignora el skydome; sigue iluminando la escena y el fondo. La opción **HDRI ilumina la niebla**, en Atmósfera, recupera el comportamiento anterior.
- Pantalla de carga: cada línea de texto va en su sitio y sin caracteres raros.

Instala la actualización desde el menú Eevee o descarga el instalador desde los recursos de esta versión. Reinicia Maya para activar los archivos nuevos.
