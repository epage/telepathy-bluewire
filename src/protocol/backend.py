#!/usr/bin/python

"""
Resources:
http://code.google.com/p/pybluez/
http://lightblue.sourceforge.net/
http://code.google.com/p/python-bluetooth-scanner
"""

from __future__ import with_statement

import logging

import bluetooth
import gobject


_moduleLogger = logging.getLogger(__name__)


# The L2CAP spec (page. 278) say "PSM values are separated into two ranges.
# Values in the first range are assigned by the Bluetooth SIG and indicate
# protocols. The second range of values [0x1001 - 0xffff] are dynamically
# allocated and used in conjunction with the Service Discovery Protocol (SDP).
# The dynamically assigned values may be used to support multiple
# implementations of a particular protocol, e.g., RFCOMM, residing on top of
# L2CAP or for prototyping an experimental protocol."
CHAT_PROTOCOL = 0x1001


class BluetoothConnection(gobject.GObject):

	__gsignals__ = {
		'data_ready' : (
			gobject.SIGNAL_RUN_LAST,
			gobject.TYPE_NONE,
			(),
		),
		'closed' : (
			gobject.SIGNAL_RUN_LAST,
			gobject.TYPE_NONE,
			(),
		),
	}

	def __init__(self, socket, addr, psm):
		gobject.GObject.__init__(self)
		self._socket = socket
		self._address = addr
		self._dataId = gobject.io_add_watch (self._socket, gobject.IO_IN, self._on_data)
		self._psm = psm

	def close(self):
		gobject.source_remove(self._dataId)
		self._dataId = None

		self._socket.close()
		self._socket = None
		self.emit("closed")

	@property
	def socket(self):
		return self._socket

	@property
	def protocol(self):
		return self._psm

	@property
	def address(self):
		return self._address

	def _on_data(self, source, condition):
		self.emit("data_ready")


gobject.type_register(BluetoothConnection)


class BluetoothListener(gobject.GObject):

	__gsignals__ = {
		'incoming' : (
			gobject.SIGNAL_RUN_LAST,
			gobject.TYPE_NONE,
			(gobject.TYPE_PYOBJECT, ),
		),
		'closed' : (
			gobject.SIGNAL_RUN_LAST,
			gobject.TYPE_NONE,
			(),
		),
	}

	def __init__(self, psm, timeout):
		gobject.GObject.__init__(self)
		self._timeout = timeout
		self._psm = psm

		self._socket = bluetooth.BluetoothSocket(bluetooth.L2CAP)
		self._socket.settimeout(self._timeout)
		self._socket.bind(("",self._psm))
		self._socket.listen(1)
		self._incomingId = gobject.io_add_watch(
			self._socket, gobject.IO_IN, self._on_incoming
		)

	def close(self):
		gobject.source_remove(self._incomingId)
		self._incomingId = None

		self._socket.close()
		self._socket = None
		self.emit("closed")

	@property
	def socket(self):
		return self._socket

	def _on_incoming(self, source, condition):
		newSocket, (address, psm) = self._socket.accept()
		newSocket.settimeout(self._timeout)
		connection = BluetoothConnection(newSocket, address, self._psm)
		self.emit("incoming", connection)


gobject.type_register(BluetoothListener)


class BluetoothBackend(gobject.GObject):

	__gsignals__ = {
		'login' : (
			gobject.SIGNAL_RUN_LAST,
			gobject.TYPE_NONE,
			(),
		),
		'logout' : (
			gobject.SIGNAL_RUN_LAST,
			gobject.TYPE_NONE,
			(),
		),
		'incoming' : (
			gobject.SIGNAL_RUN_LAST,
			gobject.TYPE_NONE,
			(gobject.TYPE_PYOBJECT, ),
		),
	}

	def __init__(self):
		gobject.GObject.__init__(self)
		self._timeout = 10
		self._listeners = {}
		self._listenerIds = {}

	def login(self):
		self._listeners[CHAT_PROTOCOL] = BluetoothListener(CHAT_PROTOCOL, self._timeout)
		self._listenerIds[CHAT_PROTOCOL] = self._listeners[CHAT_PROTOCOL].connect(
			"incoming", self._on_incoming
		)
		self.emit("login")

	def logout(self):
		for protocol in self._listeners.iterkeys():
			listener = self._listeners[protocol]
			listenerId = self._listenerIds[protocol]

			listener.disconnect(listenerId)
			listener.close()
		self._listeners.clear()
		self._listenerIds.clear()
		self.emit("logout")

	def is_logged_in(self):
		if self._listeners:
			return True
		else:
			return False

	def get_contacts(self):
		return bluetooth.discover_devices(
			duration=self._timeout,
			flush_cache = True,
			lookup_names = True
		)

	def get_contact_details(self, address):
		# @todo Use finservices to return what the other side is capable of
		return {}

	def connect(self, addr, protocol):
		sock = bluetooth.BluetoothSocket(bluetooth.L2CAP)
		sock.settimeout(self._timeout)
		try:
			sock.connect((addr, protocol))
		except bluetooth.error, e:
			sock.close()
			raise

		return BluetoothConnection(sock, addr, protocol)

	def _on_incoming(self, connection):
		self.emit("incoming", connection)


gobject.type_register(BluetoothBackend)
