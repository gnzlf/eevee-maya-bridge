Eevee Maya Bridge 0.6.14 corrige Smooth Mesh Preview: al pulsar 3, el viewport Eevee utiliza la geometría suavizada evaluada por Maya. 1 restaura la malla base y 2 conserva la superficie suavizada con el modo de jaula de Maya.

- Respeta el nivel de preview, las UV, las asignaciones de materiales por cara y por instancia, y los creases de la salida de Maya.
- Mantiene las deformaciones de skin animadas mediante el stream de puntos; no añade nodos ni aplica un Smooth permanente.
- Reconstruye los recursos cuando cambian el nivel o las reglas de suavizado para evitar combinar topología base con puntos subdivididos.

Verificación: pruebas aisladas de las teclas nativas, niveles 1/2/3, OpenSubdiv y Maya Catmull-Clark, UV, materiales, creases, instancias y skin animado; capturas reales en Eevee del cambio de silueta y de poses deformadas.

Más subdivisiones implican más evaluación, transferencia y memoria. Se utiliza el nivel del viewport; no implementa displacement ni los niveles de render de Arnold. El bridge sigue siendo experimental y no garantiza 30 FPS.

Instala la actualización y reinicia Maya para cargar el nuevo stream nativo. El instalador conserva las preferencias y la versión anterior.
