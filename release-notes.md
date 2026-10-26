Correcciones de materiales, ojos y color de piel.

- Traducción de specularColor y sus texturas en Standard Surface, aiStandardSurface, Blinn y Phong. Las máscaras especulares ya pueden mantener oscuras las pupilas en lugar de producir un reflejo blanco uniforme.
- Los Lambert dejan de recibir el reflejo especular que el puente añadía por defecto. Se conservan sus colores y las asignaciones de materiales por cara.
- El render sigue el espacio lineal ACEScg, Rec.709 o Rec.2020 de Maya. Corrige la interpretación de colores constantes ACEScg como Rec.709, que apagaba tonos de piel y ropa. Las texturas se convierten al mismo espacio de trabajo dentro de Blender, sin modificar los archivos originales.
- Las vistas comunes se aproximan con sus equivalentes de Blender: ACES 1.x usa ACES 1.3 y Un-tone-mapped usa Standard. No hay paridad completa con vistas o configuraciones OCIO personalizadas; la imagen también puede diferir por la iluminación y los modelos de sombreado.
- La transmisión del viewport usa transparencia y reflexión Fresnel para ver objetos detrás de córneas o cristales sin activar raytracing global. Es una aproximación sin refracción óptica completa. Las superficies totalmente transmisivas no tapan la profundidad usada por AO/DOF; el botón nativo de material por defecto puede volverlas opacas y restaura su estado original al desactivarlo.

Validación: comparación visual en una escena de producción con personajes; pruebas GPU de pupilas, máscaras especulares, transparencia y asignaciones por cara; captura nativa PNG/AVI Full HD; pruebas de distribución e instalación. No se modifican las escenas, referencias ni texturas originales.

Actualiza desde Eevee > Buscar actualizaciones y reinicia Maya después de guardar tu trabajo. El puente sigue siendo experimental y no reproduce todas las redes de materiales de Arnold. El instalador no tiene firma de código.
