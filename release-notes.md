Inicio y ajustes desde el viewport nativo de Maya.

- Eevee aparece como Renderer > Eevee. El cuadradito de opciones junto a su nombre abre los ajustes mediante el mecanismo nativo de Maya, igual que otros renderizadores del panel.
- Los ajustes pueden abrirse antes de encender el motor. Los cambios de esa sesión se aplican al activarlo, y la ventana permanece abierta al cambiar entre Eevee y Viewport 2.0.
- Se retiran del menú superior los comandos «Activar en viewport actual» y «Abrir panel independiente». Ese menú conserva ajustes, recarga y actualizaciones. La entrada habitual es ahora Renderer > Eevee.
- Indicador animado dentro del viewport durante el arranque. Muestra las etapas reales: inicio del motor, lectura de escena, preparación de materiales y geometría, shaders y primera imagen. Incluye contadores cuando están disponibles y tiempo transcurrido; no inventa porcentajes ni un tiempo restante.
- Cambiar a Viewport 2.0 cancela también un arranque pendiente, sin que Eevee vuelva a seleccionarse al llegar una imagen tardía. Los fallos de arranque se muestran en el propio viewport. El indicador se retira al presentar la primera imagen y su temporizador se detiene.

Validación: uso del menú Renderer real de Maya y su cuadradito, imágenes distintas de la animación, ajustes sin arrancar Blender, cancelación, errores de inicio, recuperación del panel y playblast PNG/AVI Full HD.

Actualiza desde Eevee > Buscar actualizaciones y reinicia Maya después de guardar tu trabajo. Después usa Renderer > Eevee en el viewport. El puente sigue siendo experimental. El instalador no tiene firma de código.
