#!/usr/bin/python

"""
Resources:
http://code.google.com/p/pybluez/
http://lightblue.sourceforge.net/
http://code.google.com/p/python-bluetooth-scanner
"""

from __future__ import with_statement

import select
import logging

import bluetooth
import gobject

import util.misc as misc_utils


_moduleLogger = logging.getLogger(__name__)


class _BluetoothConnection(gobject.GObject):

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

	def __init__(self, socket, addr, protocol):
		gobject.GObject.__init__(self)
		self._socket = socket
		self._address = addr
		self._dataId = gobject.io_add_watch (self._socket, gobject.IO_IN, self._on_data)
		self._protocol = protocol

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
	def address(self):
		return self._address

	@property
	def protocol(self):
		return self._protocol

	@misc_utils.log_exception(_moduleLogger)
	def _on_data(self, source, condition):
		self.emit("data_ready")
		return True


gobject.type_register(_BluetoothConnection)


class _BluetoothListener(gobject.GObject):

	__gsignals__ = {
		'incoming_connection' : (
			gobject.SIGNAL_RUN_LAST,
			gobject.TYPE_NONE,
			(gobject.TYPE_PYOBJECT, ),
		),
		'start_listening' : (
			gobject.SIGNAL_RUN_LAST,
			gobject.TYPE_NONE,
			(),
		),
		'stop_listening' : (
			gobject.SIGNAL_RUN_LAST,
			gobject.TYPE_NONE,
			(),
		),
	}

	def __init__(self, protocol, timeout):
		gobject.GObject.__init__(self)
		self._timeout = timeout
		self._protocol = protocol
		self._socket = None
		self._incomingId = None

	def start(self):
		assert self._socket is None and self._incomingId is None
		self._socket = bluetooth.BluetoothSocket(self._protocol["transport"])
		self._socket.settimeout(self._timeout)
		self._socket.bind(("", bluetooth.PORT_ANY))
		self._socket.listen(1)
		self._incomingId = gobject.io_add_watch(
			self._socket, gobject.IO_IN, self._on_incoming
		)

		bluetooth.advertise_service(self._socket, self._protocol["name"], self._protocol["uuid"])
		self.emit("start_listening")

	def stop(self):
		if self._socket is None or self._incomingId is None:
			return
		gobject.source_remove(self._incomingId)
		self._incomingId = None

		bluetooth.stop_advertising(self._socket)
		self._socket.close()
		self._socket = None
		self.emit("stop_listening")

	@property
	def isListening(self):
		return self._socket is not None and self._incomingId is not None

	@property
	def socket(self):
		assert self._socket is not None
		return self._socket

	@misc_utils.log_exception(_moduleLogger)
	def _on_incoming(self, source, condition):
		newSocket, (address, port) = self._socket.accept()
		newSocket.settimeout(self._timeout)
		connection = _BluetoothConnection(newSocket, address, self._protocol)
		self.emit("incoming_connection", connection)
		return True


gobject.type_register(_BluetoothListener)


