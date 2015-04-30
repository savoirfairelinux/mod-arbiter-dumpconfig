
from __future__ import print_function, with_statement, unicode_literals

#############################################################################

import datetime
import sys
import time
from itertools import chain

#############################################################################

import pymongo

#############################################################################

from shinken.basemodule import BaseModule
from shinken.commandcall import CommandCall
from shinken.objects.config import Config
from shinken.objects import Service
from shinken.log import logger
from shinken.objects.item import Item, Items
from shinken.property import none_object

#############################################################################

from .sanitize_shinken_object_value import sanitize_value

#############################################################################

# various data handlers and settings to configure how the serialization
# from shinken objects to "json-like" objects will be done.

_TypesInfos = Config.types_creations.copy()


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


_skip_attributes = (
    # these attributes will be globally skipped whatever are the values, if any
    'hash',
    'configuration_errors',
    'configuration_warnings',
)


_by_type_name_skip = dict(
    # for each shinken object type **name**,
    # define the list/tuple of attributes to be also skipped.

    # timeperiod objects have a dateranges attribute,
    # but it's quite a complex object type and I'm not sure it's actually
    # needed within the mongo :
    timeperiod=('dateranges',),
    realm=('serialized_confs',)
)


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


_default_attribute_value = {
    # if an attribute is missing on an object
    # then it'll get a default value from here
    'use':      [],
}

_by_type_default_attribute_value = {
    # same, but with per type:
    # example:
    # Service: {
    #   'attr_foo': default_value_for_attr_foo_on_Service_object,
    #   ..
    # }
}


_by_name_converter = {
    # for some attributes, I want to eventually adapt their value based on it:

    'use':  lambda v: v if v else []  # so to be sure to not get None/0/..
                                      # for this attribute BUT []

}

_by_type_name_converter = {
    # example:
    # Service: {
    #      'some_attr_name':   lambda value: str(value)  # say
    # }
}


class DumpConfig(BaseModule):

    def __init__(self, mod_conf):
        super(DumpConfig, self).__init__(mod_conf)
        # TODO: get that from mod_conf :
        self._host = 'localhost'
        self._port = 27017
        self._db = 'shinken'

    def _connect_db(self):
        return pymongo.MongoClient(self._host, self._port)

    def hook_late_configuration(self, arbiter):
        pass
        # TODO : Not yet sure what's the best moment to do the job..
        # hook_late_configuration takes place BEFORE some late cleaning has
        # been applied to the services already.
        # While load_retention seems, for now, a better place.
        # So, for now, choosing hook_load_retention().

    def hook_load_retention(self, arbiter):
        t0 = time.time()
        self.do_insert(arbiter)
        t1 = time.time()
        logger.info("Mongo insert took %s", (t1 - t0))

    def do_insert(self, arbiter):
        logger.info("Dumping config to mongo ..")

        try:
            self._do_insert(arbiter)
        except Exception as err:
            logger.exception("I got a fatal error: %s", err)
            sys.exit("I'm in devel/beta mode and I prefer to exit for now,"
                     "please open a ticket with this exception details :)")

    def _do_insert(self, arbiter):
        """Do that actual insert(or update) job.
        :param arbiter: The arbiter object.
        :return:
        """
        conn = self._connect_db()
        db = conn[self._db]
        for singular_name, infos in _TypesInfos.items():
            cls, clss, plural_name, _ = infos
            collection = db[plural_name]
            objects = getattr(arbiter.conf, plural_name)
            for obj in objects:
                dobj = {}
                for attr in chain(cls.properties,
                                  cls.running_properties,
                                  ('use',
                                   '_self_declared_properties',)):
                    if attr in _skip_attributes:
                        continue
                    if attr in _by_type_name_skip.get(singular_name, ()):
                        continue

                    # would we use a default value for this attribute
                    # if the object wouldn't have it ?
                    if attr in _default_attribute_value:
                        def_val_args = (_default_attribute_value[attr],)
                    elif (cls in _by_type_default_attribute_value
                            and attr in _by_type_default_attribute_value[cls]):
                        def_val_args = (_by_type_default_attribute_value[cls][attr],)
                    else:
                        def_val_args = ()

                    try:
                        val = getattr(obj, attr, *def_val_args)
                    except AttributeError:
                        pass
                    else:
                        if val is none_object:
                            # special case for this unfortunately..
                            val = None

                        val = _by_name_converter.get(attr, lambda v: v)(val)
                        if isinstance(val, _accepted_types):
                            val = sanitize_value(val)
                            attr = _rename_prop.get(attr, attr)
                            dobj[attr] = val
                        else:
                            raise RuntimeError(
                                "I'm not sure I could handle this type of value, "
                                "so for now I prefer to prematurely exit.\n"
                                "type=%s, attr=%s, val=%s ; object=%s" %
                                (type(val), attr, val, obj)
                            )
                # end for attr in ..

                # I want to be sure each object has a "unique" key value
                if isinstance(obj, Service):
                    # actually this is the only (shinken-)object type
                    # that have a 2 component unique key
                    key = {k: dobj[k]
                           for k in ('host_name', 'service_description')}
                else:
                    # each other type MUST have a get_name() which should
                    # return the unique name value for this object.
                    key_name = '%s_name' % singular_name
                    key_value = obj.get_name()
                    key = {key_name: key_value}
                    prev = dobj.setdefault(key_name, key_value)
                    if prev != key_value:
                        raise RuntimeError(
                            "damn: I wanted to be sure that object %s had the "
                            "%s attribute, but its previous value is not what "
                            "I was expecting, got %s expected %s" %
                            (object, prev, key_value))
                    dobj[key_name] = key_value

                try:
                    collection.update(key, dobj, True)
                except Exception as err:
                    raise RuntimeError("Error on insert/update of %s : %s" %
                                       (obj, err))

        collection = db['global_configuration']
        dglobal = {}
        resources = {}
        # special case for the global configuration values :
        for attr, value in vars(arbiter.conf).iteritems():
            if not isinstance(value, _accepted_types):
                continue
            if attr in ('confs', 'whole_conf_pack'):
                continue
            value = sanitize_value(value)
            if attr.startswith('$') and attr.endswith('$'):
                resources[attr[1:-1]] = value
            else:
                dglobal[attr] = value

        if 'resources' in dglobal:
            raise RuntimeError(
                "Daaamn, there was already a 'resource' attribute in the global"
                "configuration .. But I wanted to used to store the different "
                " \"resources macros\" ($USERXX$)\n"
                "Houston, we have a problem..")
        dglobal['resources'] = resources

        collection.drop()
        collection.insert(dglobal)
