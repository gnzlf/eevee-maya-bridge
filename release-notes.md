Libera el renderizador auxiliar al cerrar un panel y recupera la imagen al volver a abrirlo.

- Si Maya conserva un panel sin su vista gráfica durante tres segundos, el puente cierra exclusivamente su proceso Blender, retira la imagen compartida y libera su caché de extracción de mallas.
- Al volver la vista, inicia otro renderizador y reconstruye la escena automáticamente, conservando cámara, luces, materiales, atributos de Maya y configuración del puente.
- Los cambios breves de layout siguen usando la pausa corta de 0.6.4 y conservan el proceso existente.
- Un fallo al reiniciar se muestra como estado del puente y se limpian los recursos parciales antes de volver a intentarlo.
- Incluye las correcciones de rutas al renombrar/reagrupar y las actualizaciones sin reevaluación innecesaria de mallas de 0.6.4.

Instala esta versión y reinicia Maya al terminar de trabajar. Mantén OpenGL/OpenGL Core Profile como motor del viewport.

Validación: 24 pruebas de distribución; instalación del EXE y ocho comprobaciones del paquete en Maya 2024.2 standalone; once comprobaciones de pausa, suspensión, cierre/reinicio del proceso auxiliar y recuperación de la imagen en una escena de producción con 420 mallas. Las pruebas de GPU se ejecutaron con RTX 3070; el Acer Nitro 5/RTX 3060 aún requiere verificación en el equipo del usuario.

El viewport continúa siendo experimental. Requiere Maya 2024 instalado; no garantiza 30 FPS ni paridad completa con Arnold. El instalador no tiene firma de código.
