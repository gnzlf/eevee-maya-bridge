Eevee Maya Bridge 0.6.25 conserva la sesión cargada al cambiar de viewport.

- Después de mostrar la primera imagen, cambiar a Viewport 2.0 pausa Eevee y conserva Blender, escena, geometría, materiales y texturas en memoria.
- Al activar Eevee en otro panel se reutiliza el mismo controlador y proceso. Se actualizan cámara y cambios pendientes sin reconstruir la escena si sus datos siguen siendo válidos.
- Descarta respuestas GPU pendientes de la cámara anterior y libera sus frames para evitar bloqueos al volver, incluso después de un cambio de resolución.
- El playblast puede reanudar la sesión antes de que termine la activación diferida del menú. Se conservan la sincronización de fotogramas y deformaciones y la resolución pedida.
- Mantiene la cancelación del primer arranque y la presentación de errores. El cierre explícito libera la caché y el worker.

La sesión en pausa conserva RAM/VRAM. Para liberarla utiliza Eevee > Detener Eevee y liberar memoria, descarga el plugin o cierra Maya. Solo un panel usa Eevee a la vez. Abrir otra escena, cambiar materiales/topología o cambiar OCIO puede exigir reconstruir datos o reiniciar el worker; conservar la sesión no evita esas invalidaciones.

Validación: 118 pruebas de distribución, 8 del plugin instalado, 88 comprobaciones gráficas de reanudación/paneles/ACK/captura y 21 del menú nativo, arranque, cancelación y errores. La prueba de cambios de viewport mantuvo un solo proceso y una única construcción de escena, incluidas deformaciones y un render Full HD pendiente. Pasaron además 30 comprobaciones de Prism con MP4, AVI, MOV, poses distintas y audio.

Guarda tu trabajo y reinicia Maya después de instalar la actualización.