class _DeviceDiscoverer(bluetooth.DeviceDiscoverer):

	def __init__(self, timeout):
		bluetooth.DeviceDiscoverer.__init__(self)
		self._timeout = timeout

		self._devices = []
		self._devicesInProgress = []

	@property
	def devices(self):
		return self._devices

	def find_devices(self, *args, **kwds):
		# Ensure we always start clean and is the reason we overroad this
		self._devicesInProgress = []

		newArgs = [self]
		newArgs.extend(args)
		bluetooth.DeviceDiscoverer.find_devices(*newArgs, **kwds)

	def process_inquiry(self):
		# The default impl calls into some hci code but an example used select,
		# so going with the example

		while self.is_inquiring or 0 < len(self.names_to_find):
			# The whole reason for overriding this
			_moduleLogger.debug("Event (%r, %r)"% (self.is_inquiring, self.names_to_find))
			rfds = select.select([self], [], [], self._timeout)[0]
			if self in rfds:
				self.process_event()

	@misc_utils.log_exception(_moduleLogger)
	def device_discovered(self, address, deviceclass, name):
		device = address, deviceclass, name
		_moduleLogger.debug("Device Discovered %r" % (device, ))
		self._devicesInProgress.append(device)

	@misc_utils.log_exception(_moduleLogger)
	def inquiry_complete(self):
		_moduleLogger.debug("Inquiry Complete")
		self._devices = self._devicesInProgress


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
		'contacts_update' : (
			gobject.SIGNAL_RUN_LAST,
			gobject.TYPE_NONE,
			(gobject.TYPE_PYOBJECT, ),
		),
	}

	def __init__(self):
		gobject.GObject.__init__(self)
		self._disco = None
		self._timeout = 8
		self._listeners = {}
		self._protocols = []
		self._isListening = True

	def add_protocol(self, protocol):
		assert not self.is_logged_in()
		self._protocols.append(protocol)

	def login(self):
		self._disco = _DeviceDiscoverer(self._timeout)

		isListening = self._isListening
		for protocol in self._protocols:
			protoId = protocol["uuid"]
			self._listeners[protoId] = _BluetoothListener(protocol, self._timeout)
			if isListening:
				self._listeners[protoId].start()

		self.emit("login")

	def logout(self):
		for protocol in self._protocols:
			protoId = protocol["uuid"]
			listener = self._listeners[protoId]
			listenerId = self._listenerIds[protoId]

			listener.disconnect(listenerId)
			listener.close()
		self._listeners.clear()
		self._listenerIds.clear()
		self._disco.cancel_inquiry() # precaution
		self.emit("logout")

	def is_logged_in(self):
		if self._listeners:
			return True
		else:
			return False

	def is_listening(self):
		return self._isListening

	def enable_listening(self, enable):
		if enable:
			for listener in self._listeners.itervalues():
				assert not listener.isListening
			for listener in self._listeners.itervalues():
				listener.start()
		else:
			for listener in self._listeners.itervalues():
				assert listener.isListening
			for listener in self._listeners.itervalues():
				listener.stop()

	def get_contacts(self):
		try:
			self._disco.find_devices(
				duration=self._timeout,
				flush_cache = True,
				lookup_names = True,
			)
			self._disco.process_inquiry()
		except bluetooth.BluetoothError, e:
			# lightblue does this, so I guess I will too
			_moduleLogger.error("Error while getting contacts, attempting to cancel")
			try:
				self._disco.cancel_inquiry()
			finally:
				raise e

		return self._disco.devices

	def get_contact_services(self, address):
		services = bluetooth.find_service(address = address)
		return services

	def connect(self, addr, transport, port):
		sock = bluetooth.BluetoothSocket(transport)
		sock.settimeout(self._timeout)
		try:
			sock.connect((addr, port))
		except bluetooth.error, e:
			sock.close()
			raise

		return _BluetoothConnection(sock, addr, "")


gobject.type_register(BluetoothBackend)


class BluetoothClass(object):

	def __init__(self, description):
		self.description = description

	def __str__(self):
		return self.description


MAJOR_CLASS = BluetoothClass("Major Class")
MAJOR_CLASS.MISCELLANEOUS = BluetoothClass("Miscellaneous")
MAJOR_CLASS.COMPUTER = BluetoothClass("Computer")
MAJOR_CLASS.PHONE = BluetoothClass("Phone")
MAJOR_CLASS.LAN = BluetoothClass("LAN/Network Access Point")
MAJOR_CLASS.AV = BluetoothClass("Audio/Video")
MAJOR_CLASS.PERIPHERAL = BluetoothClass("Peripheral")
MAJOR_CLASS.IMAGING = BluetoothClass("Imaging")
MAJOR_CLASS.UNCATEGORIZED = BluetoothClass("Uncategorized")

MAJOR_CLASS.MISCELLANEOUS.RESERVED = BluetoothClass("Reserved")

