
from .version import VERSION as __version__

properties = {
    'daemons': ['arbiter', 'scheduler'],
    'phases': ['running'],
    'type': 'mongo_live_config',
    'external': False,
}


def get_instance(plugin):
    from .live_config import LiveConfig
    instance = LiveConfig(plugin)
    return instance
