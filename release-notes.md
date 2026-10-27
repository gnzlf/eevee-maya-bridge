Eevee Maya Bridge 0.6.15 corrige luces de área y añade Ambient Light, manteniendo Smooth Mesh Preview.

- Detecta Area Light nativa de Maya, Area Light de Arnold (aiAreaLight) y Ambient Light de Maya, incluso al usar luces seleccionadas.
- Las áreas respetan dimensiones, Normalize, Legacy Intensity, exposición y apertura de Arnold; evita aplicar dos veces la escala del área.
- Ambient Light responde a color e intensidad, apagado, selección y light linking por objeto. Ambient Shade mezcla una contribución uniforme con una aproximación puntual. Actualiza los atributos de sombreado sin duplicar materiales compartidos.
- La caché C++ reutiliza mallas sin cambios y omite la actualización de geometría oculta. Al mostrarla de nuevo recupera la deformación y el smooth actuales.

Verificación: capturas reales PNG Full HD de luces de área y ambient; pruebas de selección, normalización, light linking, intensidad cero y material predeterminado; smooth y skin animado; edición, Undo, ocultar/mostrar y deformadores en DG, serial y paralelo.

Rendimiento: en una comparación de 14 poses de producción con 566 mallas (391 visibles), la mediana de extracción de geometría pasó de 62,4 a 43,3 ms. Se alternó el orden de ambas rutas; las posiciones coinciden y la diferencia máxima en normales fue de 4,2e-7. Es una mejora de extracción, no una medición de FPS del viewport completo.

Ambient es un preview difuso: el componente uniforme no reproduce sombras de rayos ni volumen de Maya. Las áreas cilíndricas de Arnold se aproximan como rectángulos y no hay equivalencia fotométrica completa con Arnold. El bridge sigue siendo experimental.

Actualiza desde Eevee > Buscar actualizaciones, guarda tu trabajo y reinicia Maya para cargar la nueva biblioteca nativa. El instalador conserva las preferencias y la versión anterior.
