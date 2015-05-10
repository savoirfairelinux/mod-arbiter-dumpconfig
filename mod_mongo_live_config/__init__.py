

from .live_config import LiveConfig
from .version import VERSION

properties = {
    'daemons': ['arbiter', 'scheduler'],
    'phases': ['running'],
    'type': 'mongo_live_config',
    'external': False,
}


def get_instance(plugin):
    instance = LiveConfig(plugin)
    return instance
