mod-mongo-live-config [![Build Status](https://travis-ci.org/savoirfairelinux/mod-mongo-live-config.svg?branch=master)](https://travis-ci.org/savoirfairelinux/mod-mongo-live-config) [![Coverage Status](https://coveralls.io/repos/savoirfairelinux/mod-mongo-live-config/badge.svg)](https://coveralls.io/r/savoirfairelinux/mod-mongo-live-config)
=====================

[Alignak](https://github.com/Alignak-monitoring/alignak) module for keeping, nearly in realtime, the (Alignak) objects properties/attributes values in a mongodb,
as well as the global configuration properties/attributes values.

The module requires the following:
- pymongo >= 3.0
- Alignak >= 0.0

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
    
    # hostname : the hostname of where is running the mongodb
    #            default: 127.0.0.1
    
    # port : the port to connect to the mongodb
    #        default: 27017
    
    # db : the name of the mongo db to use
    #      default: alignak_live
}
```
