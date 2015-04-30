

from .dumpconfig import DumpConfig


properties = {
    'daemons': ['arbiter'],
    'phases': ['running'],
    'type': 'mongo_dumpconfig',
    'external': False,
}


def get_instance(plugin):
    instance = DumpConfig(plugin)
    return instance
