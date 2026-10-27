Corrección de la opción Renderer > Eevee en Maya.

- Eevee vuelve a registrarse también cuando Maya utiliza DirectX 11. En ese modo muestra un aviso nativo y su cuadradito abre la configuración de OpenGL Core Profile para el siguiente inicio. El render de Eevee sigue requiriendo OpenGL; la entrada DirectX es una guía de compatibilidad.
- El botón de configuración guarda la preferencia cuando lo pulsas. No cambia el contexto gráfico, modifica escenas, guarda proyectos ni cierra Maya. Guarda tu trabajo y reinicia después. Si MAYA_VP2_DEVICE_OVERRIDE fuerza DirectX, se explica que debe retirarse del lanzador o de Maya.env.
- Se reintenta el registro si Viewport 2.0 aún no está listo al cargar el plugin. Los reintentos son limitados y se cancelan al descargarlo. Eevee > Restaurar opción Renderer > Eevee permite volver a registrar la opción sin arrancar Blender.
- El aviso DirectX evita iniciar el proceso Blender o ejecutar operaciones OpenGL en un contexto incompatible. Los intentos de captura en ese modo se marcan como inválidos.
- Diagnósticos separados por proceso. Las pruebas batch ya no reemplazan el último diagnóstico gráfico; DIAGNOSTICO_EN_MAYA.py prefiere el registro de su propia sesión.

Verificado en la interfaz real de Maya con DirectX 11 y con OpenGL Core Profile tras reiniciar el perfil de prueba. Incluye las optimizaciones de luces y herramientas de diagnóstico de 0.6.12.

Actualiza desde Eevee > Buscar actualizaciones, guarda tu trabajo y reinicia Maya. Comprueba en Plug-in Manager que eeveeBridge.py esté Loaded; activa Auto load si quieres conservarlo en siguientes inicios. Después elige Renderer > Eevee. Si aparece el aviso DirectX, abre su cuadradito y configura OpenGL Core Profile para el próximo inicio.
