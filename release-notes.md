Calidad de sombras configurable desde Maya.

- Nueva pestaña Ajustes > Sombras: Baja (25%), Media (50%), Alta (100%, predeterminada) y Ultra (100% con más muestras para sombras suaves). El visor anterior estaba fijo al 50% y 128 MB.
- Memoria automática de 128 / 256 / 512 / 1024 MB según el nivel, o selección manual de 128–2048 MB. Más memoria ayuda cuando muchas luces llenan el presupuesto de sombras; por sí sola no aumenta su nitidez. Eevee usa mapas virtuales, sin equivalencia fija a mapas de 2K/4K.
- Los cambios se aplican en vivo sin reiniciar Blender ni reconstruir las mallas. Se guardan en las preferencias de Maya y se respetan también en el playblast PNG/AVI. La calidad adaptativa conserva los ajustes de sombras; su resolución temporal de imagen sigue limitando el detalle visible al navegar.
- El botón nativo de sombras de Maya y los controles por luz siguen activando o apagando las sombras. Se traduce el ángulo de sombra de Directional a Eevee, y Ajustes > Luz muestra los controles nativos de radio, ángulo y activación de sombras.

Alta y Ultra consumen más tiempo de GPU y memoria; no garantizan 30 FPS. La luz por defecto de Maya no proyecta sombras: usa una luz real con sombras activadas.

Validación en Maya 2024: comparación de imágenes con sombras finas a 1920 píxeles, cambios de nivel en vivo, controles nativos y ángulo de Directional, playblast PNG/AVI a 1920×1080 con sombras Ultra, escena de producción de 420 mallas con deformaciones entre poses y pruebas de distribución e instalación.

Instala desde Eevee > Buscar actualizaciones y reinicia Maya después de guardar tu trabajo. También puedes descargar el instalador de este release. El viewport y su DOF continúan siendo experimentales. El instalador no tiene firma de código.
