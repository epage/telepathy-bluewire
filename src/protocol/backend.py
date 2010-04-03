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


# The L2CAP spec (page. 278) say "PSM values are separated into two ranges.
# Values in the first range are assigned by the Bluetooth SIG and indicate
# protocols. The second range of values [0x1001 - 0xffff] are dynamically
# allocated and used in conjunction with the Service Discovery Protocol (SDP).
# The dynamically assigned values may be used to support multiple
# implementations of a particular protocol, e.g., RFCOMM, residing on top of
# L2CAP or for prototyping an experimental protocol."
CHAT_PROTOCOL = 0x1001


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

	@misc_utils.log_exception(_moduleLogger)
	def _on_data(self, source, condition):
		self.emit("data_ready")
		return True


gobject.type_register(_BluetoothConnection)


class _BluetoothListener(gobject.GObject):

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

	@misc_utils.log_exception(_moduleLogger)
	def _on_incoming(self, source, condition):
		newSocket, (address, psm) = self._socket.accept()
		newSocket.settimeout(self._timeout)
		connection = _BluetoothConnection(newSocket, address, self._psm)
		self.emit("incoming", connection)
		return True


gobject.type_register(_BluetoothListener)


class _DeviceDiscoverer(bluetooth.DeviceDiscoverer):

	def __init__(self):
		bluetooth.DeviceDiscoverer.__init__(self)
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

		readfiles = [self, ]
		while self.is_inquiring or 0 < len(self.names_to_find):
			# The whole reason for overriding this
			_moduleLogger.debug("Event (%r, %r)"% (self.is_inquiring, self.names_to_find))
			rfds = select.select(readfiles, [], [])[0]
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
		'incoming' : (
			gobject.SIGNAL_RUN_LAST,
			gobject.TYPE_NONE,
			(gobject.TYPE_PYOBJECT, ),
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
		self._listenerIds = {}

	def login(self):
		self._disco = _DeviceDiscoverer()
		self._listeners[CHAT_PROTOCOL] = _BluetoothListener(CHAT_PROTOCOL, self._timeout)
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
		self._disco.cancel_inquiry() # precaution
		self.emit("logout")

	def is_logged_in(self):
		if self._listeners:
			return True
		else:
			return False

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

	def connect(self, addr, protocol):
		sock = bluetooth.BluetoothSocket(bluetooth.L2CAP)
		sock.settimeout(self._timeout)
		try:
			sock.connect((addr, protocol))
		except bluetooth.error, e:
			sock.close()
			raise

		return _BluetoothConnection(sock, addr, protocol)

	@misc_utils.log_exception(_moduleLogger)
	def _on_incoming(self, connection):
		self.emit("incoming", connection)
		return True


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
