"""Eevee viewport bridge for Maya. Blender runs in a separate process."""
__version__ = "0.6.25"


def show():
    from . import ui
    return ui.attach()
