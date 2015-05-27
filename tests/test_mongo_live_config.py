
import sys
import time

from setup_mongo import MongoServerInstance

from shinken.objects.host import Host


if sys.version_info[:2] < (3, 0):
    import unittest2 as unittest
else:
    import unittest


import shinken.objects.module

import mod_mongo_live_config
import mod_mongo_live_config.live_config


dictconf = dict(
    module_name="we don't care",
    module_type="we don't care*2"
)


class SimpleTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.mongo = MongoServerInstance()
        dconf = dictconf.copy()
        dconf['port'] = cls.mongo.mongo_port
        cls.modconf = shinken.objects.module.Module(dconf)

    @classmethod
    def tearDownClass(cls):
        cls.mongo.close()

    def setUp(self):
        self.module_instance = mod_mongo_live_config.get_instance(self.modconf)

    def tearDown(self):
        self.module_instance.quit()

    def test_simple_attr_assign(self):
        mod = self.module_instance

        mod.hook_pre_scheduler_mod_start(None, start_thread=False)

        objects = mod.test_and_get_objects_updates()
        self.assertFalse(objects)

        host = Host()
        # creating an Host already updates many of its attributes..
        # I prefer to know exactly what attributes I'm playing with,
        # so :
        mod.test_and_get_objects_updates()

        self.assertFalse(mod.test_and_get_objects_updates())

        # let's go:
        host.host_name = "bla"
        host.alias = "alias"

        objects = mod.test_and_get_objects_updates()

        self.assertIn(Host, objects)
        self.assertIn(host, objects[Host],
                      'host should have been added.')
        self.assertIn('host_name', objects[Host][host],
                      'host_name should be present in the host modified keys')
        self.assertEqual('bla', objects[Host][host]['host_name'])

        conn = mod._connect_to_mongo()
        db = conn['shinken_live']
        hosts_collection = db['hosts']
        result = hosts_collection.find_one(dict(host_name="bla"))
        self.assertFalse(result)

        # this is all the job :
        mod.do_updates(db, objects)

        result = hosts_collection.find_one(dict(host_name="bla"))
        self.assertTrue(result)
        del result['_id']
        self.assertEqual(dict(host_name='bla', alias='alias'), result)

    # TODO: continue


