Mejoras de estabilidad al cerrar paneles, renombrar objetos y actualizar el viewport.

- El puente espera cuando Maya conserva un panel pero su vista gráfica todavía no existe, en lugar de detenerse con `Object does not exist`. Reanuda el envío cuando la vista vuelve y reduce la frecuencia del temporizador mientras espera.
- Al activar Eevee, se eligen paneles que realmente tienen una vista disponible.
- Renombrar una malla, un grupo antecesor o un material, y cambiar de padre, invalida las rutas exportadas. El puente reconstruye sus referencias para evitar nombres antiguos y fallos en light linking. Los avisos de cambio de identidad permanecen activos durante la reproducción.
- Las solicitudes de otra imagen por cambios de calidad o ajustes ya no recorren todas las mallas si su geometría no está sucia. Los cambios reales de deformadores y animación conservan su actualización.
- Conserva las correcciones de carga/descarga y diagnóstico introducidas en 0.6.3.

Instala esta versión y reinicia Maya al terminar de trabajar. Mantén OpenGL/OpenGL Core Profile como motor del viewport.

Validación: 24 pruebas de distribución; instalación del EXE y ocho comprobaciones del paquete en Maya 2024.2 standalone; cambios de nombres y jerarquía con Maya API y con imágenes reales de Eevee; recuperación de vista y evaluación de geometría; deformadores, skin y blendShapes; pruebas visuales de luces, selección, sombras, light linking, AO, DOF, volumen y salida a 1920. Las pruebas de GPU se ejecutaron con RTX 3070; el Acer Nitro 5/RTX 3060 aún requiere verificación en el equipo del usuario.

El viewport continúa siendo experimental. Requiere Maya 2024 instalado; no garantiza 30 FPS ni paridad completa con Arnold. El instalador no tiene firma de código.
