"""Blender decode of native Maya samples and independent graph/data-space checks."""
import bpy,json,sys,os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'blender'));sys.path.insert(0,str(ROOT/'scripts'))
import worker
OUT=ROOT/'diagnostics/looks22';checks={};reports={}
image=bpy.data.images.load(str(OUT/'layered.exr'));image.colorspace_settings.name='Raw' if os.environ.get('EEVEE_NATIVE_OCIO') else 'Non-Color'
pixels=list(image.pixels);w,h=image.size;errors=[]
for expected in json.loads((OUT/'texture-reference.json').read_text()):
 i=4*((h-1-expected['y'])*w+expected['x']);errors.extend(abs(a-b) for a,b in zip(pixels[i:i+3],expected['rgb']))
checks['float_exr_matches_native_maya_uv_samples']=max(errors)<1e-5
checks['hdr_values_not_clamped']=max(pixels)>1
reports['sample_max_error']=max(errors)
spec={'name':'SharedColorAndData','kind':'standardSurface','color':[.8,.5,.2],'metallic':0,'roughness':.2,'emission':[0,0,0],'emission_strength':0,'transmission':0,
      'color_texture':{'path':str(OUT/'layered.exr'),'color_space':'ACEScg'},
      'roughness_texture':{'path':str(OUT/'layered.exr'),'color_space':'Raw','channel':'outColorR'}}
mat=worker.make_material(spec);images=[n for n in mat.node_tree.nodes if n.type=='TEX_IMAGE']
checks['shared_file_keeps_color_and_data_spaces_independent']=len(images)==2 and images[0].image!=images[1].image and images[0].image.colorspace_settings.name=='ACEScg' and images[1].image.colorspace_settings.is_data
shader=mat.node_tree.nodes['Principled BSDF'];source=shader.inputs['Roughness'].links[0].from_socket
checks['scalar_red_channel_reaches_roughness']=source.name=='Red'
spec.update(name='EyeShell',transmission=1,transmission_texture={'path':str(OUT/'layered.exr'),'color_space':'Raw','channel':'outColorR'},transmission_color_texture={'path':str(OUT/'layered.exr'),'color_space':'ACEScg'})
mat=worker.make_material(spec,True)
checks['transmission_masks_supported']=bool(mat.get('eevee_transmission_preview')) and any(n.type=='MIX_SHADER' and n.inputs[0].is_linked and n.inputs[0].links[0].from_node.type=='SEPARATE_COLOR' for n in mat.node_tree.nodes)
(OUT/'material-graph-result.json').write_text(json.dumps({'passed':all(checks.values()),'checks':checks,'reports':reports},indent=2))
print(json.dumps(checks,indent=2));assert all(checks.values()),checks
