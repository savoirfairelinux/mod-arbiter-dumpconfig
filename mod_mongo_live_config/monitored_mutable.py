

def retain_actions(actions):
    """decorator to be used on a subclass of Monitored_Mutable.
    :param actions: is the list(or tuple) of function names that must be
    intercepted in order to mark the object on which it is applied
    as having been modified.
    """
    def wraps(cls):
        base_type = cls.get_base_type()
        for action in actions:
            base_type_func = getattr(base_type, action)

            def wrapped(base_type_func=base_type_func):
                def newaction(self, *a, **kw):
                    res = base_type_func(self, *a, **kw)
                    self.retain()
                    return res
                return newaction
            setattr(cls, action, wrapped())
        return cls
    return wraps


class Monitored_Mutable(object):

    def __new__(cls, *args, **kwargs):
        monitor = kwargs.pop('monitor')
        # assert isinstance(monitor, LiveConfig)
        object = kwargs.pop('object')
        attr = kwargs.pop('attr')
        self = super(Monitored_Mutable, cls).__new__(cls, *args, **kwargs)
        self._monitor = monitor
        self._object = object
        self._attr = attr
        return self

    def __init__(self, *args, **kw):
        kw.pop('monitor')
        kw.pop('object')
        kw.pop('attr')
        super(Monitored_Mutable, self).__init__(*args, **kw)

    def retain(self):
        self._monitor.retain(type(self._object), self._object, self._attr, self)

    @classmethod
    def get_base_type(cls):
        mro = cls.mro()
        base_idx = 1 + mro.index(Monitored_Mutable)
        return mro[base_idx]

    # we want still to be picklable,
    # but as if we were the original value:
    def __reduce__(self):
        return (
            self.get_base_type(),
            tuple((tuple(self),))
        )


#############################################################################

@retain_actions(('insert', 'append', 'extend', 'pop',
                 '__delitem__', '__setitem__', '__delslice__'))
class Monitored_List(Monitored_Mutable, list):
    pass

#############################################################################


@retain_actions(('add', 'remove', 'pop', 'clear'))
class Monitored_Set(Monitored_Mutable, set):

    def discard(self, obj):
        # don't bother retaining the change if nothing would be changed:
        if obj in self:
            self.retain()
            super(Monitored_Set, self).discard(obj)

#############################################################################


def get_monitor_type_for(value):
    if isinstance(value, list):
        return Monitored_List
    elif isinstance(value, set):
        return Monitored_Set
