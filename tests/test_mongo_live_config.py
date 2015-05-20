import copy
import sys

from setup_mongo import MongoServerInstance

from shinken.objects.host import Host


if sys.version_info[:2] < (3, 0):
    import unittest2 as unittest
else:
    import unittest


import shinken.objects.module

import mod_mongo_live_config
import mod_mongo_live_config.live_config


dictconf = (dict(
    module_name="we don't care",
    module_type="we don't care*2"
))


class SimpleTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.mongo = MongoServerInstance()
        dconf = dictconf.copy()
        dconf['port'] = cls.mongo.mongo_port
        modconf = shinken.objects.module.Module(dconf)
        cls.module_instance = mod_mongo_live_config.get_instance(modconf)

    @classmethod
    def tearDownClass(cls):
        cls.mongo.close()

    def test_hooked_is_ok(self):
        mod = self.module_instance
        self.assertFalse(mod._hooked)
        mod.hook_pre_scheduler_mod_start(None)
        self.assertTrue(mod._hooked)

    def test_simple_attr_assign(self):
        mod = self.module_instance
        mod.hook_pre_scheduler_mod_start(None)

        host = Host()
        host.host_name = "bla"
        self.assertIn(host, mod._objects_updated[Host],
                      'host should have been added.')
        self.assertIn('host_name', mod._objects_updated[Host][host],
                      'host_name should be present in the host modified keys')
        self.assertEqual('bla', mod._objects_updated[Host][host]['host_name'])
        mod.hook_scheduler_tick(None)
        self.assertNotIn(host, mod._objects_updated[Host],
                         "after the scheduler hook the updated objects "
                         "should be reset")

    # TODO: continue


