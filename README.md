mod-mongo-live-config [![Build Status](https://travis-ci.org/savoirfairelinux/mod-arbiter-dumpconfig.svg?branch=master)](https://travis-ci.org/savoirfairelinux/mod-arbiter-dumpconfig) [![Coverage Status](https://img.shields.io/coveralls/savoirfairelinux/mod-arbiter-dumpconfig.svg)](https://coveralls.io/r/savoirfairelinux/mod-arbiter-dumpconfig?branch=master)
=====================

Shinken module for keeping, nearly in realtime, the Shinken objects properties/attributes values in a mongodb,
as well as the global configuration properties/attributes values.

The module requires the following:
- pymongo >= 2.6.3
- Shinken >= 2.4

NB:
===

This module is still under devel/beta mode ..


Configuration:
==============
```
define module {
 
    module_name your_module_name
    module_type mongo_live_config
    
    # optional directives:
    
    # host : the hostname of where is running the mongodb
    #        default: 127.0.0.1
    
    # port : the port to connect to the mongodb
    #        default: 27017
    
    # db : the name of the mongo db to use
    #      default: shinken_live
}
```
