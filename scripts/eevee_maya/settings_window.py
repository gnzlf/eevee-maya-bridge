"""Maya-styled settings editing the real viewport attributes, not duplicate switches."""
import maya.cmds as cmds
import maya.api.OpenMaya as om
from . import native_controls, shadow_quality
from . import graphics, maya_lights, hdri, light_photometry
from .ui import QtCore

WINDOW = "eeveeViewportSettings"
INTERACTION_SAMPLES = (('1 (más fluido)', 1), ('2', 2), ('4', 4), ('Igual que Maya', 0))
_window = None


LABEL = 141          # matches attrControlGrp label column, so all rows align
GAP = 3


def _row(label):
    """Label column + control column; the caller adds the control."""
    row = cmds.rowLayout(numberOfColumns=2, columnWidth2=(LABEL, 150), adjustableColumn=2,
                         columnAttach2=('right', 'left'), columnOffset2=(GAP, GAP))
    cmds.text(label=label, align='right')
    return row


def _menu(label, items, value=None, command=None, annotation=''):
    _row(label)
    menu = cmds.optionMenu(annotation=annotation)
    if command: cmds.optionMenu(menu, edit=True, changeCommand=command)
    for item in items: cmds.menuItem(label=item)
    if value is not None and value in items: cmds.optionMenu(menu, edit=True, value=value)
    cmds.setParent('..')
    return menu


def _check(label, value=False, command=None, annotation=''):
    _row('')
    box = cmds.checkBox(label=label, value=value, annotation=annotation)
    if command: cmds.checkBox(box, edit=True, changeCommand=command)
    cmds.setParent('..')
    return box


def _buttons(*pairs):
    """Buttons share the control column evenly and shrink with the window."""
    _row('')
    form = cmds.formLayout(height=26)
    buttons = [cmds.button(label=label, command=command, height=24) for label, command in pairs]
    step = 100.0 / len(buttons)
    cmds.formLayout(form, edit=True,
        attachForm=[(b, 'top', 1) for b in buttons],
        attachPosition=[(b, 'left', 1, int(round(i * step))) for i, b in enumerate(buttons)] +
                       [(b, 'right', 1, int(round((i + 1) * step))) for i, b in enumerate(buttons)])
    cmds.setParent('..'); cmds.setParent('..')
    return buttons


def _section(title):
    """Flat heading with a thin rule instead of nested boxed frames."""
    cmds.separator(style='none', height=8)
    cmds.text(label=title, align='left', font='boldLabelFont', height=18)
    cmds.separator(style='in', height=6)


def _more(title='Más opciones'):
    frame = cmds.frameLayout(label=title, collapsable=True, collapse=True, marginWidth=0, marginHeight=4,
                             borderVisible=False, font='plainLabelFont')
    cmds.columnLayout(adjustableColumn=True, rowSpacing=4)
    return frame


def _end_more():
    cmds.setParent('..'); cmds.setParent('..')


