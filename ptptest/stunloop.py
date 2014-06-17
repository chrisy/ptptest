# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4
# 
# Copyright (c) 2014 Chris Luke <chrisy@flirble.org>
"""STUN support"""

import os, sys, eventlet

sys.path.insert(0, os.path.dirname(__file__)+'/../pystun')
import stun

class Stun(object):
	ui = None

	def __init__(self, ui=None):
		super(Stun, self).__init__()
		self.ui = ui

	def set_ui(self, ui):
		self.ui = ui

 	def run(self):
		while True:
			nat_type = 'Unknown'
			external_ip = 'Unknown'
			external_port = None
			fail = False

			if self.ui:
				self.ui.log("Running STUN probe")
			try:
				nat_type, external_ip, external_port = stun.get_ip_info()
			except:
				fail = True

			if self.ui:
				if fail:
					self.ui.log("STUN failed")
				else:
					self.ui.log("STUN completed")
				self.ui.set_stun(nat_type, external_ip, external_port)

			eventlet.sleep(300)
