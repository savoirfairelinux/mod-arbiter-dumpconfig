

import sys

if sys.version_info[:2] < (3, 0):
    import unittest2 as unittest
else:
    import unittest


import shinken.objects.module

import mod_mongo_live_config
import mod_mongo_live_config.live_config


modconf = shinken.objects.module.Module(dict(
    module_name="we don't care",
    module_type="we don't care*2"
))


class SimpleTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.module_instance = mod_mongo_live_config.get_instance(modconf)

    def test_hooked_is_ok(self):
        mod = self.module_instance
        self.assertFalse(mod._hooked)
        mod.hook_pre_scheduler_mod_start(None)
        self.assertTrue(mod._hooked)

    # TODO: continue


