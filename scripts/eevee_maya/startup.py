"""Startup milestones, with counts where available and no invented ETA."""
LABELS = {'starting': 'Iniciando motor', 'export': 'Leyendo escena de Maya',
          'materials': 'Preparando materiales', 'meshes': 'Preparando geometría',
          'shaders': 'Preparando shaders y primera imagen', 'presenting': 'Mostrando primera imagen'}


def label(progress):
    text = LABELS.get(progress.get('stage'), 'Preparando primera imagen')
    total = progress.get('total', 0)
    if total:
        text += ' · %d / %d' % (progress.get('completed', 0), total)
    return text
