from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
from eevee_maya.lighting import same_light_links, set_light_visibility


class LinkInvalidation(unittest.TestCase):
    def test_light_property_edits_keep_the_same_links(self):
        previous = {'receivers': ['meshA'], 'shadow_blockers': ['meshB'], 'intensity': 1, 'matrix': [1]}
        for key, value in [('intensity', 2), ('matrix', [2]), ('cone_angle', .8),
                           ('penumbra', .1), ('shadows', False), ('volume_factor', 3)]:
            current = dict(previous, **{key: value})
            self.assertTrue(same_light_links(current, previous))

    def test_each_native_link_edit_invalidates(self):
        previous = {'receivers': ['meshA'], 'shadow_blockers': ['meshB']}
        for field in ('receivers', 'shadow_blockers'):
            self.assertFalse(same_light_links(dict(previous, **{field: []}), previous))
            self.assertFalse(same_light_links(dict(previous, **{field: ['meshC']}), previous))

    def test_new_light_and_rebuilt_scene_initialize_links(self):
        self.assertFalse(same_light_links({'receivers': []}, None))
        self.assertFalse(same_light_links({}, None))

    def test_missing_and_explicit_empty_lists_are_not_equivalent(self):
        self.assertFalse(same_light_links({}, {'receivers': []}))
        self.assertFalse(same_light_links({'receivers': []}, {}))
        self.assertFalse(same_light_links({'shadow_blockers': []}, {}))
        self.assertTrue(same_light_links({}, {}))


class VisibilityWrites(unittest.TestCase):
    class Light:
        def __init__(self):
            self.hide_viewport = False
            self.hide_render = False
            self.writes = []

        def __setattr__(self, name, value):
            if name in ('hide_viewport', 'hide_render') and 'writes' in self.__dict__:
                self.writes.append((name, value))
            object.__setattr__(self, name, value)

    def test_repeated_visibility_does_not_write_rna(self):
        light = self.Light()
        for _ in range(20):
            set_light_visibility(light, True)
        self.assertEqual(light.writes, [])

    def test_hide_show_changes_both_render_and_viewport_once(self):
        light = self.Light()
        for _ in range(20):
            set_light_visibility(light, False)
        self.assertEqual(light.writes, [('hide_viewport', True), ('hide_render', True)])
        light.writes.clear()
        set_light_visibility(light, True)
        self.assertEqual(light.writes, [('hide_viewport', False), ('hide_render', False)])

    def test_mismatched_state_repairs_only_the_changed_flag(self):
        light = self.Light()
        light.hide_render = True
        light.writes.clear()
        set_light_visibility(light, True)
        self.assertEqual(light.writes, [('hide_render', False)])


if __name__ == '__main__':
    unittest.main()
