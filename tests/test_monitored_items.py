
import cPickle


import mod_mongo_live_config.live_config as live_config
from mod_mongo_live_config.monitored_mutable import Monitored_List

from test_mongo_live_config import unittest


class FakeMonitor(object):
    def __init__(self):
        self.callcount = 0

    def retain(self, *a, **kw):
        self.callcount += 1


def pickle_unpickle(obj):
    return cPickle.loads(
        cPickle.dumps(obj)
    )


class Test_Monitored_Items(unittest.TestCase):

    def test_monitored_list(self):

        monitor = FakeMonitor()
        attr = 'an_attribute'

        monitored_list = Monitored_List([33], monitor=monitor, object=object(), attr=attr)
        self.assertEqual([33], monitored_list)
        p_obj = pickle_unpickle(monitored_list)
        self.assertIs(list, type(p_obj))
        self.assertEqual([33], p_obj)

        monitored_list = Monitored_List([], monitor=monitor, object=object(), attr=attr)
        self.assertEqual([], monitored_list)

        monitored_list.append(42)
        self.assertEqual([42], monitored_list)
        self.assertEqual(1, monitor.callcount)

        del monitored_list[:]
        self.assertEqual([], monitored_list)
        self.assertEqual(2, monitor.callcount)

        monitored_list.extend([1, 2, 3, 4])
        self.assertEqual([1, 2, 3, 4], monitored_list)
        self.assertEqual(3, monitor.callcount)
        p_obj = pickle_unpickle(monitored_list)
        self.assertIs(list, type(p_obj))
        self.assertEqual([1, 2, 3, 4], p_obj)

        monitored_list.pop(1)
        self.assertEqual([1, 3, 4], monitored_list)
        self.assertEqual(4, monitor.callcount)

        del monitored_list[0]
        self.assertEqual([3, 4], monitored_list)
        self.assertEqual(5, monitor.callcount)

        del monitored_list[:2]
        self.assertEqual([], monitored_list)
        self.assertEqual(6, monitor.callcount)
