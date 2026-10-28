Eevee Maya Bridge 0.6.21 corrige los playblasts negros o congelados y añade compatibilidad con la opción QuickTime de Prism.

- Sincroniza cada pose también cuando Maya renderiza el playblast offscreen mediante un panel interno diferente del panel Eevee. Antes ese cambio podía omitir la actualización y reutilizar una imagen anterior, o negro durante el arranque.
- El adaptador de Prism fija el panel Eevee antes de aplicar la cámara y comprueba que se hayan capturado todos los fotogramas. Conserva los nombres, versiones, JPEG→MP4 y MP4 con audio de Prism.
- La opción QuickTime de Prism genera MOV H.264/AAC mediante su FFmpeg y una captura AVI temporal de Maya, conservando el audio incluido por Maya. No requiere instalar QuickTime antiguo ni modificar los archivos de Prism.
- Un fallo al presentar la textura GPU invalida el playblast. Se comprueba también que la cámara de captura corresponda al panel seleccionado.

La adaptación se aplica únicamente durante la operación de playblast de Prism cuando Eevee está activo. El comando original se restaura al terminar, también ante errores. Al descargar el plugin se restaura la función original de Prism. El AVI temporal puede requerir bastante espacio en clips largos. QuickTime nativo fuera de Prism conserva sus requisitos originales.

Guarda tu trabajo y reinicia Maya después de actualizar para activar 0.6.21.

Verificación: 102 pruebas de distribución, 30 comprobaciones gráficas con el adaptador de Prism instalado y arranque en frío, sonido audible, skin y cámara animada. Una escena de producción pasó los 148 fotogramas Full HD en MP4 y MOV; se compararon inicio, mitad y final con PNG de referencia. Pasan también las regresiones de PNG/AVI, captura en frío y una escena grande en una sesión de prueba aislada, sin guardar los archivos originales.
