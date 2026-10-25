# Componentes externos

- Blender: el instalador descarga la distribución portátil oficial de Blender 5.2.0 desde blender.org y verifica su SHA-256. Blender conserva sus avisos, licencias y acceso al código fuente: https://www.blender.org/about/license/ y https://download.blender.org/source/.
- Autodesk Maya no se distribuye con este proyecto. Maya 2024 de 64 bits debe estar instalado y disponer de su licencia correspondiente. Los headers y bibliotecas del SDK de Autodesk tampoco se incluyen.
- El puente usa las bibliotecas Python y Qt ya incluidas en Maya y en Blender. No instala paquetes pip dentro de Maya.
- Los binarios propios `eevee_scene.dll` y `eevee_gpu_v5.dll` se acompañan de sus fuentes en `native/`.