def _page():
    # One scroll per page that fills the tab: the page scrolls as a whole.
    scroll = cmds.scrollLayout(childResizable=True, horizontalScrollBarThickness=0, verticalScrollBarThickness=12)
    cmds.columnLayout(adjustableColumn=True, rowSpacing=4, columnAttach=('both', 10))
    return scroll


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
        self.hdri_widgets = {}
        self.compatibility_only = False
        self.timer = QtCore.QTimer()
        if cmds.window(WINDOW, exists=True): cmds.deleteUI(WINDOW)
        # A saved size from the old boxed layout would reopen it tiny.
        if cmds.windowPref(WINDOW, exists=True): cmds.windowPref(WINDOW, remove=True)
        self.window = cmds.window(WINDOW, title="Eevee", widthHeight=(470, 620), sizeable=True)
        form = cmds.formLayout()
        camera_name = cmds.modelPanel(self.panel,query=True,camera=True).rsplit("|", 1)[-1]
        header = cmds.columnLayout(adjustableColumn=True, rowSpacing=0, columnAttach=('both', 12))
        cmds.separator(style='none', height=8)
        self.title = cmds.text(label=camera_name, align="left", font="boldLabelFont", height=20)
        self.status = cmds.text(label="", align="left", height=18, font='smallPlainLabelFont')
        cmds.separator(style='none', height=4)
        cmds.setParent(form)
        import maya.api.OpenMayaRender as render
        if render.MRenderer.drawAPI() == render.MRenderer.kDirectX11:
            self.compatibility_only = True
            body = cmds.columnLayout(adjustableColumn=True, rowSpacing=8, columnAttach=('both', 12))
            cmds.text(label=graphics.DIRECTX_MESSAGE, align='left', wordWrap=True)
            cmds.text(label='Reinicia Maya para aplicar el cambio.', align='left')
            self.graphics_status = cmds.text(label='', align='left', wordWrap=True)
            cmds.button(label='Configurar OpenGL', command=self.configure_opengl, height=26)
            cmds.formLayout(form, edit=True,
                attachForm=[(header,'top',0),(header,'left',0),(header,'right',0),(body,'left',0),(body,'right',0)],
                attachControl=[(body,'top',4,header)])
            cmds.showWindow(self.window)
            return
        # The tab area is attached to every window edge, so it grows with the window.
        tabs = cmds.tabLayout(innerMarginWidth=0, innerMarginHeight=4, childResizable=True)
        cmds.formLayout(form, edit=True,
            attachForm=[(header,'top',0),(header,'left',0),(header,'right',0),
                        (tabs,'left',4),(tabs,'right',4),(tabs,'bottom',4)],
            attachControl=[(tabs,'top',0,header)])

        # Vista
        viewport_scroll = _page()
        _section('Vista')
        self.light_modes = [("Por defecto", "default"), ("Todas", "all"), ("Seleccionadas", "active"), ("Conjunto fijado", "selected"), ("Plana", "flat"), ("Sin luces", "none")]
        self.lighting = _menu("Iluminación", [label for label,_ in self.light_modes], command=self.set_lighting)
        self.widgets['displayTextures'] = _check('Texturas', command=lambda value:self.set_panel('displayTextures', value))
        self.attribute("hardwareRenderingGlobals.ssaoEnable", "Oclusión ambiental")
        self.attribute("hardwareRenderingGlobals.multiSampleEnable", "Antialiasing")
        _more()
        for flag, label in (("depthOfFieldPreview", "Vista previa de DOF"),
                            ("useDefaultMaterial", "Material por defecto"), ("wireframeOnShaded", "Alambre sobre sombreado")):
            self.widgets[flag] = _check(label, command=lambda value, f=flag:self.set_panel(f, value))
        self.attribute("hardwareRenderingGlobals.ssaoRadius", "Radio AO")
        self.attribute("hardwareRenderingGlobals.ssaoAmount", "Intensidad AO")
        self.attribute("hardwareRenderingGlobals.multiSampleCount", "Muestras AA")
        _end_more()
        _section('Efectos')
        self.attribute("hardwareRenderingGlobals.bloomEnable", "Bloom")
        self.attribute("hardwareRenderingGlobals.bloomThreshold", "Umbral")
        self.attribute("hardwareRenderingGlobals.bloomAmount", "Intensidad")
        _more('Atmósfera')
        node = ui.scene_settings(select=False)
        for attr, label in (("volumetrics", "Atmósfera volumétrica"), ("density", "Densidad"),
                            ('fogAutoRange','Alcance automático'), ("fogDistance","Alcance (cm)"),
                            ("fogColor", "Color"), ("anisotropy", "Anisotropía")):
            self.attribute(node+"."+attr, label)
        _end_more()
        cmds.setParent(tabs)

        # Luces y sombras
        light_tab = _page()
        _section('Luces')
        mode=controller.engine.config.get('light_intensity_mode','viewport2')
        self.intensity_mode=_menu('Intensidad', [label for label,_ in light_photometry.LABELS],
                                  next(label for label,key in light_photometry.LABELS if key==mode), self.set_intensity_mode)
        _buttons(('Light Linking…', self.open_light_linking), ('Volumen', self.prepare_volume))
        _section('Sombras')
        self.shadow_enabled = _check('Sombras', command=lambda value:self.set_panel('shadows', value))
        values = shadow_quality.resolve(controller.engine.config)
        self.shadow_quality = _menu('Calidad', [label for label,_ in shadow_quality.LABELS],
                                    next(label for label,key in shadow_quality.LABELS if key==values['preset']), self.set_shadow_quality)
        _more()
        pool = str(controller.engine.config.get('shadow_pool_size', 'auto'))
        self.shadow_pool = _menu('Memoria', ['Automática'] + [p+' MB' for p in shadow_quality.POOLS],
                                 pool+' MB' if pool in shadow_quality.POOLS else 'Automática', self.set_shadow_pool)
        _end_more()
        _section('Luz seleccionada')
        self.light_column=cmds.columnLayout(adjustableColumn=True,rowSpacing=4)
        cmds.setParent(tabs)

        # Entorno
        hdri_tab = _page()
        _section('HDRI')
        _row('SkyDome'); self.hdri_menu=cmds.optionMenu(changeCommand=self.choose_hdri); cmds.setParent('..')
        _buttons(('Usar selección', self.selected_hdri), ('Nueva…', self.create_hdri), ('Imagen…', self.load_hdri))
        self.hdri_column=cmds.columnLayout(adjustableColumn=True,rowSpacing=4)
        cmds.setParent('..')
        _more()
        minimum=int(controller.engine.config.get('hdri_resolution',2048))
        self.reflection_quality=_menu('Detalle de reflejos', ['Nativo','1024','2048','4096'],
                                      str(minimum) if minimum else 'Nativo', self.set_hdri_resolution)
        _end_more()
        cmds.setParent(tabs)

        # Cámara
        camera_scroll = _page()
        _section('Enfoque')
        _row(''); self.dof_status=cmds.text(label='',align='left',height=20); cmds.setParent('..')
        _buttons(('Activar DOF', self.enable_dof), ('Enfocar selección', self.focus_selection), ('Enfocar con clic', self.pick_focus))
        _section('Cámara')
        self.camera_column = cmds.columnLayout(adjustableColumn=True, rowSpacing=4)
        cmds.setParent(tabs)

        # Rendimiento
        performance_scroll = _page()
        _section('Resolución')
        self.quality = _menu('Ancho del render', ['320','640','960','1280','1920'], str(controller.engine.config["max_width"]), self.set_render_width)
        _section('Mientras te mueves')
        _check('Calidad adaptativa', bool(controller.engine.config.get('adaptive_quality',True)), self.set_adaptive_quality,
               'Reduce resolución y muestras al editar o reproducir; al soltar vuelve a la calidad completa.')
        _menu('Resolución al editar', ['640','960','1280','1920'], str(controller.engine.config.get('interaction_width',960)), self.set_interaction_width)
        current=int(controller.engine.config.get('interaction_samples',1))
        _menu('Muestras AA', [label for label,_ in INTERACTION_SAMPLES],
              next((label for label,value in INTERACTION_SAMPLES if value==current),INTERACTION_SAMPLES[0][0]), self.set_interaction_samples,
              'Muestras mientras navegas, editas o reproduces. Al soltar se usan las Muestras AA de Maya.')
        _check('Navegación rápida', bool(controller.engine.config.get('fast_navigation',True)),
               lambda value:self.set_navigation('fast_navigation',bool(value)))
        _menu('Resolución al navegar', ['320','480','640','960','1280','1920'], str(controller.engine.config.get('navigation_width',640)),
              lambda value:self.set_navigation('navigation_width',int(value)))
        cmds.setParent(tabs)

        self.tabs=tabs;self.hdri_tab=hdri_tab
        cmds.tabLayout(tabs, edit=True, tabLabel=((viewport_scroll,"Vista"),(light_tab,"Luces"),(hdri_tab,"Entorno HDRI"),
                                                  (camera_scroll,"Cámara"),(performance_scroll,"Rendimiento")))
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
                self.hdri_widgets={}
                def bound(plug,label):
                    control=self.attribute(plug,label)
                    if control:self.hdri_widgets[plug.rsplit('.',1)[-1]]=control
                bound(self.hdri+'.visibility','Activo')
                self.hdri_background=_check('Mostrar de fondo',command=self.show_hdri_background)
                bound(self.hdri+'.intensity','Intensidad')
                bound(self.hdri+'.exposure','Exposición')
                parent=cmds.listRelatives(self.hdri,parent=True,fullPath=True)[0]
                bound(parent+'.rotateY','Rotación')
                if connection:bound(connection[0]+'.'+connection[1],'Imagen')
                else:_row('');cmds.text(label='Sin imagen HDRI',align='left');cmds.setParent('..')
                _more('Avanzado')
                bound(self.hdri+'.resolution','Resolución')
                for axis in 'XZ':bound(parent+'.rotate'+axis,'Rotación '+axis)
                if connection:bound(connection[0]+'.colorSpace','Espacio de color')
                _end_more()
            else:_row('');cmds.text(label='Crea o elige una SkyDome.',align='left');cmds.setParent('..')
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
            cmds.text(self.title, edit=True, label=camera.rsplit("|",1)[-1])
            old=cmds.setParent(query=True); cmds.setParent(self.camera_column)
            for attr,label in (("depthOfField","DOF de la cámara"),("focusDistance","Enfoque"),
                               ("fStop","F Stop"),("focalLength","Focal"),("focusRegionScale","Región de foco")):
                self.attribute(camera+"."+attr,label)
            self.attribute("hardwareRenderingGlobals.renderDepthOfField","DOF global")
            cmds.setParent(old); self.camera=camera
        lights=maya_lights.selected()
        light=lights[0] if lights else ""
        if light!=self.light:
            for child in cmds.columnLayout(self.light_column,query=True,childArray=True) or []:cmds.deleteUI(child)
            old=cmds.setParent(query=True);cmds.setParent(self.light_column)
            _row('');cmds.text(label=light.rsplit("|",1)[-1] if light else "Selecciona una luz para editarla aquí.",align="left",font='plainLabelFont' if light else 'obliqueLabelFont');cmds.setParent('..')
            if light:
                for attr,label in (("color","Color"),("intensity","Intensidad"),("aiExposure","Exposición Arnold"),
                                   ("ambientShade","Ambient Shade"),("normalize","Normalizar área"),("legacyIntensity","Intensidad Maya antigua"),
                                   ("aiSpread","Apertura de área Arnold"),("aiDiffuse","Difuso Arnold"),("aiSpecular","Especular Arnold"),
                                   ("decayRate","Decaimiento Maya"),("centerOfIllumination","Ref. decaimiento"),
                                   ("coneAngle","Ángulo de cono"),("penumbraAngle","Penumbra"),("dropoff","Dropoff"),
                                   ("emitDiffuse","Emitir difuso"),("emitSpecular","Emitir especular"),
                                   ("lightRadius","Radio de sombra"),("lightAngle","Ángulo de sombra"),
                                   ("useRayTraceShadows","Sombras de trazado"),
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