MAJOR_CLASS.COMPUTER.UNCATEGORIZED = BluetoothClass("Uncategorized, code for device not assigned")
MAJOR_CLASS.COMPUTER.DESKTOP = BluetoothClass("Desktop workstation")
MAJOR_CLASS.COMPUTER.SERVER = BluetoothClass("Server-class computer")
MAJOR_CLASS.COMPUTER.LAPTOP = BluetoothClass("Laptop")
MAJOR_CLASS.COMPUTER.HANDHELD = BluetoothClass("Handheld PC/PDA (clam shell)")
MAJOR_CLASS.COMPUTER.PALM_SIZE = BluetoothClass("Palm sized PC/PDA")
MAJOR_CLASS.COMPUTER.WEARABLE = BluetoothClass("Wearable computer (Watch sized)")
MAJOR_CLASS.COMPUTER.RESERVED = BluetoothClass("Reserved")

MAJOR_CLASS.PHONE.UNCATEGORIZED = BluetoothClass("Uncategorized, code for device not assigned")
MAJOR_CLASS.PHONE.CELLULAR = BluetoothClass("Cellular")
MAJOR_CLASS.PHONE.CORDLESS = BluetoothClass("Cordless")
MAJOR_CLASS.PHONE.SMART_PHONE = BluetoothClass("Smart phone")
MAJOR_CLASS.PHONE.MODEM = BluetoothClass("Wired modem or voice gateway")
MAJOR_CLASS.PHONE.ISDN = BluetoothClass("Common ISDN Access")
MAJOR_CLASS.PHONE.RESERVED = BluetoothClass("Reserved")

MAJOR_CLASS.LAN.UNCATEGORIZED = BluetoothClass("Uncategorized")
MAJOR_CLASS.LAN.RESERVED = BluetoothClass("Reserved")

MAJOR_CLASS.AV.UNCATEGORIZED = BluetoothClass("Uncategorized, code for device not assigned")
MAJOR_CLASS.AV.HEADSET = BluetoothClass("Device conforms to headset profile")
MAJOR_CLASS.AV.HANDS_FREE = BluetoothClass("Hands-free")
MAJOR_CLASS.AV.MICROPHONE = BluetoothClass("Microphone")
MAJOR_CLASS.AV.LOUDSPEAKER = BluetoothClass("Loudspeaker")
MAJOR_CLASS.AV.HEADPHONES = BluetoothClass("Headphones")
MAJOR_CLASS.AV.PORTABLE_AUDIO = BluetoothClass("Portable Audio")
MAJOR_CLASS.AV.CAR_AUDIO = BluetoothClass("Car Audio")
MAJOR_CLASS.AV.SET_TOP_BOX = BluetoothClass("Set-top box")
MAJOR_CLASS.AV.HIFI_AUDIO_DEVICE = BluetoothClass("HiFi Audio Device")
MAJOR_CLASS.AV.VCR = BluetoothClass("VCR")
MAJOR_CLASS.AV.VIDEO_CAMERA = BluetoothClass("Video Camera")
MAJOR_CLASS.AV.CAMCORDER = BluetoothClass("Camcorder")
MAJOR_CLASS.AV.VIDEO_MONITOR = BluetoothClass("Video Monitor")
MAJOR_CLASS.AV.VIDEO_DISPLAY = BluetoothClass("Video Display and Loudspeaker")
MAJOR_CLASS.AV.VIDEO_CONFERENCING = BluetoothClass("Video Conferencing")
MAJOR_CLASS.AV.GAMING = BluetoothClass("Gaming/Toy")
MAJOR_CLASS.AV.RESERVED = BluetoothClass("Reserved")

MAJOR_CLASS.PERIPHERAL.UNCATEGORIZED = BluetoothClass("Uncategorized, code for device not assigned")
MAJOR_CLASS.PERIPHERAL.JOYSTICK = BluetoothClass("Joystick")
MAJOR_CLASS.PERIPHERAL.GAMEPAD = BluetoothClass("Gamepad")
MAJOR_CLASS.PERIPHERAL.REMOTE_CONTROL = BluetoothClass("Remote Control")
MAJOR_CLASS.PERIPHERAL.SENSING_DEVICE = BluetoothClass("Sensing Device")
MAJOR_CLASS.PERIPHERAL.DIGITIZER_TABLET = BluetoothClass("Digitizer Tablet")
MAJOR_CLASS.PERIPHERAL.CARD_READER = BluetoothClass("Card Reader (e.g. SIM Card Reader)")
MAJOR_CLASS.PERIPHERAL.RESERVED = BluetoothClass("Reserved")

