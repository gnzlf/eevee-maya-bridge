"""Read-only audit of incoming material connections; never edits or evaluates meshes."""
import os
from .texture_paths import resolve


SUPPORTED = ('standardSurface', 'aiStandardSurface', 'lambert', 'blinn', 'phong', 'aiStandardVolume')
STANDARD = {'baseColor', 'metalness', 'specularRoughness', 'specularColor', 'opacity', 'emissionColor'}
CLASSIC = {'color', 'ambientColor', 'incandescence', 'specularColor'}
NORMAL = {'bump2d': 'bumpValue', 'aiBump2d': 'bumpMap', 'aiNormalMap': 'input'}


def audit(cmds, nodes=None, include_names=False):
    """Inspect all scene materials (including unused) unless nodes are supplied.

    Only the supplied command interface reads Maya. Default reports contain
    aliases and node types, without scene names, texture paths or exceptions.
    A known material family is still approximate, never certified identical.
    """
    all_materials = nodes is None
    nodes = sorted(set(cmds.ls(materials=True) or [])) if all_materials else sorted(set(nodes))
    materials = []
    for index, node in enumerate(nodes, 1):
        item = {'material_id': 'material_%03d' % index, 'kind': None, 'status': 'approximate', 'issues': []}
        if include_names:
            item['name'] = node

        def issue(code, attribute=None, source_kind=None):
            entry = {'code': code}
            if attribute is not None:
                entry['attribute'] = attribute
            if source_kind is not None:
                entry['source_kind'] = source_kind
            if entry not in item['issues']:
                item['issues'].append(entry)

        def check_file(source, attribute):
            path = cmds.getAttr(source + '.fileTextureName') or ''
            if path and not os.path.isabs(path):
                path = cmds.workspace(expandName=path)
            tiled = cmds.getAttr(source + '.uvTilingMode') == 3
            pattern = (cmds.getAttr(source + '.computedFileTextureNamePattern') or '') if tiled else ''
            if pattern and not os.path.isabs(pattern):
                pattern = cmds.workspace(expandName=pattern)
            if resolve(path, tiled, pattern) is None:
                issue('texture_not_readable', attribute, 'file')

        try:
            kind = item['kind'] = cmds.nodeType(node)
            if kind not in SUPPORTED:
                item['status'] = 'unsupported'
                issue('unsupported_shader')
            else:
                pairs = cmds.listConnections(node, source=True, destination=False,
                                             connections=True, plugs=True) or []
                textures = STANDARD if kind in ('standardSurface', 'aiStandardSurface') else CLASSIC
                if kind == 'lambert':
                    textures = CLASSIC - {'specularColor'}
                if kind == 'aiStandardVolume':
                    textures = set()  # Current volume translation reads constants.
                for destination, source in zip(pairs[::2], pairs[1::2]):
                    attribute = destination.split('.', 1)[-1]
                    if attribute == 'message':
                        continue
                    source_node, channel = source.split('.', 1)
                    source_kind = cmds.nodeType(source_node)
                    if attribute == 'normalCamera' and source_kind in NORMAL:
                        normal_input = source_node + '.' + NORMAL[source_kind]
                        files = cmds.listConnections(normal_input, source=True, destination=False, plugs=True) or []
                        if not files:
                            issue('normal_without_file_texture', attribute, source_kind)
                        for file_plug in files:
                            file_node, file_channel = file_plug.split('.', 1)
                            file_kind = cmds.nodeType(file_node)
                            if file_kind == 'file':
                                check_file(file_node, attribute)
                                if file_channel != 'outColor':
                                    issue('texture_channel_approximated', attribute, file_kind)
                            else:
                                issue('unsupported_normal_connection', attribute, file_kind)
                    elif attribute in textures and source_kind == 'file':
                        check_file(source_node, attribute)
                        if channel != 'outColor':
                            issue('texture_channel_approximated', attribute, source_kind)
                    else:
                        issue('untranslated_connection', attribute, source_kind)
        except (RuntimeError, ValueError, OSError):
            item['status'] = 'unreadable'
            issue('material_read_failed')
        materials.append(item)
    return {
        'schema': 1,
        'scope': 'all_scene_materials_including_unused' if all_materials else 'explicit_materials',
        'material_count': len(materials),
        'materials_with_issues': sum(bool(item['issues']) for item in materials),
        'unsupported_count': sum(item['status'] == 'unsupported' for item in materials),
        'unreadable_count': sum(item['status'] == 'unreadable' for item in materials),
        'notes': ['Revisión de conexiones entrantes y archivos; no certifica equivalencia visual ni inspecciona todo el grafo.',
                  'Los materiales conocidos siguen siendo aproximaciones aunque no se detecten incidencias.'],
        'materials': materials,
    }


def anonymized(report):
    return dict(report, materials=[{key: value for key, value in item.items() if key != 'name'}
                                   for item in report['materials']])
