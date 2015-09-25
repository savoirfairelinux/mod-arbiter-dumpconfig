
import sys
import mock
from alignak.objects.config import Config

if sys.version_info[:2] < (3, 0):
    import unittest2 as unittest
else:
    import unittest

import alignak.objects.module
from alignak.objects.host import Host

import mod_mongo_live_config
import mod_mongo_live_config.live_config
from mod_mongo_live_config.default import DEFAULT_DATABASE_NAME

from setup_mongo import MongoServerInstance

dictconf = dict(
    module_name="we don't care",
    module_type="we don't care*2"
)


class NameSpace(object):
    pass


class SimpleTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.mongo = MongoServerInstance()
        dconf = dictconf.copy()
        dconf['port'] = cls.mongo.mongo_port
        cls.modconf = alignak.objects.module.Module(dconf)

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

        conn = mod._connect_to_mongo()
        db = conn[DEFAULT_DATABASE_NAME]
        hosts_collection = db['hosts']
        result = hosts_collection.find_one(dict(host_name="bla"))
        self.assertFalse(result)

        # this is all the job :
        mod.do_updates(db, objects)

        result = hosts_collection.find_one(dict(host_name="bla"))
        self.assertTrue(result)
        del result['_id']
        self.assertEqual(dict(host_name='bla', alias='alias'), result)

    def test_insert(self):
        mod = self.module_instance
        arbiter = NameSpace()
        conf = arbiter.conf = NameSpace()
        conf.get_name = lambda: "the-conf"

        from mod_mongo_live_config.sanitize import types_infos
        # print(types_infos)
        for cls, infos in types_infos.items():
            if cls is Config:
                continue
            objects = []
            setattr(conf, infos.plural, objects)

        # insert at least one host :
        conf.hosts.append(Host({
            'host_name': 'test_host',
        }))

        mod.do_insert(arbiter)

        conn = mod._connect_to_mongo()
        db = conn[DEFAULT_DATABASE_NAME]
        hosts_collection = db['hosts']

        result = hosts_collection.find_one(dict(host_name="test_host"))

        expected = {u'state_id_before_impact': 0, u'last_time_unreachable': 0, u'childs': [], u'business_rule': None, u'last_problem_id': 0, u's_time': 0.0, u'chk_depend_of': [], u'chk_depend_of_me': [], u'check_flapping_recovery_notification': True, u'last_state': u'PENDING', u'topology_change': False, u'my_own_business_impact': -1, u'last_hard_state_change': 0.0, u'was_in_hard_unknown_reach_phase': False, u'notifications_in_progress': {}, u'last_state_update': 0, u'execution_time': 0.0, u'start_time': 0, u'notified_contacts': [], u'flapping_comment_id': 0, u'early_timeout': 0, u'in_scheduled_downtime': False, u'long_output': u'', u'host_name': u'test_host', u'timeout': 0, u'output': u'', u'in_checking': False, u'check_type': 0, u'in_scheduled_downtime_during_last_check': False, u'source_problems': [], u'last_event_id': 0, u'service_includes': [], u'problem_has_been_acknowledged': False, u'last_state_type': u'HARD', u'downtimes': [], u'last_time_up': 0, u'last_hard_state': u'PENDING', u'processed_business_rule': u'', u'comments': [], u'last_check_command': u'', u'state': u'UP', u'is_problem': False, u'end_time': 0, u'tags': [], u'triggers': [], u'acknowledgement_type': 1, u'child_dependencies': [], u'flapping_changes': [], u'last_perf_data': u'', u'current_notification_number': 0, u'last_notification': 0.0, u'use': [], u'state_before_hard_unknown_reach_phase': u'UP', u'parent_dependencies': [], u'percent_state_change': 0.0, u'u_time': 0.0, u'last_state_id': 0, u'has_been_checked': 0, u'pending_flex_downtime': 0, u'act_depend_of_me': [], u'service_excludes': [], u'state_type_id': 0, u'scheduled_downtime_depth': 0, u'state_before_impact': u'PENDING', u'last_state_change': 0.0, u'duration_sec': 0, u'state_id': 0, u'perf_data': u'', u'is_impact': False, u'impacts': [], u'in_hard_unknown_reach_phase': False, u'should_be_scheduled': 1, u'latency': 0, u'state_changed_since_impact': False, u'current_event_id': 0, u'next_chk': 0, u'last_chk': 0, u'current_notification_id': 0, u'last_snapshot': 0, u'pack_id': -1, u'return_code': 0, u'customs': {}, u'in_maintenance': None, u'got_default_realm': False, u'got_business_rule': False, u'services': [], u'state_type': u'HARD', u'attempt': 0, u'act_depend_of': [], u'acknowledgement': None, u'last_time_down': 0, u'modified_attributes': 0L, u'current_problem_id': 0, u'is_flapping': False, u'last_hard_state_id': 0}
        del result['_id']
        self.assertEqual(expected, result)

    # TODO: continue