MAJOR_CLASS.IMAGING.UNCATEGORIZED = BluetoothClass("Uncategorized, code for device not assigned")
MAJOR_CLASS.IMAGING.DISPLAY = BluetoothClass("Display")
MAJOR_CLASS.IMAGING.CAMERA = BluetoothClass("Camera")
MAJOR_CLASS.IMAGING.SCANNER = BluetoothClass("Scanner")
MAJOR_CLASS.IMAGING.PRINTER = BluetoothClass("Printer")
MAJOR_CLASS.IMAGING.RESERVED = BluetoothClass("Reserved")

SERVICE_CLASS = BluetoothClass("Service Class")
SERVICE_CLASS.LIMITED = BluetoothClass("Limited Discoverable Mode")
SERVICE_CLASS.POSITIONING = BluetoothClass("Positioning (Location identification)")
SERVICE_CLASS.NETWORKING = BluetoothClass("Networking (LAN, Ad hoc, ...)")
SERVICE_CLASS.RENDERING = BluetoothClass("Rendering (Printing, speaking, ...)")
SERVICE_CLASS.CAPTURING = BluetoothClass("Capturing (Scanner, microphone, ...)")
SERVICE_CLASS.OBJECT_TRANSFER = BluetoothClass("Object Transfer (v-Inbox, v-Folder, ...)")
SERVICE_CLASS.AUDIO = BluetoothClass("Audio (Speaker, Microphone, Headset service, ...")
SERVICE_CLASS.TELEPHONY = BluetoothClass("Telephony (Cordless telephony, Modem, Headset service, ...)")
SERVICE_CLASS.INFORMATION = BluetoothClass("Information (WEB-server, WAP-server, ...)")

_ORDERED_MAJOR_CLASSES = (
	MAJOR_CLASS.MISCELLANEOUS,
	MAJOR_CLASS.COMPUTER,
	MAJOR_CLASS.PHONE,
	MAJOR_CLASS.LAN,
	MAJOR_CLASS.AV,
	MAJOR_CLASS.PERIPHERAL,
	MAJOR_CLASS.IMAGING,
)

_SERVICE_CLASSES = (
	(13 - 13, SERVICE_CLASS.LIMITED),
	(16 - 13, SERVICE_CLASS.POSITIONING),
	(17 - 13, SERVICE_CLASS.NETWORKING),
	(18 - 13, SERVICE_CLASS.RENDERING),
	(19 - 13, SERVICE_CLASS.CAPTURING),
	(20 - 13, SERVICE_CLASS.OBJECT_TRANSFER),
	(21 - 13, SERVICE_CLASS.AUDIO),
	(22 - 13, SERVICE_CLASS.TELEPHONY),
	(23 - 13, SERVICE_CLASS.INFORMATION),
)


def _parse_device_class(deviceclass):
	# get some information out of the device class and display it.
	# voodoo magic specified at:
	#
	# https://www.bluetooth.org/foundry/assignnumb/document/baseband
	majorClass = (deviceclass >> 8) & 0xf
	minorClass = (deviceclass >> 2) & 0x3f
	serviceClasses = (deviceclass >> 13) & 0x7ff
	return majorClass, minorClass, serviceClasses


def parse_device_class(deviceclass):
	majorClassCode, minorClassCode, serviceClassCodes = _parse_device_class(deviceclass)
	try:
		majorClass = _ORDERED_MAJOR_CLASSES[majorClassCode]
	except IndexError:
		majorClass = MAJOR_CLASS.UNCATEGORIZED

	serviceClasses = []
	for bitpos, cls in _SERVICE_CLASSES:
		if serviceClassCodes & (1 << bitpos):
			serviceClasses.append(cls)

	return majorClass, minorClassCode, serviceClasses
