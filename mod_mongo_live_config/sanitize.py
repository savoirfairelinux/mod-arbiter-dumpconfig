
import datetime

from shinken.objects.config import Config
from shinken.objects.item import Item
from shinken.commandcall import CommandCall
from shinken.objects.host import Host
from shinken.objects.realm import Realm
from shinken.objects.timeperiod import Timeperiod
from shinken.objects import Service
from shinken.property import none_object

#############################################################################

from .default import GLOBAL_CONFIG_COLLECTION_NAME

#############################################################################

accepted_types = (
    # for each shinken object, we'll look at each of its attribute defined
    # in its class 'properties' and 'running_properties' dicts (+ few others
    # hardcoded one because we miss them in pre-mentioned dicts unfortun.. )

    # If the object attribute value isn't one of 'accepted_types'
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
    'checks_in_progress',
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

types_infos = _build_types_infos()
del _build_types_infos

#############################################################################
if False:
    # unused feature for now.. but could be used..

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

def get_def_attr_value(attr, cls):
    """ Return, in a single-element tuple, the default value to be used for an
        attribute named 'attr' and belonging to the class 'cls'.
        If no such default value exists, returns the empty tuple.
        So that the returned value can directly be used like this:
        >>> obj = Service()
        >>> attr = 'foo'
        >>> val = getattr(obj, attr,
        ...               *get_def_attr_value(attr, Service))
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

_shinken_objects_types = (
    # theses classes (or subclass of) should have a get_name() method.
    # returning the actual "name" of the object.
    # which MUST be unique for every objects of the same type.
    # NB: Service is the exception to this rule..
    Item,
    CommandCall,
)


def CommandCallHandler(v):
    return v.call

_sanitizer_handlers = {
    # define type -> transformation
    # if a value has a type here then it'll be transformed according
    # to the given lambda/function.

    # the hosts & services have attached in their 'command' attribute
    # a CommandCall instance
    # for that kind of object we only want the actually linked command_name:
    CommandCall: CommandCallHandler,

    # sets and frozensets don't have an equivalent in mongo,
    # we'll translate them into tuples.
    set:            tuple,
    frozenset:      tuple,
}


def _sanitize_value(value):
    """ Sanitize a value
    :param value:
    :return:
    """
    if value is none_object:  # special case
        return None

    handler = _sanitizer_handlers.get(type(value), lambda v: v)
    value = handler(value)

    if isinstance(value, _shinken_objects_types):
        return value.get_name()

    # for tuple or list values,
    # we need to recursively sanitize their value :
    if isinstance(value, (tuple, list)):
        return type(value)(_sanitize_value(subval)
                           for subval in value)

    return value


def sanitize_value(cls, obj, attr, value):
    value = get_value_by_type_name_val(cls, attr, value)
    return _sanitize_value(value)
