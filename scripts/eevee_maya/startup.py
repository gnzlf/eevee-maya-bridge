"""Startup milestones, with counts where available and no invented ETA."""
import unicodedata


def hud_text(text):
    """MUIDrawManager fonts drop or garble non-ASCII glyphs; keep viewport text plain."""
    text = str(text).replace('·', '-').replace('×', 'x').replace('…', '...')
    text = unicodedata.normalize('NFKD', text)
    return ''.join(ch for ch in text if not unicodedata.combining(ch)).encode('ascii', 'replace').decode('ascii')


LABELS = {'starting': 'Iniciando motor', 'export': 'Leyendo escena de Maya',
          'materials': 'Preparando materiales', 'meshes': 'Preparando geometría',
          'shaders': 'Preparando shaders y primera imagen', 'presenting': 'Mostrando primera imagen',
          'resume':'Actualizando vista Eevee'}


def label(progress):
    text = LABELS.get(progress.get('stage'), 'Preparando primera imagen')
    total = progress.get('total', 0)
    if total:
        text += ': %d de %d' % (progress.get('completed', 0), total)
    return text
