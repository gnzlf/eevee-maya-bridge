Eevee Maya Bridge 0.6.19 añade ajustes HDRI y corrige recursos GPU al cambiar de resolución.

- Nueva pestaña HDRI en los ajustes del renderer: elegir o crear SkyDome, cargar/reemplazar imagen, mostrar/ocultar fondo, visibilidad del fondo, intensidad, exposición, rotación y resolución de reflejos.
- Ocultar el fondo conserva luz y reflejos. Los controles utilizan atributos nativos de Maya y se guardan con la escena; admiten Undo y animación. Reemplazar una imagen compartida no altera los mapas de otras luces o materiales.
- Corrige `OpenSharedResource (HRESULT=0x80070057)` provocado por cambios de tamaño: las texturas anteriores se mantienen hasta que Maya confirma que ya no necesita esos fotogramas. Se reproducía el mismo error al demorar la primera importación de un recurso antiguo después de un resize.
- Conserva las correcciones de texturas UDIM de 0.6.18.

El HDRI sigue usando el World de Eevee: no añade light linking por objeto, pesos difuso/especular independientes ni equivalencia completa con los rebotes de Arnold. La corrección GPU cubre la duración de recursos durante resize; no cambia adaptadores ni certifica otros errores de drivers.

Las pruebas incluyen importaciones demoradas tras cuatro tamaños GPU, liberación de pools confirmados, controles HDRI nativos, fondo oculto con reflejos, HDR/EXR y capturas Full HD.

Verificación: 93 pruebas de distribución, 45 comprobaciones HDRI con la ventana de ajustes, 7 comprobaciones de resize GPU, 8 de edición/Undo de las imágenes y 8 de carga/recarga del instalador. Pasan las regresiones de PNG/AVI, arranque en frío y escena de producción sin guardar cambios en el archivo original.

Actualiza desde Eevee > Buscar actualizaciones, guarda tu trabajo y reinicia Maya para cargar el código nuevo.
