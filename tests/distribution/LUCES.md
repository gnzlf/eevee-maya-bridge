# Verificación de luces y atmósfera

Las pruebas gráficas crean escenas genéricas en un proceso de Maya separado. No deben ejecutarse en una sesión de trabajo ni utilizan escenas o recursos del cliente.

## Casos

- `probe_area_ambient_gui.py`: area nativa y de Arnold, intensidad, orientación, escala y normalización; ambient, color, intensidad, ambientShade, posición, light linking, material por defecto y selección. Capturas a 1920×1080.
- `probe_spot_gui.py`: intensidad, distancia, movimiento del receptor, sombras, escala del icono, dropoff, dirección, cono, selección y cámara trasladada/rotada.
- `probe_local_volume_gui.py`: point y directional sobre una superficie; intensidad, color, selección y light linking; directional desde arriba; point independiente de su rotación. Comprueba además la atmósfera de point, area y spot, el botón real de activación y sus controles de volumen, color y selección. Point ilumina en todas direcciones; area respeta su orientación y spot conserva el cono.
- Con `EEVEE_LOCAL_VOLUME_PHASE=shadows`, el último script verifica los botones nativos de sombras y los vínculos de sombras de point, area, directional y spot. También comprueba la oclusión de la atmósfera de point, area y spot con una placa opaca. Compara la contribución luminosa contra una captura de intensidad cero porque la niebla sobre el fondo de Maya puede tener un nivel distinto de negro.

## Perfil obligatorio

`probe_local_volume_gui.py` exige `EEVEE_LOCAL_VOLUME_PROBE` apuntando a una carpeta de salida y `MAYA_APP_DIR` a `<salida>/local_volume_regression_profile`. Ejecutarlo con Maya gráfico, OpenGL Core Profile, `-noAutoloadPlugins`, `MAYA_SKIP_USERSETUP_PY=1` y un `MAYA_MODULE_PATH` vacío para el perfil. El script importa el bridge del repositorio y se inicia mediante `runpy.run_path`; no conecta puertos al Maya del usuario.

Los resultados, errores, PID y capturas se guardan en esa carpeta. La sesión se cierra al terminar; si Maya no finaliza por sus evaluadores, comprobar el PID, executable y línea de comandos del proceso creado antes de detenerlo. No identificar una sesión solamente por el nombre `maya.exe`.

## Uso en el viewport

Seleccionar la point, area o spot, abrir los ajustes de Eevee desde Renderer y, en **Luz**, pulsar **Activar volumetría en la luz seleccionada**. El botón activa la atmósfera y añade **Volumétrica Eevee** e **Intensidad de volumen** a la luz. En **Eevee** se ajustan densidad, color, anisotropía y alcance de la atmósfera. El botón nativo **Sombras** del viewport controla también las sombras de estas luces en la niebla.

Estas pruebas verifican comportamiento y controles en escenas acotadas. No certifican igualdad fotométrica con Arnold, equivalencia de decaimiento no cuadrático, light linking volumétrico por receptor, vínculos por caras ni todas las redes de materiales. La ambient usa una aproximación propia del bridge; no se certifica como fuente volumétrica global. El spread de area es una limitación de Eevee ([manual de Blender 5.2](https://docs.blender.org/manual/en/5.2/render/eevee/limitations/limitations.html)); no debe considerarse equivalente a un cono de spotlight.
