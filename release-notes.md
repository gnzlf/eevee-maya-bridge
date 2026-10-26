Antialiasing durante animación y enfoque por superficie.

- La calidad adaptativa conserva las muestras AA seleccionadas en Maya durante reproducción, navegación y edición. Deja de imponer dos muestras al moverse. La reducción temporal a 960 píxeles sigue disponible; más muestras tienen coste de GPU.
- El autofoco sobre una malla usa la primera superficie visible en dirección al centro de la selección, en lugar del centro de su bounding box. Los componentes mantienen la profundidad seleccionada. Se consulta la cámara actual del panel y se respetan unidades y escala del rig.
- Nuevo botón en Ajustes > Cámara: «Enfocar un punto con un clic en el viewport». Permite enfocar un ojo o una zona concreta del rostro. No cambia la selección y vuelve a la herramienta anterior después del clic; Q permite salir sin enfocar.
- El enfoque establece el atributo nativo Focus Distance y activa los controles DOF de cámara, panel y viewport. Los cambios pueden deshacerse con Undo.
- El preview aplica DOF una sola vez: desactiva el desenfoque de Blender en la imagen de origen antes de la presentación con profundidad en Maya. Evita sumar dos desenfoques.

Validación en Maya 2024.2 y RTX 3070: diez comprobaciones de superficie, componentes, unidades y cámaras; enfoque y selección de punto en la escena de producción; comparación de cuatro poses animadas con AA2/AA8 frente a referencia AA16; pruebas de distribución e instalador. El desenfoque continúa siendo un preview, con posibles halos, y no reproduce el bokeh completo de Blender.

Actualiza desde Eevee > Buscar actualizaciones o instala el EXE del release y reinicia Maya después de guardar tu trabajo. No garantiza 30 FPS: conservar más muestras puede reducir la velocidad. El instalador no tiene firma de código.
