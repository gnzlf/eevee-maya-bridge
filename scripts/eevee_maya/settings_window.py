"""Maya-styled settings editing the real viewport attributes, not duplicate switches."""
import maya.cmds as cmds
import maya.api.OpenMaya as om
from . import native_controls
from .ui import QtCore

WINDOW = "eeveeViewportSettings"
_window = None


class SettingsWindow:
    def __init__(self, controller):
        from . import ui
        self.controller = controller
        self.panel = controller.panel
        self.widgets = {}
        self.camera = None
        self.light = None
        self.timer = QtCore.QTimer()
        if cmds.window(WINDOW, exists=True): cmds.deleteUI(WINDOW)
        self.window = cmds.window(WINDOW, title="Eevee · Ajustes del viewport", widthHeight=(490, 650), sizeable=True)
        cmds.columnLayout(adjustableColumn=True, rowSpacing=8, columnAttach=("both", 10))
        cmds.text(label="Eevee · " + cmds.modelPanel(self.panel,query=True,camera=True), align="left", font="boldLabelFont", height=28)
        self.status = cmds.text(label="", align="left", height=22)
        tabs = cmds.tabLayout(innerMarginWidth=8, innerMarginHeight=8)
        viewport_tab = cmds.columnLayout(adjustableColumn=True, rowSpacing=6)
        cmds.text(label="Los botones de la barra de Maya y estos controles comparten estado.", align="left", wordWrap=True)
        self.lighting = cmds.optionMenu(label="Iluminación", changeCommand=self.set_lighting)
        self.light_modes = [("Por defecto", "default"), ("Todas las luces", "all"), ("Seleccionadas", "active"), ("Conjunto fijado", "selected"), ("Iluminación plana", "flat"), ("Sin luces", "none")]
        for label, _ in self.light_modes: cmds.menuItem(label=label)
        for flag, label in (("shadows", "Sombras"), ("depthOfFieldPreview", "Vista previa de profundidad de campo"),
                            ("displayTextures", "Texturas"), ("useDefaultMaterial", "Material por defecto"),
                            ("wireframeOnShaded", "Alambre sobre sombreado")):
            self.widgets[flag] = cmds.checkBox(label=label, changeCommand=lambda value, f=flag:self.set_panel(f, value))
        cmds.separator(style="in", height=12)
        self.attribute("hardwareRenderingGlobals.ssaoEnable", "Ambient occlusion")
        self.attribute("hardwareRenderingGlobals.ssaoRadius", "Radio AO (píxeles)")
        self.attribute("hardwareRenderingGlobals.ssaoAmount", "Intensidad AO")
        cmds.text(label="AO en pantalla. Radio e intensidad compartidos con Viewport 2.0.", align="left", wordWrap=True)
        self.attribute("hardwareRenderingGlobals.multiSampleEnable", "Antialiasing")
        self.attribute("hardwareRenderingGlobals.multiSampleCount", "Muestras AA")
        cmds.text(label="El botón AA de Maya controla muestras de Eevee. Más muestras reducen ruido y pueden bajar los FPS.", align="left", wordWrap=True)
        cmds.setParent(tabs)
        camera_tab = cmds.columnLayout(adjustableColumn=True, rowSpacing=8)
        cmds.button(label='Enfocar la selección',command=self.focus_selection)
        self.camera_column = cmds.columnLayout(adjustableColumn=True, rowSpacing=6)
        cmds.setParent(camera_tab)
        cmds.text(label="Se usan los atributos de la cámara de Maya. El desenfoque sigue siendo un preview del puente y puede mostrar halos en siluetas.", align="left", wordWrap=True)
        cmds.setParent(tabs)
        light_tab = cmds.scrollLayout(childResizable=True)
        light_controls=cmds.columnLayout(adjustableColumn=True,rowSpacing=6)
        cmds.text(label="Selecciona una luz Maya para editar sus atributos nativos.",align="left",wordWrap=True)
        self.light_column=cmds.columnLayout(adjustableColumn=True,rowSpacing=6)
        cmds.setParent(light_controls)
        cmds.button(label="Activar volumetría en la luz seleccionada",command=self.prepare_volume)
        cmds.text(label="El haz necesita atmósfera. Este botón activa la atmósfera Eevee y añade controles de volumen a la luz.",align="left",wordWrap=True)
        cmds.text(label="Cono y penumbra siguen los ángulos de Maya. Dropoff se aproxima con luces concéntricas; el decaimiento se calibra en Center of Illumination.",align="left",wordWrap=True)
        cmds.text(label='Light linking: utiliza el Relationship Editor de Maya. Se traducen vínculos de objetos y de sombras.',align='left',wordWrap=True)
        cmds.button(label='Abrir Light Linking de Maya',command=self.open_light_linking)
        cmds.setParent(tabs)
        effects_tab = cmds.columnLayout(adjustableColumn=True, rowSpacing=6)
        self.attribute("hardwareRenderingGlobals.bloomEnable", "Bloom de viewport")
        self.attribute("hardwareRenderingGlobals.bloomThreshold", "Umbral bloom")
        self.attribute("hardwareRenderingGlobals.bloomAmount", "Intensidad bloom")
        cmds.separator(style="in", height=12)
        node = ui.scene_settings(select=False)
        for attr, label in (("volumetrics", "Atmósfera volumétrica Eevee"), ("density", "Densidad"),
                            ('fogAutoRange','Ajustar alcance a la escena'),
                            ("fogDistance","Alcance mínimo / manual (cm)"),
                            ("fogColor", "Color de niebla"), ("anisotropy", "Anisotropía")):
            self.attribute(node+"."+attr, label)
        cmds.separator(style="in", height=12)
        menu = self.quality = cmds.optionMenu(label="Ancho del render", changeCommand=lambda value:ui.set_quality(int(value)))
        for width in (320, 640, 960, 1280, 1920): cmds.menuItem(label=str(width))
        cmds.optionMenu(menu, edit=True, value=str(controller.engine.config["max_width"]))
        cmds.text(label="La iluminación admite Point, Spot, Directional y Area. La respuesta de luz y materiales puede diferir de Viewport 2.0 y Arnold.", align="left", wordWrap=True)
        cmds.text(label="Light linking por objeto y sombras. Los vínculos por caras, motion blur y luces especiales de Arnold siguen sin soporte.", align="left", wordWrap=True)
        cmds.tabLayout(tabs, edit=True, tabLabel=((viewport_tab,"Viewport"),(camera_tab,"Cámara"),(light_tab,"Luz"),(effects_tab,"Eevee")))
        self.timer.timeout.connect(self.refresh)
        self.timer.start(250)
        cmds.scriptJob(uiDeleted=[self.window,self.timer.stop],runOnce=True)
        self.refresh()
        cmds.showWindow(self.window)

    @staticmethod
    def attribute(plug, label):
        if cmds.objExists(plug): return cmds.attrControlGrp(attribute=plug,label=label)

    def set_panel(self, flag, value):
        cmds.modelEditor(self.panel,edit=True,**{flag:bool(value)})
        self.controller.force=True

    def set_lighting(self, label):
        mode=next(mode for text,mode in self.light_modes if text==label)
        cmds.modelEditor(self.panel,edit=True,displayLights=mode)
        self.controller.force=True

    def prepare_volume(self,*args):
        from . import ui
        lights=cmds.ls(selection=True,dag=True,type="light",long=True) or []
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

    def focus_selection(self,*args):
        selected=cmds.ls(selection=True,long=True) or []
        selected=[name for name in selected if not cmds.ls(name,dag=True,type='light') and not cmds.ls(name,dag=True,type='camera')]
        if not selected:cmds.warning('Selecciona el objeto o componente que quieras enfocar');return
        bounds=cmds.exactWorldBoundingBox(selected)
        # xform and bounding boxes use Maya's working units; MFnCamera uses cm.
        unit=om.MDistance.uiUnit()
        center=om.MPoint(*[om.MDistance((bounds[i]+bounds[i+3])*.5,unit).asCentimeters() for i in range(3)])
        selection=om.MSelectionList();selection.add(self.camera);path=selection.getDagPath(0)
        matrix=path.inclusiveMatrix()
        forward=om.MVector(-matrix[8],-matrix[9],-matrix[10]).normal()
        depth=(center-om.MPoint(matrix[12],matrix[13],matrix[14]))*forward
        if depth<=0:cmds.warning('La selección está detrás de la cámara');return
        fn=om.MFnCamera(path);fn.focusDistance=depth
        self.controller.force=True

    @staticmethod
    def open_light_linking(*args):
        import maya.mel as mel
        mel.eval('LightCentricLightLinkingEditor;')

    def refresh(self):
        from . import ui
        if not cmds.window(WINDOW,exists=True): self.timer.stop(); return
        if ui._controller is not self.controller:
            self.timer.stop()
            cmds.deleteUI(self.window)
            return
        state=native_controls.read(self.panel)
        if cmds.optionMenu(self.quality,query=True,value=True)!=str(self.controller.engine.config["max_width"]):
            cmds.optionMenu(self.quality,edit=True,value=str(self.controller.engine.config["max_width"]))
        for flag,control in self.widgets.items(): cmds.checkBox(control,edit=True,value=state[flag])
        label=next(text for text,mode in self.light_modes if mode==state["displayLights"])
        cmds.optionMenu(self.lighting,edit=True,value=label)
        cmds.text(self.status,edit=True,label=self.controller.engine.status)
        camera=cmds.modelPanel(self.panel,query=True,camera=True)
        selection=om.MSelectionList(); selection.add(camera); path=selection.getDagPath(0)
        if path.node().hasFn(om.MFn.kTransform): path.extendToShape()
        camera=path.fullPathName()
        if camera!=self.camera:
            for child in cmds.columnLayout(self.camera_column,query=True,childArray=True) or []: cmds.deleteUI(child)
            old=cmds.setParent(query=True); cmds.setParent(self.camera_column)
            cmds.text(label=camera.rsplit("|",1)[-1],align="left")
            for attr,label in (("depthOfField","DOF de la cámara"),("focusDistance","Distancia de enfoque"),
                               ("fStop","F Stop"),("focalLength","Distancia focal"),("focusRegionScale","Escala de región de foco")):
                self.attribute(camera+"."+attr,label)
            self.attribute("hardwareRenderingGlobals.renderDepthOfField","DOF global de viewport")
            cmds.setParent(old); self.camera=camera
        lights=cmds.ls(selection=True,dag=True,type="light",long=True) or []
        light=lights[0] if lights else ""
        if light!=self.light:
            for child in cmds.columnLayout(self.light_column,query=True,childArray=True) or []:cmds.deleteUI(child)
            old=cmds.setParent(query=True);cmds.setParent(self.light_column)
            cmds.text(label=light.rsplit("|",1)[-1] if light else "Ninguna luz seleccionada",align="left")
            if light:
                for attr,label in (("color","Color"),("intensity","Intensidad"),("aiExposure","Exposición Arnold"),
                                   ("decayRate","Decaimiento Maya"),("centerOfIllumination","Referencia de decaimiento"),
                                   ("coneAngle","Ángulo de cono"),("penumbraAngle","Penumbra"),("dropoff","Dropoff"),
                                   ("emitDiffuse","Emitir difuso"),("emitSpecular","Emitir especular"),
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
