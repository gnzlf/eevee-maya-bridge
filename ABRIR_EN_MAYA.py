"""Drag this file into a Maya viewport or execute it in the Python Script Editor."""
import sys
from pathlib import Path


def onMayaDroppedPythonFile(*args):
    launch()


def launch():
    root = Path(__file__).resolve().parent
    scripts = str(root / "scripts")
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    import eevee_maya
    return eevee_maya.show()


if __name__ == "__main__":
    launch()
