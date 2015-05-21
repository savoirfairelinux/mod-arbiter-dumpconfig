#!/usr/bin/env python
# -*- coding: utf-8 -*-

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

# Copyright (C) 2015, Savoir-faire Linux, Inc.
#
# Authors:
#   Grégory Starck <gregory.starck@savoirfairelinux.com>
#
#############################################################################

from __future__ import with_statement

import os.path as p
import sys
from setuptools import setup, find_packages

description = "A Shinken 'module' to mirror, nearly in realtime, the Shinken ' \
              'objects attributes in a mongo db"

# README
with open('README.md') as f:
    readme = f.read()

# LICENSE
with open('LICENSE') as f:
    license = f.read()

# For tests requirements:
if sys.version_info[:2] < (3, 0):
    unittest_pkg = "unittest2"
else:
    unittest_pkg = "unittest"

# VERSION
with open(p.join('mod_mongo_live_config', 'version.py')) as f:
    exec(f.read())
try:
    VERSION
except NameError:
    # so to have a default version if version.py
    # would be empty or not declare a VERSION.
    VERSION = "0.0.0"


setup(
    name='mod_mongo_live_config',
    version=VERSION,
    description=description,
    long_description=readme,
    author='Grégory Starck',
    author_email='gregory.starck@savoirfairelinux.com',
    url='https://github.com/savoirfairelinux/mod-mongo-live-config',
    license=license,
    packages=find_packages(exclude=('tests', 'docs')),
    install_requires=[
        "pymongo==3.0",
    ],
    extras_require={
        'test': [
            unittest_pkg,
            'nose==1.3',
            'coverage==3.7',
        ],
    },
)
