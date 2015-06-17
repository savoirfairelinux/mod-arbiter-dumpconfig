
from __future__ import print_function, with_statement, unicode_literals

#############################################################################

from collections import defaultdict, deque

import sys
import threading
import time

#############################################################################

import pymongo
from pymongo.errors import PyMongoError

#############################################################################

from alignak.basemodule import BaseModule
from alignak.daemons.arbiterdaemon import Arbiter
from alignak.objects.config import Config
from alignak.objects import Service
from alignak.log import logger
from alignak.objects.item import Item

#############################################################################

from .default import (
    DEFAULT_DATABASE_NAME,
    DEFAULT_DATABASE_HOST,
    DEFAULT_DATABASE_PORT,
    GLOBAL_CONFIG_COLLECTION_NAME,
)
from .monitored_mutable import get_monitor_type_for
from .sanitize import (
    types_infos,
    accepted_types,
    sanitize_value,
    get_def_attr_value,
)

#############################################################################

_not_exist = object()  # a sentinel to be used..

#############################################################################

def get_object_unique_key(obj, infos):
    if isinstance(obj, Service):
        key = {}
        for k in ('host_name', 'service_description'):
            key[k] = getattr(obj, k)
    else:
        key = {'%s_name' % infos.singular: obj.get_name()}
    return key

#############################################################################


