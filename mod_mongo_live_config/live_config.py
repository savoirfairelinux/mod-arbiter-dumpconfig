
from __future__ import print_function, with_statement, unicode_literals

#############################################################################

from collections import defaultdict

import datetime
import sys
import threading
import time

#############################################################################

import pymongo

#############################################################################

from shinken.basemodule import BaseModule
from shinken.commandcall import CommandCall
from shinken.daemons.arbiterdaemon import Arbiter
from shinken.objects.config import Config
from shinken.objects import Service
from shinken.log import logger
from shinken.objects.host import Host
from shinken.objects.item import Item, Items
from shinken.objects.realm import Realm
from shinken.objects.timeperiod import Timeperiod
from shinken.property import none_object

#############################################################################

from .sanitize_shinken_object_value import sanitize_value

#############################################################################

GLOBAL_CONFIG_COLLECTION_NAME = "global_configuration"

_not_exist = object()  # a sentinel to be used..

_accepted_types = (
    # for each shinken object, we'll look at each of its attribute defined
    # in its class 'properties' and 'running_properties' dicts (+ few others
    # hardcoded one because we miss them in pre-mentioned dicts unfortun.. )

    # If the object attribute value isn't one of '_accepted_types'
    # then that attribute will simply be skipped !

    # "base" types:
    type(None),
    bool,
    int,
    long,
    float,
    str,
    unicode,

    # special types also understood by mongo:
    datetime.datetime,
    datetime.time,

    # "container" types :
    dict,
    tuple,
    list,
    set,
    frozenset,

    # shinken objects types:
    Item,
    CommandCall,   # CommandCall isn't subclass of Item actually
)

#############################################################################

_skip_attributes = (
    # these attributes will be globally skipped whatever are the values, if any
    'hash',
    'configuration_errors',
    'configuration_warnings',
    'broks',
    'actions',
)

_by_type_skip_attributes = {
    # for each shinken object type,
    # define the (list/tuple of) attributes to be also skipped.

    # timeperiod objects have a dateranges attribute,
    # but it's quite a complex object type and I'm not sure it's actually
    # needed within the mongo :
    Timeperiod: ('dateranges',),
    Realm: ('serialized_confs',),
    Config: ('confs', 'whole_conf_pack',),
    Host: ('checks_in_progress',),
    Service: ('checks_in_progress',),
}


#############################################################################
# various data handlers and settings to configure how the serialization
# from shinken objects to "json-like" objects will be done.

class TypeInfos(object):
    def __init__(self, singular, clss, plural, accepted_properties):
        self.singular = singular
        self.clss = clss
        self.plural = plural
        self.accepted_properties = accepted_properties


# just to save us to recompute this every time we need to work on a
# particular shinken object type :
def _build_types_infos():
    res = {}
    for _, (cls, clss, plural, _) in Config.types_creations.items():
        accepted_properties = set(cls.properties) | set(cls.running_properties)
        accepted_properties -= set(_skip_attributes)
        accepted_properties -= set(_by_type_skip_attributes.get(cls, ()))
        accepted_properties.add('use')
        res[cls] = TypeInfos(cls.__name__.lower(), clss, plural,
                             accepted_properties)

    # Config is a bit special (it has not "plural" class):
    ap = set(Config.properties) | set(Config.running_properties)
    ap -= set(_skip_attributes)
    ap -= set(_by_type_skip_attributes.get(Config, ()))
    res[Config] = TypeInfos('config', None, GLOBAL_CONFIG_COLLECTION_NAME, ap)
    return res

_types_infos = _build_types_infos()
del _build_types_infos

#############################################################################

_rename_prop = {
    # if you want to globally rename some attributes between shinken and mongo.
    # example:
    # 'attr_foo':   'attr_bar'
}

_by_type_rename_prop = {
    # same than _rename_prop but takes also into account the object class.
    # example:
    # Service: {
    #   'attr_foo':     'attr_bar'
    # }
}


def get_dest_attr(objtype, attr):
    destattr = _rename_prop.get(attr)
    if destattr:
        return destattr
    return _by_type_rename_prop.get(objtype, {}).get(attr, attr)

#############################################################################

_def_attr_value = {
    # if an attribute is missing on an object
    # then it'll get a default *handler* value from here,
    'use': lambda: [],  # that is the lambda will be executed
                        # and it's return value will be used as the default.
}

