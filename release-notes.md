Corrección de carga/descarga del plug-in cuando Maya devuelve `Unexpected Internal Failure` en Viewport 2.0.

- La descarga del plug-in siempre intenta retirar su comando, aunque falle la limpieza gráfica. Evita que `eeveeViewport` quede registrado y bloquee la carga siguiente.
- Un registro gráfico fallido no conserva una instancia inválida; la descarga comprueba si Maya ya retiró el viewport.
- El registro del viewport se intenta en el siguiente ciclo de reposo de Maya, después de instalar el menú. Un fallo gráfico ya no aborta la carga del plug-in.
- Diagnóstico completo en `%LOCALAPPDATA%\EeveeMayaBridge\diagnostics\plugin_load.json`, independiente de los permisos de la carpeta del plug-in.
- Se incluye `DIAGNOSTICO_EN_MAYA.py` para recopilar GPU, versión de Maya y errores de carga sin abrir ni guardar escenas.

Si 0.6.2 ya falló en esa sesión, guarda tu trabajo y cierra Maya. Instala esta versión y vuelve a iniciar Maya para retirar el comando residual de la sesión anterior. Mantén OpenGL/OpenGL Core Profile como motor del viewport.

Validación: 24 pruebas automáticas, instalación del EXE en un perfil separado, carga de las DLL y tres ciclos de carga/descarga del plug-in empaquetado con Maya 2024.2 en modo standalone. El Acer Nitro 5/RTX 3060 aún requiere verificación en el equipo del usuario.

El viewport continúa siendo experimental. Requiere Maya 2024 instalado; no garantiza 30 FPS ni paridad completa con Arnold. El instalador no tiene firma de código.
