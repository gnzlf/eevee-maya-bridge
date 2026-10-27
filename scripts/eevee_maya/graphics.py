"""Graphics compatibility messages and an explicit next-start preference change."""
import os

DIRECTX_MESSAGE = 'Maya está usando DirectX 11. El render de Eevee requiere OpenGL Core Profile.'
RESTART_MESSAGE = 'OpenGL Core Profile configurado. Guarda tu trabajo y reinicia Maya para activar Eevee.'


def configure_opengl(cmds):
    """Called only by the settings button. Never opens, saves or closes a scene."""
    cmds.optionVar(stringValue=('vp2RenderingEngine', 'OpenGLCoreProfile'))
    cmds.savePrefs(general=True)
    if os.environ.get('MAYA_VP2_DEVICE_OVERRIDE') == 'VirtualDeviceDx11':
        return ('Preferencia guardada. MAYA_VP2_DEVICE_OVERRIDE fuerza DirectX 11: '
                'retira esa variable de Maya.env o del lanzador de Maya antes de reiniciar.')
    return RESTART_MESSAGE
