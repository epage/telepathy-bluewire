import logging

import telepathy

try:
	import conic as _conic
	conic = _conic
except (ImportError, OSError):
	conic = None

try:
	import osso as _osso
	osso = _osso
except (ImportError, OSError):
	osso = None

import constants
import util.go_utils as gobject_utils
import util.misc as misc_utils


_moduleLogger = logging.getLogger(__name__)


class TimedDisconnect(object):

	def __init__(self, connRef):
		self._connRef = connRef
		self.__delayedDisconnect = gobject_utils.Timeout(self._on_delayed_disconnect)

	def start(self):
		self.__delayedDisconnect.start(seconds=20)

	def stop(self):
		self.__delayedDisconnect.cancel()

	@misc_utils.log_exception(_moduleLogger)
	def _on_delayed_disconnect(self):
		_moduleLogger.info("Timed disconnect occurred")
		self._connRef().disconnect(telepathy.CONNECTION_STATUS_REASON_NETWORK_ERROR)


class AutoDisconnect(object):

	def __init__(self, connRef):
		self._connRef = connRef
		if conic is not None:
			self.__connection = conic.Connection()
		else:
			self.__connection = None

		self.__connectionEventId = None
		self.__delayedDisconnect = gobject_utils.Timeout(self._on_delayed_disconnect)

	def start(self):
		if self.__connection is not None:
			self.__connectionEventId = self.__connection.connect("connection-event", self._on_connection_change)

	def stop(self):
		self._cancel_delayed_disconnect()

	@misc_utils.log_exception(_moduleLogger)
	def _on_connection_change(self, connection, event):
		"""
		@note Maemo specific
		"""
		status = event.get_status()
		error = event.get_error()
		iap_id = event.get_iap_id()
		bearer = event.get_bearer_type()

		if status == conic.STATUS_DISCONNECTED:
			_moduleLogger.info("Disconnected from network, starting countdown to logoff")
			self.__delayedDisconnect.start(seconds=5)
		elif status == conic.STATUS_CONNECTED:
			_moduleLogger.info("Connected to network")
			self._cancel_delayed_disconnect()
		else:
			_moduleLogger.info("Other status: %r" % (status, ))

	@misc_utils.log_exception(_moduleLogger)
	def _cancel_delayed_disconnect(self):
		_moduleLogger.info("Cancelling auto-log off")
		self.__delayedDisconnect.cancel()

	@misc_utils.log_exception(_moduleLogger)
	def _on_delayed_disconnect(self):
		if not self._connRef().session.is_logged_in():
			_moduleLogger.info("Received connection change event when not logged in")
			return
		try:
			self._connRef().disconnect(telepathy.CONNECTION_STATUS_REASON_NETWORK_ERROR)
		except Exception:
			_moduleLogger.exception("Error durring disconnect")


class DisconnectOnShutdown(object):
	"""
	I'm unsure when I get notified of shutdown or if I have enough time to do
	anything about it, but thought this might help
	"""

	def __init__(self, connRef):
		self._connRef = connRef

		self._osso = None
		self._deviceState = None

	def start(self):
		if osso is not None:
			self._osso = osso.Context(constants.__app_name__, constants.__version__, False)
			self._deviceState = osso.DeviceState(self._osso)
			self._deviceState.set_device_state_callback(self._on_device_state_change, 0)
		else:
			_moduleLogger.warning("No device state support")

	def stop(self):
		try:
			self._deviceState.close()
		except AttributeError:
			pass # Either None or close was removed (in Fremantle)
		self._deviceState = None
		try:
			self._osso.close()
		except AttributeError:
			pass # Either None or close was removed (in Fremantle)
		self._osso = None

	@misc_utils.log_exception(_moduleLogger)
	def _on_device_state_change(self, shutdown, save_unsaved_data, memory_low, system_inactivity, message, userData):
		"""
		@note Hildon specific
		"""
		try:
			self._connRef().disconnect(telepathy.CONNECTION_STATUS_REASON_REQUESTED)
		except Exception:
			_moduleLogger.exception("Error durring disconnect")
