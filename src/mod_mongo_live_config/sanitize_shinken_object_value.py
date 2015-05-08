

from shinken.commandcall import CommandCall
from shinken.objects.item import Item
from shinken.property import none_object


_shinken_objects_types = (
    # theses types should have a get_name() method.
    # returning the actual "name" of the object.
    # which MUST be unique for every objects of the same type.
    Item,
    CommandCall,
)


_sanitizer_handlers = {
    # define type -> transformation
    # if a value has a type here then it'll be transformed according
    # to the given lambda/function.

    # the hosts & services have attached in their 'command' attribute
    # a CommandCall instance
    # for that kind of object we only want the actually linked command_name:
    CommandCall: lambda v: v.command.command_name,

    # sets and frozensets don't have an equivalent in mongo,
    # we'll translate them into tuples.
    set:            tuple,
    frozenset:      tuple,
}


def sanitize_value(value):
    """ Sanitize a value
    :param value:
    :return:
    """
    if value is none_object:  # special case
        return None

    value = _sanitizer_handlers.get(type(value), lambda v: v)(value)

    if isinstance(value, _shinken_objects_types):
        return value.get_name()

    # for tuple or list values,
    # we need to recursively sanitize their value :
    if isinstance(value, (tuple, list)):
        return type(value)(sanitize_value(subval)
                           for subval in value)

    return value
