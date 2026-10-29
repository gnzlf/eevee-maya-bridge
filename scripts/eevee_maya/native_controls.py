"""Read the same modelEditor/globals that Maya's own viewport toolbar edits."""
import math
import re
import maya.cmds as cmds

_enums = {}
_selected_lights = {}


def global_value(name, default):
    plug = "hardwareRenderingGlobals." + name
    return cmds.getAttr(plug) if cmds.objExists(plug) else default


def sample_count():
    name = "multiSampleCount"
    value = int(global_value(name, 3))
    if name not in _enums:
        entries = cmds.attributeQuery(name, node="hardwareRenderingGlobals", listEnum=True) or []
        mapping, index = {}, 0
        for entry in (entries[0].split(":") if entries else []):
            label, *explicit = entry.split("=")
            if explicit: index = int(explicit[0])
            number = re.match(r"\s*(\d+)", label)
            if number: mapping[index] = int(number.group(1))
            index += 1
        _enums[name] = mapping
    return max(1, min(64, _enums[name].get(value, 2 ** min(value, 6))))


def read(panel):
    result = {}
    for flag in ("displayLights", "shadows", "displayTextures", "useDefaultMaterial",
                 "depthOfFieldPreview", "wireframeOnShaded", "displayAppearance"):
        result[flag] = cmds.modelEditor(panel, query=True, **{flag: True})
    for flag,default in (('exposure',0),('gamma',1),('cmEnabled',True),('viewTransformName','')):
        try:result[flag]=cmds.modelEditor(panel,query=True,**{flag:True})
        except (RuntimeError,TypeError):result[flag]=default
    result.update(ao=bool(global_value("ssaoEnable", False)),
                  viewport_width=int(cmds.modelEditor(panel,query=True,width=True)),
                  ao_radius_pixels=float(global_value("ssaoRadius", 16)),
                  ao_amount=float(global_value("ssaoAmount", 1)),
                  aa=bool(global_value("multiSampleEnable", False)),
                  aa_samples=sample_count(),
                  render_dof=bool(global_value("renderDepthOfField", True)),
                  bloom=bool(global_value("bloomEnable", False)),
                  bloom_threshold=float(global_value("bloomThreshold", .8)),
                  bloom_amount=float(global_value("bloomAmount", 1)))
    mode=result["displayLights"]
    if mode in ("selected", "active"):
        from . import maya_lights
        selected = maya_lights.selected()
        # 'active' follows the current selection; 'selected' captures a preset
        # which remains lit while selecting geometry, as in Maya's Lighting menu.
        old=_selected_lights.get(panel)
        if mode=="active" or old is None or old[0]!=mode:
            _selected_lights[panel]=(mode,selected)
        result["selected_lights"] = selected if mode=="active" else _selected_lights[panel][1]
    else:_selected_lights.pop(panel,None)
    return result


def apply(snapshot, state):
    snapshot["native"] = state
    snapshot["samples"] = state["aa_samples"] if state["aa"] else 1
    camera = snapshot["camera"]
    camera["dof"] = bool(camera["dof"] and state["depthOfFieldPreview"] and state["render_dof"])
    focus = max(camera.get("focus_distance", 10), 1)
    state["ao_world_radius"] = max(.001, state["ao_radius_pixels"] / max(1,state.get("viewport_width",snapshot["width"]))
                                    * focus * 2 * math.tan(camera["fov_x"] / 2))
    snapshot["effects"].update(bloom=state["bloom"], bloom_threshold=state["bloom_threshold"],
                               bloom_strength=state["bloom_amount"])
    return snapshot