_by_type_def_attr_value = {
    # same, but with per type:
    # example:
    # Service: {
    #   'attr_foo': lambda: default_value_for_attr_foo_on_Service_object,
    #   ..
    # }
}


def get_default_attr_value_args(attr, cls):
    """ Return, in a single-element tuple, the default value to be used for an
        attribute named 'attr' and belonging to the class 'cls'.
        If no such default value exists, returns the empty tuple.
        So that the returned value can directly be used like this:
        >>> obj = Service()
        >>> attr = 'foo'
        >>> val = getattr(obj, attr, *get_default_attr_value_args(attr,
                                                                  Service))
    :param attr: The name of the attribute.
    :param cls: The class to which the attribute belongs to.
    """
    handler = _def_attr_value.get(attr)
    if not handler:
        handler = _by_type_def_attr_value.get(cls, {}).get(attr)
    if handler:
        return handler(),  # NB: don't miss the ',' !
    return ()

#############################################################################

_by_name_converter = {
    # for some attributes, I want to eventually adapt their value based on it:

    'use': lambda v: v if v else []  # so to be sure to not get None/0/..
                                     # for this attribute *BUT*: []

}

_by_type_name_converter = {
    # example:
    # Service: {
    #      'some_attr_name':   lambda value: str(value)  # say
    # }
}


def get_value_by_type_name_val(cls, attr, value):
    handler = _by_name_converter.get(attr)
    if not handler:
        handler = _by_type_name_converter.get(cls, {}).get(attr)
    if handler:
        return handler(value)
    return value

#############################################################################


