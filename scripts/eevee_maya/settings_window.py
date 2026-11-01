"""Maya-styled settings editing the real viewport attributes, not duplicate switches."""
import maya.cmds as cmds
import maya.api.OpenMaya as om
from . import native_controls, shadow_quality
from . import graphics, maya_lights, hdri, light_photometry
from .ui import QtCore

WINDOW = "eeveeViewportSettings"
INTERACTION_SAMPLES = (('1 · como Blender (más fluido)', 1), ('2', 2), ('4', 4),
                       ('Igual que Maya (sin reducir)', 0))
_window = None


class SettingsWindow:
    def __init__(self, controller):
        from . import ui
        self.controller = controller
        self.panel = controller.panel
        self.widgets = {}
        self.camera = None
        self.light = None
        self.hdri = None
        self.hdri_names = None
        self.hdri_image = None
        self.compatibility_only = False
        self.timer = QtCore.QTimer()
        if cmds.window(WINDOW, exists=True): cmds.deleteUI(WINDOW)
        self.window = cmds.window(WINDOW, title="Eevee · Viewport", widthHeight=(570, 690), sizeable=True)
        cmds.columnLayout(adjustableColumn=True, rowSpacing=8, columnAttach=("both", 10))
        camera_name = cmds.modelPanel(self.panel,query=True,camera=True).rsplit("|", 1)[-1]
        cmds.text(label="Eevee   ·   " + camera_name, align="left", font="boldLabelFont", height=28)
        self.status = cmds.text(label="", align="left", height=22)
        import maya.api.OpenMayaRender as render
        if render.MRenderer.drawAPI() == render.MRenderer.kDirectX11:
            self.compatibility_only = True
            cmds.text(label=graphics.DIRECTX_MESSAGE, align='left', wordWrap=True, height=60)
            cmds.text(label='Reinicia Maya para aplicar el cambio.', align='left', height=24)
            self.graphics_status = cmds.text(label='', align='left', wordWrap=True, height=40)
            cmds.button(label='Configurar OpenGL', command=self.configure_opengl)
            cmds.showWindow(self.window)
            return
        tabs = cmds.tabLayout(innerMarginWidth=8, innerMarginHeight=8)
        viewport_scroll = cmds.scrollLayout(childResizable=True)
        viewport_tab = cmds.columnLayout(adjustableColumn=True, rowSpacing=8)
        cmds.frameLayout(label='Vista', collapsable=False, marginWidth=8, marginHeight=8)
        cmds.columnLayout(adjustableColumn=True, rowSpacing=5)
        self.lighting = cmds.optionMenu(label="Iluminación", changeCommand=self.set_lighting)
        self.light_modes = [("Por defecto", "default"), ("Todas", "all"), ("Seleccionadas", "active"), ("Conjunto fijado", "selected"), ("Plana", "flat"), ("Sin luces", "none")]
        for label, _ in self.light_modes: cmds.menuItem(label=label)
        for flag, label in (("displayTextures", "Texturas"),):
            self.widgets[flag] = cmds.checkBox(label=label, changeCommand=lambda value, f=flag:self.set_panel(f, value))
        cmds.setParent('..'); cmds.setParent('..')
        cmds.frameLayout(label='Imagen', collapsable=False, marginWidth=8, marginHeight=8)
        cmds.columnLayout(adjustableColumn=True, rowSpacing=5)
        self.attribute("hardwareRenderingGlobals.ssaoEnable", "Oclusión ambiental")
        self.attribute("hardwareRenderingGlobals.multiSampleEnable", "Antialiasing")
        cmds.setParent('..'); cmds.setParent('..')
        cmds.frameLayout(label='Más opciones', collapsable=True, collapse=True, marginWidth=8, marginHeight=8)
        cmds.columnLayout(adjustableColumn=True, rowSpacing=5)
        for flag, label in (("depthOfFieldPreview", "Vista previa de profundidad de campo"),
                            ("useDefaultMaterial", "Material por defecto"), ("wireframeOnShaded", "Alambre sobre sombreado")):
            self.widgets[flag] = cmds.checkBox(label=label, changeCommand=lambda value, f=flag:self.set_panel(f, value))
        self.attribute("hardwareRenderingGlobals.ssaoRadius", "Radio AO")
        self.attribute("hardwareRenderingGlobals.ssaoAmount", "Intensidad AO")
        self.attribute("hardwareRenderingGlobals.multiSampleCount", "Muestras AA")
        cmds.setParent('..'); cmds.setParent('..')
        cmds.frameLayout(label='Rendimiento', collapsable=True, collapse=True, marginWidth=8, marginHeight=8)
        cmds.columnLayout(adjustableColumn=True, rowSpacing=5)
        cmds.checkBox(label='Calidad adaptativa', value=bool(controller.engine.config.get('adaptive_quality',True)),
                      changeCommand=self.set_adaptive_quality)
        edit_width=cmds.optionMenu(label='Resolución al editar',changeCommand=self.set_interaction_width)
        for width in (640,960,1280,1920):cmds.menuItem(label=str(width))
        cmds.optionMenu(edit_width,edit=True,value=str(controller.engine.config.get('interaction_width',960)))
        cmds.checkBox(label='Navegación rápida',value=bool(controller.engine.config.get('fast_navigation',True)),
                      changeCommand=lambda value:self.set_navigation('fast_navigation',bool(value)))
        navigation=cmds.optionMenu(label='Resolución al navegar',changeCommand=lambda value:self.set_navigation('navigation_width',int(value)))
        for width in (320,480,640,960,1280,1920):cmds.menuItem(label=str(width))
        cmds.optionMenu(navigation,edit=True,value=str(controller.engine.config.get('navigation_width',640)))
        samples=cmds.optionMenu(label='Muestras AA al moverse',changeCommand=self.set_interaction_samples,
                                annotation='Muestras mientras navegas, editas o reproduces. Al soltar se usan las Muestras AA de Maya.')
        for label,_ in INTERACTION_SAMPLES:cmds.menuItem(label=label)
        current=int(controller.engine.config.get('interaction_samples',1))
        cmds.optionMenu(samples,edit=True,value=next((label for label,value in INTERACTION_SAMPLES if value==current),INTERACTION_SAMPLES[0][0]))
        cmds.setParent('..'); cmds.setParent('..')
        cmds.setParent(tabs)
        shadow_scroll = cmds.scrollLayout(childResizable=True)
        shadow_tab = cmds.columnLayout(adjustableColumn=True, rowSpacing=8)
        cmds.frameLayout(label='Sombras', collapsable=False, marginWidth=8, marginHeight=8)
        cmds.columnLayout(adjustableColumn=True, rowSpacing=5)
        self.shadow_enabled = cmds.checkBox(label='Sombras del viewport de Maya',
                                            changeCommand=lambda value:self.set_panel('shadows', value))
        values = shadow_quality.resolve(controller.engine.config)
        self.shadow_quality = cmds.optionMenu(label='Calidad de sombras', changeCommand=self.set_shadow_quality)
        for label, key in shadow_quality.LABELS: cmds.menuItem(label=label)
        cmds.optionMenu(self.shadow_quality, edit=True,
                        value=next(label for label,key in shadow_quality.LABELS if key==values['preset']))
        cmds.setParent('..'); cmds.setParent('..')
        cmds.frameLayout(label='Avanzado', collapsable=True, collapse=True, marginWidth=8, marginHeight=8)
        cmds.columnLayout(adjustableColumn=True, rowSpacing=5)
        self.shadow_pool = cmds.optionMenu(label='Memoria de sombras', changeCommand=self.set_shadow_pool)
        cmds.menuItem(label='Automática según calidad')
        for pool in shadow_quality.POOLS: cmds.menuItem(label=pool+' MB')
        pool = str(controller.engine.config.get('shadow_pool_size', 'auto'))
        cmds.optionMenu(self.shadow_pool, edit=True,
                        value=pool+' MB' if pool in shadow_quality.POOLS else 'Automática según calidad')
        cmds.setParent('..'); cmds.setParent('..')
        cmds.button(label='Editar luz seleccionada', command=lambda *_:cmds.tabLayout(tabs, edit=True, selectTab=light_tab))
        cmds.setParent(tabs)
        camera_scroll = cmds.scrollLayout(childResizable=True)
        camera_tab = cmds.columnLayout(adjustableColumn=True, rowSpacing=8)
        cmds.frameLayout(label='Enfoque', collapsable=False, marginWidth=8, marginHeight=8)
        cmds.columnLayout(adjustableColumn=True, rowSpacing=5)
        cmds.button(label='Activar profundidad de campo',command=self.enable_dof)
        cmds.button(label='Enfocar selección',command=self.focus_selection)
        cmds.button(label='Enfocar con clic',command=self.pick_focus)
        self.dof_status=cmds.text(label='',align='left',height=22)
        cmds.setParent('..'); cmds.setParent('..')
        cmds.frameLayout(label='Cámara', collapsable=True, collapse=True, marginWidth=8, marginHeight=8)
        self.camera_column = cmds.columnLayout(adjustableColumn=True, rowSpacing=5)
        cmds.setParent(tabs)
        light_tab = cmds.scrollLayout(childResizable=True)
        light_controls=cmds.columnLayout(adjustableColumn=True,rowSpacing=6)
        cmds.frameLayout(label='Iluminación', collapsable=False, marginWidth=8, marginHeight=8)
        cmds.columnLayout(adjustableColumn=True, rowSpacing=5)
        self.intensity_mode=cmds.optionMenu(label='Intensidad de las luces',changeCommand=self.set_intensity_mode)
        for label,key in light_photometry.LABELS:cmds.menuItem(label=label)
        mode=controller.engine.config.get('light_intensity_mode','viewport2')
        cmds.optionMenu(self.intensity_mode,edit=True,value=next(label for label,key in light_photometry.LABELS if key==mode))
        cmds.button(label='Activar volumen en luz seleccionada',command=self.prepare_volume)
        cmds.button(label='Light Linking…',command=self.open_light_linking)
        cmds.setParent('..'); cmds.setParent('..')
        cmds.frameLayout(label='Atributos de la luz seleccionada', collapsable=True, collapse=True, marginWidth=8, marginHeight=8)
        self.light_column=cmds.columnLayout(adjustableColumn=True,rowSpacing=5)
        cmds.setParent(light_controls)
        cmds.setParent(tabs)
        hdri_tab=cmds.scrollLayout(childResizable=True)
        hdri_controls=cmds.columnLayout(adjustableColumn=True,rowSpacing=8)
        cmds.frameLayout(label='Entorno HDRI', collapsable=False, marginWidth=8, marginHeight=8)
        cmds.columnLayout(adjustableColumn=True,rowSpacing=5)
        self.hdri_menu=cmds.optionMenu(label='SkyDome',changeCommand=self.choose_hdri)
        cmds.button(label='Usar SkyDome seleccionada',command=self.selected_hdri)
        cmds.button(label='Crear SkyDome y cargar HDRI…',command=self.create_hdri)
        cmds.button(label='Cargar imagen…',command=self.load_hdri)
        cmds.setParent('..'); cmds.setParent('..')
        cmds.frameLayout(label='Ajustes del entorno', collapsable=True, collapse=False, marginWidth=8, marginHeight=8)
        self.hdri_column=cmds.columnLayout(adjustableColumn=True,rowSpacing=6)
        cmds.setParent(hdri_controls)
        cmds.frameLayout(label='Avanzado', collapsable=True, collapse=True, marginWidth=8, marginHeight=8)
        cmds.columnLayout(adjustableColumn=True,rowSpacing=5)
        self.reflection_quality=cmds.optionMenu(label='Detalle de reflejos',changeCommand=self.set_hdri_resolution)
        for label in ('Nativo','1024','2048','4096'):cmds.menuItem(label=label)
        minimum=int(controller.engine.config.get('hdri_resolution',2048))
        cmds.optionMenu(self.reflection_quality,edit=True,value=str(minimum) if minimum else 'Nativo')
        cmds.button(label='Usar todas las luces',command=lambda *_:self.set_lighting('Todas'))
        cmds.setParent('..'); cmds.setParent('..')
        cmds.setParent(tabs)
        effects_scroll = cmds.scrollLayout(childResizable=True)
        effects_tab = cmds.columnLayout(adjustableColumn=True, rowSpacing=8)
        cmds.frameLayout(label='Efectos', collapsable=False, marginWidth=8, marginHeight=8)
        cmds.columnLayout(adjustableColumn=True,rowSpacing=5)
        self.attribute("hardwareRenderingGlobals.bloomEnable", "Bloom de viewport")
        self.attribute("hardwareRenderingGlobals.bloomThreshold", "Umbral")
        self.attribute("hardwareRenderingGlobals.bloomAmount", "Intensidad")
        cmds.setParent('..'); cmds.setParent('..')
        cmds.frameLayout(label='Atmósfera', collapsable=True, collapse=True, marginWidth=8, marginHeight=8)
        cmds.columnLayout(adjustableColumn=True,rowSpacing=5)
        node = ui.scene_settings(select=False)
        for attr, label in (("volumetrics", "Atmósfera volumétrica Eevee"), ("density", "Densidad"),
                            ('fogAutoRange','Alcance automático'), ("fogDistance","Alcance (cm)"),
                            ("fogColor", "Color"), ("anisotropy", "Anisotropía")):
            self.attribute(node+"."+attr, label)
        cmds.setParent('..'); cmds.setParent('..')
        cmds.frameLayout(label='Calidad', collapsable=False, marginWidth=8, marginHeight=8)
        cmds.columnLayout(adjustableColumn=True,rowSpacing=5)
        menu = self.quality = cmds.optionMenu(label="Ancho del render", changeCommand=self.set_render_width)
        for width in (320, 640, 960, 1280, 1920): cmds.menuItem(label=str(width))
        cmds.optionMenu(menu, edit=True, value=str(controller.engine.config["max_width"]))
        cmds.setParent('..'); cmds.setParent('..')
        self.tabs=tabs;self.hdri_tab=hdri_tab
        cmds.tabLayout(tabs, edit=True, tabLabel=((viewport_scroll,"Viewport"),(shadow_scroll,"Sombras"),(camera_scroll,"Cámara"),(light_tab,"Luces"),(hdri_tab,"Entorno"),(effects_scroll,"Eevee")))
        self.timer.timeout.connect(self.refresh)
        self.timer.start(500)
        cmds.scriptJob(uiDeleted=[self.window,self.timer.stop],runOnce=True)
        self.refresh()
        cmds.showWindow(self.window)

    @staticmethod
    def attribute(plug, label):
        if cmds.objExists(plug): return cmds.attrControlGrp(attribute=plug,label=label)

    def choose_hdri(self,*args):
        index=cmds.optionMenu(self.hdri_menu,query=True,select=True)-1
        self.hdri=self.hdri_names[index] if self.hdri_names and 0<=index<len(self.hdri_names) else None
        self.hdri_image=None
        self.refresh_hdri(rebuild=True)

    def selected_hdri(self,*args):
        selected=[name for name in maya_lights.selected() if cmds.nodeType(name)=='aiSkyDomeLight']
        if not selected:cmds.warning('Selecciona una Arnold SkyDome primero');return
        self.hdri=selected[0];self.hdri_names=None;self.refresh_hdri(rebuild=True)

    @staticmethod
    def hdri_file():
        files=cmds.fileDialog2(caption='Imagen HDRI lat-long',fileMode=1,fileFilter='HDRI (*.hdr *.exr);;Imágenes (*.png *.jpg *.tif *.tiff)')
        return files[0] if files else None

    def create_hdri(self,*args):
        path=self.hdri_file()
        if not path:return
        try:self.hdri=hdri.create(path)
        except (RuntimeError,ValueError) as error:cmds.warning(str(error));return
        self.hdri_names=None;self.refresh_hdri(rebuild=True);self.controller.force=True

    def load_hdri(self,*args):
        if not self.hdri:cmds.warning('Crea o elige una SkyDome primero');return
        path=self.hdri_file()
        if not path:return
        try:hdri.load_image(self.hdri,path)
        except (RuntimeError,ValueError) as error:cmds.warning(str(error));return
        self.refresh_hdri(rebuild=True);self.controller.force=True

    def show_hdri_background(self,value):
        if self.hdri and cmds.objExists(self.hdri+'.camera'):
            cmds.setAttr(self.hdri+'.camera',1 if value else 0)
            self.controller.force=True

    def refresh_hdri(self,rebuild=False):
        names=hdri.domes()
        if names!=self.hdri_names:
            for item in cmds.optionMenu(self.hdri_menu,query=True,itemListLong=True) or []:cmds.deleteUI(item)
            for name in names:cmds.menuItem(label=name.rsplit('|',1)[-1],parent=self.hdri_menu)
            if not names:cmds.menuItem(label='No hay SkyDome',parent=self.hdri_menu)
            if self.hdri not in names:self.hdri=next((n for n in maya_lights.selected() if n in names),names[0] if names else None)
            self.hdri_names=names;rebuild=True
        cmds.optionMenu(self.hdri_menu,edit=True,enable=bool(names),select=names.index(self.hdri)+1 if self.hdri in names else 1)
        connection=hdri.image_connection(self.hdri) if self.hdri else None
        signature=(self.hdri,connection)
        if signature!=self.hdri_image:rebuild=True
        if rebuild:
            for child in cmds.columnLayout(self.hdri_column,query=True,childArray=True) or []:cmds.deleteUI(child)
            old=cmds.setParent(query=True);cmds.setParent(self.hdri_column)
            self.hdri_background=None
            if self.hdri:
                cmds.frameLayout(label='Básico',collapsable=False,marginWidth=6,marginHeight=5)
                cmds.columnLayout(adjustableColumn=True,rowSpacing=4)
                self.attribute(self.hdri+'.visibility','Entorno activo')
                self.hdri_background=cmds.checkBox(label='Mostrar imagen de fondo',changeCommand=self.show_hdri_background)
                self.attribute(self.hdri+'.intensity','Intensidad')
                self.attribute(self.hdri+'.exposure','Exposición')
                cmds.setParent('..');cmds.setParent('..')
                cmds.frameLayout(label='Avanzado',collapsable=True,collapse=True,marginWidth=6,marginHeight=5)
                cmds.columnLayout(adjustableColumn=True,rowSpacing=4)
                self.attribute(self.hdri+'.resolution','Resolución')
                parent=cmds.listRelatives(self.hdri,parent=True,fullPath=True)[0]
                for axis in 'XYZ':self.attribute(parent+'.rotate'+axis,'Rotación '+axis)
                if connection:
                    self.attribute(connection[0]+'.'+connection[1],'Imagen HDRI')
                    self.attribute(connection[0]+'.colorSpace','Espacio de color')
                else:cmds.text(label='Sin imagen HDRI',align='left',height=20)
                cmds.setParent('..');cmds.setParent('..')
            else:cmds.text(label='Crea o selecciona una SkyDome.',align='left',height=22)
            cmds.setParent(old);self.hdri_image=signature
        if self.hdri and self.hdri_background:
            cmds.checkBox(self.hdri_background,edit=True,value=cmds.getAttr(self.hdri+'.camera')>0,
                          enable=cmds.getAttr(self.hdri+'.camera',settable=True))

    def configure_opengl(self, *args):
        try:
            message = graphics.configure_opengl(cmds)
        except RuntimeError as exc:
            cmds.warning('No se pudo guardar la preferencia gráfica: ' + str(exc))
            return
        cmds.text(self.graphics_status, edit=True, label=message)

    def set_panel(self, flag, value):
        cmds.modelEditor(self.panel,edit=True,**{flag:bool(value)})
        self.controller.force=True

    def set_lighting(self, label):
        mode=next(mode for text,mode in self.light_modes if text==label)
        cmds.modelEditor(self.panel,edit=True,displayLights=mode)
        self.controller.force=True

    def prepare_volume(self,*args):
        from . import ui
        lights=maya_lights.selected()
        if not lights:cmds.warning("Selecciona una luz Maya primero");return
        for light in lights:
            if not cmds.objExists(light+".eeveeVolume"):
                cmds.addAttr(light,longName="eeveeVolume",niceName="Volumetrica Eevee",attributeType="bool",defaultValue=True,keyable=True)
            if not cmds.objExists(light+".eeveeVolumeFactor"):
                cmds.addAttr(light,longName="eeveeVolumeFactor",niceName="Intensidad volumen Eevee",attributeType="double",defaultValue=1,minValue=0,softMaxValue=10,keyable=True)
            cmds.setAttr(light+".eeveeVolume",True)
        node=ui.scene_settings(select=False)
        cmds.setAttr(node+".volumetrics",True)
        self.light=None
        self.controller.force=True
        self.refresh()

    def set_adaptive_quality(self, value):
        self.controller.engine.config['adaptive_quality'] = bool(value)
        self.controller.force = True

    def set_navigation(self,key,value):
        self.controller.engine.config[key]=value
        self.controller.force=True

    def set_interaction_samples(self,label):
        value=next(value for text,value in INTERACTION_SAMPLES if text==label)
        self.controller.engine.config['interaction_samples']=value
        cmds.optionVar(intValue=('eeveeInteractionSamples',value))
        self.controller.force=True

    def set_interaction_width(self,value):
        width=int(value)
        self.controller.engine.config['interaction_width']=width
        cmds.optionVar(intValue=('eeveeInteractionWidth',width))
        self.controller.force=True

    def set_hdri_resolution(self,label):
        value=0 if label=='Nativo' else int(label)
        self.controller.engine.config['hdri_resolution']=value
        cmds.optionVar(intValue=('eeveeHdriResolution',value))
        self.controller.force=True

    def set_intensity_mode(self,label):
        mode=next(key for text,key in light_photometry.LABELS if text==label)
        self.controller.engine.config['light_intensity_mode']=mode
        cmds.optionVar(stringValue=('eeveeLightIntensityMode',mode))
        self.controller.force=True

    def set_render_width(self, value):
        self.controller.engine.config['max_width'] = int(value)
        self.controller.force = True

    def set_shadow_quality(self, label):
        key = next(key for text,key in shadow_quality.LABELS if text==label)
        self.set_shadow_preference('shadow_quality', key)

    def set_shadow_pool(self, label):
        self.set_shadow_preference('shadow_pool_size', label.split()[0] if label.endswith(' MB') else 'auto')

    def set_shadow_preference(self, key, value):
        self.controller.engine.config[key] = value
        cmds.optionVar(stringValue=(shadow_quality.PREFERENCES[key], value))
        self.controller.force = True

    def focus_selection(self,*args):
        selected=cmds.ls(selection=True,long=True) or []
        selected=[name for name in selected if not cmds.ls(name,dag=True,type=maya_lights.types()) and not cmds.ls(name,dag=True,type='camera')]
        if not selected:cmds.warning('Selecciona el objeto o componente que quieras enfocar');return
        from . import focus
        path=focus.camera_path(cmds.modelPanel(self.panel,query=True,camera=True))
        self.focus_point(path,focus.selection_point(path,selected))

    def focus_point(self,path,point):
        from . import focus
        distance=focus.depth(path,point)
        if distance<=0:cmds.warning('El punto está detrás de la cámara');return
        cmds.undoInfo(openChunk=True,chunkName='Eevee focus')
        try:
            value=om.MDistance(distance,om.MDistance.kCentimeters).asUnits(om.MDistance.uiUnit())
            cmds.setAttr(path.fullPathName()+'.focusDistance',value)
            self.enable_dof()
        finally:cmds.undoInfo(closeChunk=True)

    def pick_focus(self,*args):
        from . import focus
        import maya.api.OpenMayaUI as omui
        context='eeveePickFocusContext'
        previous=cmds.currentCtx()
        if cmds.draggerContext(context,exists=True):cmds.deleteUI(context)
        def pressed():
            try:
                panel=cmds.getPanel(underPointer=True)
                if panel!=self.panel:
                    cmds.warning('Haz clic en el viewport Eevee activo');return
                x,y,_=cmds.draggerContext(context,query=True,anchorPoint=True)
                view=omui.M3dView.getM3dViewFromModelPanel(panel)
                origin,direction=om.MPoint(),om.MVector()
                view.viewToWorld(int(x),int(y),origin,direction)
                point=focus.ray_hit(origin,direction,focus.visible_meshes())
                if point is None:cmds.warning('No hay una superficie de malla bajo ese punto');return
                path=focus.camera_path(cmds.modelPanel(panel,query=True,camera=True))
                self.focus_point(path,point)
            finally:cmds.evalDeferred(lambda:cmds.setToolTo(previous))
        cmds.draggerContext(context,pressCommand=pressed,cursor='crossHair',space='screen',undoMode='step')
        cmds.setToolTo(context)
        cmds.inViewMessage(amg='Haz clic sobre la superficie que quieres enfocar. Q para salir sin enfocar.',pos='midCenter',fade=True)

    def enable_dof(self,*args):
        camera=cmds.modelPanel(self.panel,query=True,camera=True)
        selection=om.MSelectionList();selection.add(camera);path=selection.getDagPath(0)
        if path.node().hasFn(om.MFn.kTransform):path.extendToShape()
        cmds.setAttr(path.fullPathName()+'.depthOfField',True)
        cmds.modelEditor(self.panel,edit=True,depthOfFieldPreview=True)
        cmds.setAttr('hardwareRenderingGlobals.renderDepthOfField',True)
        self.controller.force=True
        self.refresh()

    @staticmethod
    def open_light_linking(*args):
        import maya.mel as mel
        mel.eval('LightCentricLightLinkingEditor;')

    def refresh(self):
        from . import ui
        if self.compatibility_only:
            return
        if not cmds.window(WINDOW,exists=True): self.timer.stop(); return
        if not cmds.modelPanel(self.panel,exists=True):
            self.timer.stop()
            cmds.deleteUI(self.window)
            return
        self.controller = ui.settings_context(self.panel)
        self.refresh_hdri()
        state=native_controls.read(self.panel)
        if cmds.checkBox(self.shadow_enabled,query=True,value=True)!=state['shadows']:
            cmds.checkBox(self.shadow_enabled,edit=True,value=state['shadows'])
        if cmds.optionMenu(self.quality,query=True,value=True)!=str(self.controller.engine.config["max_width"]):
            cmds.optionMenu(self.quality,edit=True,value=str(self.controller.engine.config["max_width"]))
        for flag,control in self.widgets.items():
            if cmds.checkBox(control,query=True,value=True)!=state[flag]:
                cmds.checkBox(control,edit=True,value=state[flag])
        label=next(text for text,mode in self.light_modes if mode==state["displayLights"])
        if cmds.optionMenu(self.lighting,query=True,value=True)!=label:
            cmds.optionMenu(self.lighting,edit=True,value=label)
        status=self.controller.engine.status
        if cmds.text(self.status,query=True,label=True)!=status:
            cmds.text(self.status,edit=True,label=status)
        camera=cmds.modelPanel(self.panel,query=True,camera=True)
        selection=om.MSelectionList(); selection.add(camera); path=selection.getDagPath(0)
        if path.node().hasFn(om.MFn.kTransform): path.extendToShape()
        camera=path.fullPathName()
        fn=om.MFnCamera(path)
        if not fn.isDepthOfField:
            dof_text='DOF apagado · cámara'
        elif not state['depthOfFieldPreview']:
            dof_text='DOF apagado · panel'
        elif not state['render_dof']:
            dof_text='DOF apagado · viewport'
        else:
            dof_text='DOF activo · %.1f cm · f/%.1f' % (fn.focusDistance,fn.fStop)
        if cmds.text(self.dof_status,query=True,label=True)!=dof_text:
            cmds.text(self.dof_status,edit=True,label=dof_text)
        if camera!=self.camera:
            for child in cmds.columnLayout(self.camera_column,query=True,childArray=True) or []: cmds.deleteUI(child)
            old=cmds.setParent(query=True); cmds.setParent(self.camera_column)
            cmds.text(label=camera.rsplit("|",1)[-1],align="left")
            for attr,label in (("depthOfField","DOF de la cámara"),("focusDistance","Distancia de enfoque"),
                               ("fStop","F Stop"),("focalLength","Distancia focal"),("focusRegionScale","Escala de región de foco")):
                self.attribute(camera+"."+attr,label)
            self.attribute("hardwareRenderingGlobals.renderDepthOfField","DOF global de viewport")
            cmds.setParent(old); self.camera=camera
        lights=maya_lights.selected()
        light=lights[0] if lights else ""
        if light!=self.light:
            for child in cmds.columnLayout(self.light_column,query=True,childArray=True) or []:cmds.deleteUI(child)
            old=cmds.setParent(query=True);cmds.setParent(self.light_column)
            cmds.text(label=light.rsplit("|",1)[-1] if light else "Ninguna luz seleccionada",align="left")
            if light:
                for attr,label in (("color","Color"),("intensity","Intensidad"),("aiExposure","Exposición Arnold"),
                                   ("ambientShade","Ambient Shade"),("normalize","Normalizar área"),("legacyIntensity","Intensidad Maya antigua"),
                                   ("aiSpread","Apertura de área Arnold"),("aiDiffuse","Difuso Arnold"),("aiSpecular","Especular Arnold"),
                                   ("decayRate","Decaimiento Maya"),("centerOfIllumination","Referencia de decaimiento"),
                                   ("coneAngle","Ángulo de cono"),("penumbraAngle","Penumbra"),("dropoff","Dropoff"),
                                   ("emitDiffuse","Emitir difuso"),("emitSpecular","Emitir especular"),
                                   ("lightRadius","Radio de sombra"),("lightAngle","Ángulo de sombra"),
                                   ("useRayTraceShadows","Proyectar sombras de trazado"),
                                   ("useDepthMapShadows","Sombras de mapa"),("eeveeVolume","Volumétrica Eevee"),
                                   ("eeveeVolumeFactor","Intensidad de volumen")):
                    if cmds.nodeType(light)=="directionalLight" and attr in ("decayRate","centerOfIllumination"):continue
                    self.attribute(light+"."+attr,label)
            cmds.setParent(old);self.light=light


def show(controller):
    global _window
    if controller is None:
        raise RuntimeError("Activa Eevee en un viewport antes de abrir sus ajustes")
    _window=SettingsWindow(controller)
    return _window.window
