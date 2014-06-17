# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4
# 
# Copyright (c) 2014 Chris Luke <chrisy@flirble.org>
# 
"""BSON monkey patches"""

import os, sys

sys.path.insert(0, os.path.dirname(__file__)+'/')
sys.path.insert(0, os.path.dirname(__file__)+'/../bson')
import bson
