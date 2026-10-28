"""Blender background helper: preserve synthetic HDR float values in an EXR."""
from pathlib import Path
import sys
import bpy
output=Path(sys.argv[sys.argv.index('--')+1]).resolve()
source=bpy.data.images.load(str(output/'fixture.hdr'))
source.colorspace_settings.name='Non-Color'
image=bpy.data.images.new('Synthetic HDR EXR',width=source.size[0],height=source.size[1],float_buffer=True)
image.colorspace_settings.name='Non-Color'
image.pixels.foreach_set(source.pixels[:])
image.file_format='OPEN_EXR'
image.filepath_raw=str(output/'fixture.exr')
image.save()