class LiveConfig(BaseModule):

    def __init__(self, mod_conf):
        super(LiveConfig, self).__init__(mod_conf)
        self._host = getattr(mod_conf, 'hostname', DEFAULT_DATABASE_HOST)
        self._port = int(getattr(mod_conf, 'port', DEFAULT_DATABASE_PORT))
        self._db_name = getattr(mod_conf, 'db', DEFAULT_DATABASE_NAME)
        self._hooked = False
        self._objects_updated = deque([self.make_objects_updates()])
        self._stop_requested = False
        self._thread = self.make_thread()

    def make_thread(self):
        th = threading.Thread(target=self._thread_run, name='mongo_liveconfig_monitor')
        th.daemon = True
        return th

    def quit(self):
        self._stop_requested = True
        if self._thread.isAlive():
            logger.debug("Waiting mongo live thread ..")
            self._thread.join()
            logger.info("mongo live thread successfully joined.")

    def _thread_run(self):
        con = None
        while not self._stop_requested:
            if con is None:
                try:
                    con = self._connect_to_mongo()
                    db = con[self._db_name]
                    db.collection_names()
                except PyMongoError as err:
                    logger.error("Could not connect to mongo: %s", err)
                    time.sleep(1)
                    continue

            objects = self.test_and_get_objects_updates()
            if not objects:
                time.sleep(1)
                continue
            # as we don't use any lock around _objects_updated,
            # this little sleep should ensure that no more threads
            # will be able to use the previous self._objects_updated
            # stored locally here in 'objects'.
            time.sleep(0.1)
            try:
                self.do_updates(db, objects)
            except Exception as err:
                logger.exception("Fatal error updating objects in mongo: %s", err)
                con = None

    def test_and_get_objects_updates(self):
        objects = self._objects_updated[0]
        if objects:
            self._objects_updated.append(self.make_objects_updates())
            self._objects_updated.popleft()
            return objects
        return None

    @staticmethod
    def make_objects_updates():
        # return a dict suitable for storing the objects updated
        # keys are Shinken objects type (Item, Host, ..)
        # values are defaultdict(dict) :
        #   with key: the object updated
        #      value: a set of updated attributes
        return defaultdict(lambda: defaultdict(set))

    def _connect_to_mongo(self):
        return pymongo.MongoClient(self._host, self._port,
                                   connectTimeoutMS=5000,
                                   #serverSelectionTimeoutMS=5000,
                                   socketTimeoutMS=7500)

    def hook_late_configuration(self, arbiter):
        pass
        # TODO : Not yet sure what's the best moment to do the job..
        # hook_late_configuration takes place BEFORE some late cleaning has
        # been applied to the services already.
        # While load_retention seems, for now, a better place.
        # So, for now, choosing hook_load_retention().

    def hook_load_retention(self, daemon):
        if not isinstance(daemon, Arbiter):
            return
        logger.info("Dumping config to mongo ..")
        t0 = time.time()
        self.do_insert(daemon)
        logger.info("Mongo insert took %s", (time.time() - t0))

    def do_insert(self, arbiter):
        try:
            with self._connect_to_mongo() as conn:
                self._do_insert(conn, arbiter)
        except Exception as err:
            logger.exception("I got a fatal error: %s", err)
            sys.exit("I'm in devel/beta mode and I prefer to exit for now,"
                     "please open a ticket with this exception details, thx :)")

    def _do_insert(self, conn, arbiter):
        """Do that actual insert(or update) job.
        :param arbiter: The arbiter object.
        :return:
        """
        db = conn[self._db_name]

        for cls, infos in types_infos.items():
            if cls is Config:
                continue  # special cased below ..
            collection = db[infos.plural]
            collection.drop()
            if pymongo.version >= "2.7":
                bulkop = collection.initialize_unordered_bulk_op()
            objects = getattr(arbiter.conf, infos.plural)
            for obj in objects:
                dobj = {}  # the mongo document which will be stored..
                for attr in infos.accepted_properties:
                    # would we use a default value for this attribute
                    # if the object wouldn't have it ?
                    def_val_args = get_def_attr_value(attr, cls)

                    try:
                        val = getattr(obj, attr, *def_val_args)
                    except AttributeError:
                        pass
                    else:
                        val = sanitize_value(cls, obj, attr, val)
                        if isinstance(val, accepted_types):
                            dobj[attr] = val
                        else:
                            raise RuntimeError(
                                "I'm not sure I could handle this type of value "
                                "and I'm in devel/beta mode,\n"
                                "so for now I prefer to prematurely exit.\n"
                                "type=%s, attr=%s, val=%s ; object=%s" %
                                (type(val), attr, val, obj)
                            )
                # end for attr in ..

                key = get_object_unique_key(obj, infos)
                try:
                    if pymongo.version >= "2.7":
                        bulkop.find(key).upsert().replace_one(dobj)
                    else:
                        collection.update(key, {"$set": dobj}, upsert=True)
                except Exception as err:
                    raise RuntimeError("Error on insert/update of %s-%s : %s" %
                                       (cls, obj.get_name(), err))

            # end for obj in objects..

            if objects and pymongo.version >= "2.7":
                # mongo requires at least one document for a bulkop.execute()
                try:
                    bulkop.execute()
                except Exception as err:
                    raise RuntimeError("Error on bulk execute for collection "
                                       "%s : %s" % (infos.plural, err))
        # end for cls, infos in types_infos.items()

        # special case for the global configuration values :
        collection = db[GLOBAL_CONFIG_COLLECTION_NAME]
        collection.drop()
        dglobal = {}
        macros = {}  # special case for alignak macros ($XXX$)
        for attr in types_infos[Config].accepted_properties:
            def_val_args = get_def_attr_value(attr, Config)
            try:
                value = getattr(arbiter.conf, attr, *def_val_args)
            except AttributeError:
                continue
            if not isinstance(value, accepted_types):
                continue
            value = sanitize_value(cls, obj, attr, value)
            # special case, mongo don't accept keys starting with '$',
            # and we'll put that in a subkey of the main document.
            if attr.startswith('$') and attr.endswith('$'):
                macros[attr[1:-1]] = value
            else:
                dglobal[attr] = value

        if 'macros' in dglobal:
            raise RuntimeError(
                "Daaamn, there was already a 'macros' attribute in the global"
                "configuration .. But I wanted to used to store the different "
                " \"resources macros\" ($USERXX$)\n"
                "Houston, we have a problem..")
        dglobal['macros'] = macros

        key = {'config_name': arbiter.conf.get_name()}
        collection.update(key, dglobal, True)

    ########################

    def hook_pre_scheduler_mod_start(self, scheduler, start_thread=True):
        if self._hooked:
            return

        self._hooked = True
        if start_thread:
            self._thread.start()

        # had to declare hooked_setattr "encapsulated" here
        # so to have access to 'self' (where we store the _objects_updated).
        def hooked_setattr(obj, attr, value):
            cls = obj.__class__
            type_infos = types_infos[cls]
            if attr in type_infos.accepted_properties:
                retain_change = True
                mon_type = get_monitor_type_for(value)
                if mon_type:
                    if not isinstance(value, mon_type):
                        value = mon_type(value, monitor=self, object=obj, attr=attr)
                    else:
                        if value._object != obj:
                            raise RuntimeError('WHAT !? obj=%s attr=%s value._object=%s' % (
                                obj, attr, value._object
                            ))
                elif value == getattr(obj, attr, _not_exist):
                    # only retain, for update, the new value if it's different
                    # than the previous one actually..
                    retain_change = False
                if retain_change:
                    self.retain(cls, obj, attr, value)
            super(Item, obj).__setattr__(attr, value)

        Item.__setattr__ = hooked_setattr

    def retain(self, cls, obj, attr, value):
        self._objects_updated[-1][cls][obj].add(attr)

    def do_updates(self, db, objs_updated):

        n_updated = 0
        tot_attr_updated = 0
        if __debug__:
            attributes_updated = set()

        t0 = time.time()

        for cls, objects in objs_updated.iteritems():
            infos = types_infos[cls]
            collection = db[infos.plural]
            if pymongo.version >= "2.7":
                bulkop = collection.initialize_unordered_bulk_op()

            for obj, attr_set in objects.iteritems():
                dest = {}
                dobj = {'$set': dest}

                key = get_object_unique_key(obj, infos)

                for attr in attr_set:
                    try:
                        value = getattr(obj, attr)
                    except AttributeError:
                        continue
                    dest[attr] = sanitize_value(cls, obj, attr, value)
                    if __debug__:
                        attributes_updated.add(attr)

                tot_attr_updated += len(dest)

                try:
                    if pymongo.version >= "2.7":
                        bulkop.find(key).upsert().update_one(dobj)
                    else:
                        collection.update(key, dobj, upsert=True)
                except Exception as err:
                    raise RuntimeError("Error on insert/update of %s : %s" %
                                       (obj.get_name(), err))
                n_updated += 1
            # end for obj, lst in objects.items()

            if objects and pymongo.version >= "2.7":
                # mongo requires at least one document for a bulkop.execute()
                try:
                    bulkop.execute()
                except Exception as err:
                    raise RuntimeError("Error on bulk execute for collection "
                                       "%s : %s" % (infos.plural, err))

        if n_updated:
            fmt = "updated %s objects with %s attributes in mongo in %s secs"
            args = [n_updated, tot_attr_updated, time.time() - t0]
            if __debug__:
                fmt += " attributes=%s"
                args.append(attributes_updated)
            logger.info(fmt, *args)

