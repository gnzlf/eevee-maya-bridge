"""Eevee viewport bridge for Maya. Blender runs in a separate process."""
__version__ = "0.6.19"


def show():
    from . import ui
    return ui.attach()