class LiveConfig(BaseModule):

    def __init__(self, mod_conf):
        super(LiveConfig, self).__init__(mod_conf)
        self._host = getattr(mod_conf, 'hostname', '127.0.0.1')
        self._port = int(getattr(mod_conf, 'port', 27017))
        self._db_name = getattr(mod_conf, 'db', 'shinken_live')
        self._hooked = False
        self._lock = threading.Lock()
        self._objects_updated = self._make_objects_updates()

    @staticmethod
    def _make_objects_updates():
        # return a dict suitable for storing the objects updated
        # keys are Shinken objects type (Item, Host, ..)
        # values are defaultdict(dict) :
        #   with key: the object updated
        #      value: another dict of updated attributes
        #         with key: the attribute name
        #            value: the new attribute value
        return {cls: defaultdict(dict) for cls in _types_infos}

    def init(self):
        for objects in self._objects_updated.values():
            objects.clear()

    def _connect_db(self):
        return pymongo.MongoClient(self._host, self._port)

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
        t1 = time.time()
        logger.info("Mongo insert took %s", (t1 - t0))

    def do_insert(self, arbiter):
        try:
            with self._connect_db() as conn:
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
        for cls, infos in _types_infos.items():
            if cls is Config:
                continue  # special cased below ..
            collection = db[infos.plural]
            bulkop = collection.initialize_unordered_bulk_op()
            objects = getattr(arbiter.conf, infos.plural)
            for obj in objects:
                dobj = {}  # the mongo document which will be stored..
                for attr in infos.accepted_properties:
                    # would we use a default value for this attribute
                    # if the object wouldn't have it ?
                    def_val_args = get_default_attr_value_args(attr, cls)

                    try:
                        val = getattr(obj, attr, *def_val_args)
                    except AttributeError:
                        pass
                    else:
                        if val is none_object:
                            # special case for this unfortunately..
                            val = None

                        val = get_value_by_type_name_val(cls, attr, val)
                        if isinstance(val, _accepted_types):
                            dobj[get_dest_attr(cls, attr)] = sanitize_value(val)
                        else:
                            raise RuntimeError(
                                "I'm not sure I could handle this type of value "
                                "and I'm in devel/beta mode,\n"
                                "so for now I prefer to prematurely exit.\n"
                                "type=%s, attr=%s, val=%s ; object=%s" %
                                (type(val), attr, val, obj)
                            )
                # end for attr in ..

                # I want to be sure each object has a "unique" "key" value
                if isinstance(obj, Service):
                    # actually this is the only (shinken-)object type
                    # that have a 2 components "unique key" :
                    key = {k: dobj[k]
                           for k in ('host_name', 'service_description')}
                else:
                    # each other type MUST have a get_name() which should
                    # return the unique name value for this object.
                    key_name = '%s_name' % infos.singular
                    key_value = obj.get_name()
                    key = {key_name: key_value}
                    prev = dobj.setdefault(key_name, key_value)
                    if prev != key_value:
                        raise RuntimeError(
                            "damn: I wanted to be sure that object %s:%s had the "
                            "%s attribute, but its previous value is not what "
                            "I was expecting, got %s expected %s" %
                            (cls, obj.get_name(), attr, prev, key_value))

                try:
                    bulkop.find(key).upsert().replace_one(dobj)
                except Exception as err:
                    raise RuntimeError("Error on insert/update of %s-%s : %s" %
                                       (cls, obj.get_name(), err))

            # end for obj in objects..

            if objects:
                # mongo requires at least one document for a bulkop.execute()
                try:
                    bulkop.execute()
                except Exception as err:
                    raise RuntimeError("Error on bulk execute for collection "
                                       "%s : %s" % (infos.plural, err))
        # end for cls, infos in _types_infos.items()

        # special case for the global configuration values :
        collection = db[GLOBAL_CONFIG_COLLECTION_NAME]
        dglobal = {}
        macros = {}  # special case for shinken macros ($XXX$)
        for attr in _types_infos[Config].accepted_properties:
            def_val_args = get_default_attr_value_args(attr, Config)
            try:
                value = getattr(arbiter.conf, attr, *def_val_args)
            except AttributeError:
                continue
            if not isinstance(value, _accepted_types):
                continue
            value = sanitize_value(value)
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

    def hook_pre_scheduler_mod_start(self, scheduler):
        if self._hooked:
            return

        self._my_conn = self._connect_db()
        self._my_db = self._my_conn[self._db_name]
        self._hooked = True

        # had to declare hooked_setattr "encapsulated" here
        # so to have access to 'self' (where we store the _objects_updated).
        def hooked_setattr(obj, attr, value):
            # filter on obj + attr ..
            # print("->", type(obj), attr, value)
            cls = obj.__class__
            type_infos = _types_infos[cls]

            if attr in type_infos.accepted_properties:
                if value != getattr(obj, attr, _not_exist):
                    # only retain, for update, the new value if it's different
                    # than the previous one actually..
                    # with self._lock:
                    # TODO / TOCHECK: should we use the lock ??
                    self._objects_updated[cls][obj][attr] = value
            super(Item, obj).__setattr__(attr, value)

        Item.__setattr__ = hooked_setattr

    def hook_scheduler_tick(self, daemon):

        n_updated = 0
        tot_attr_updated = 0

        objs_updated, self._objects_updated = (
            self._objects_updated, self._make_objects_updates())

        time.sleep(0.05)

        t0 = time.time()

        for cls, objects in objs_updated.iteritems():
            infos = _types_infos[cls]
            collection = self._my_db[infos.plural]
            bulkop = collection.initialize_unordered_bulk_op()
            for obj, dct in objects.iteritems():
                dest = {}
                dobj = {'$set': dest}

                if isinstance(obj, Service):
                    key = {k: getattr(obj, k)
                           for k in ('host_name', 'service_description')}
                else:
                    key = {'%s_name' % infos.singular: obj.get_name()}

                for attr, value in dct.iteritems():
                    value = get_value_by_type_name_val(cls, attr, value)
                    destattr = get_dest_attr(cls, attr)
                    dest[destattr] = sanitize_value(value)

                tot_attr_updated += len(dest)

                try:
                    # print("%s -> %s" % (key, dest))
                    bulkop.find(key).update_one(dobj)
                except Exception as err:
                    raise RuntimeError("Error on insert/update of %s : %s" %
                                       (obj.get_name(), err))
                n_updated += 1
            # end for obj, lst in objects.items()

            if objects:
                # mongo requires at least one document for a bulkop.execute()
                try:
                    bulkop.execute()
                except Exception as err:
                    raise RuntimeError("Error on bulk execute for collection "
                                       "%s : %s" % (infos.plural, err))

        if n_updated:
            logger.info("updated %s objects with %s attributes in mongo in %s secs ..",
                        n_updated, tot_attr_updated, time.time() - t0)

        for cls in self._objects_updated:
            self._objects_updated[cls].clear()
