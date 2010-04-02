import weakref
import logging

import telepathy

import constants
import tp
import util.go_utils as gobject_utils
import util.misc as misc_utils

import protocol
import handle

#import aliasing
#import avatars
#import capabilities
#import contacts
#import presence
import requests
#import simple_presence

import autogv
import channel_manager


_moduleLogger = logging.getLogger(__name__)


class BluewireOptions(object):

	useGVContacts = True

	assert protocol.session.Session._DEFAULTS["contacts"][1] == "hours"
	contactsPollPeriodInHours = protocol.session.Session._DEFAULTS["contacts"][0]

	def __init__(self, parameters = None):
		if parameters is None:
			return
		self.useGVContacts = parameters["use-gv-contacts"]
		self.contactsPollPeriodInHours = parameters['contacts-poll-period-in-hours']


class BluewireConnection(
	tp.Connection,
	#aliasing.AliasingMixin,
	#avatars.AvatarsMixin,
	#capabilities.CapabilitiesMixin,
	#contacts.ContactsMixin,
	#presence.PresenceMixin,
	requests.RequestsMixin,
	#simple_presence.SimplePresenceMixin,
):

	# overiding base class variable
	_mandatory_parameters = {
	}
	# overiding base class variable
	_optional_parameters = {
		'contacts-poll-period-in-hours': 'i',
	}
	_parameter_defaults = {
		'contacts-poll-period-in-hours': BluewireOptions.contactsPollPeriodInHours,
	}
	_secret_parameters = set((
	))

	@misc_utils.log_exception(_moduleLogger)
	def __init__(self, manager, parameters):
		self.check_parameters(parameters)

		# Connection init must come first
		self.__options = BluewireOptions(parameters)
		self.__session = protocol.session.Session(
			defaults = {
				"contacts": (self.__options.contactsPollPeriodInHours, "hours"),
			},
		)
		tp.Connection.__init__(
			self,
			constants._telepathy_protocol_name_,
			"device",
			constants._telepathy_implementation_name_
		)
		#aliasing.AliasingMixin.__init__(self)
		#avatars.AvatarsMixin.__init__(self)
		#capabilities.CapabilitiesMixin.__init__(self)
		#contacts.ContactsMixin.__init__(self)
		#presence.PresenceMixin.__init__(self)
		requests.RequestsMixin.__init__(self)
		#simple_presence.SimplePresenceMixin.__init__(self)

		self.__manager = weakref.proxy(manager)
		self.__channelManager = channel_manager.ChannelManager(self)

		self.set_self_handle(handle.create_handle(self, 'connection'))
		self._plumbing = [
			autogv.AutoDisconnect(weakref.ref(self)),
		]
		self._delayedConnect = gobject_utils.Async(self._delayed_connect)

		_moduleLogger.info("Connection created")
		self._timedDisconnect = autogv.TimedDisconnect(weakref.ref(self))
		self._timedDisconnect.start()

	@property
	def manager(self):
		return self.__manager

	@property
	def session(self):
		return self.__session

	@property
	def options(self):
		return self.__options

	@property
	def username(self):
		return self.__credentials[0]

	@property
	def callbackNumberParameter(self):
		return self.__callbackNumberParameter

	def get_handle_by_name(self, handleType, handleName):
		requestedHandleName = handleName.encode('utf-8')
		if handleType == telepathy.HANDLE_TYPE_CONTACT:
			h = handle.create_handle(self, 'contact', requestedHandleName)
		elif handleType == telepathy.HANDLE_TYPE_LIST:
			# Support only server side (immutable) lists
			h = handle.create_handle(self, 'list', requestedHandleName)
		else:
			raise telepathy.errors.NotAvailable('Handle type unsupported %d' % handleType)
		return h

	@property
	def _channel_manager(self):
		return self.__channelManager

	@misc_utils.log_exception(_moduleLogger)
	def Connect(self):
		"""
		For org.freedesktop.telepathy.Connection
		"""
		if self._status != telepathy.CONNECTION_STATUS_DISCONNECTED:
			_moduleLogger.info("Attempting connect when not disconnected")
			return
		_moduleLogger.info("Kicking off connect")
		self._delayedConnect.start()
		self._timedDisconnect.stop()

	@misc_utils.log_exception(_moduleLogger)
	def _delayed_connect(self):
		_moduleLogger.info("Connecting...")
		self.StatusChanged(
			telepathy.CONNECTION_STATUS_CONNECTING,
			telepathy.CONNECTION_STATUS_REASON_REQUESTED
		)
		try:
			self.__session.load(self.__cachePath)

			for plumber in self._plumbing:
				plumber.start()
			self.session.login(*self.__credentials)

			subscribeHandle = self.get_handle_by_name(telepathy.HANDLE_TYPE_LIST, "subscribe")
			subscribeProps = self.generate_props(telepathy.CHANNEL_TYPE_CONTACT_LIST, subscribeHandle, False)
			self.__channelManager.channel_for_props(subscribeProps, signal=True)
			publishHandle = self.get_handle_by_name(telepathy.HANDLE_TYPE_LIST, "publish")
			publishProps = self.generate_props(telepathy.CHANNEL_TYPE_CONTACT_LIST, publishHandle, False)
			self.__channelManager.channel_for_props(publishProps, signal=True)
		except Exception:
			_moduleLogger.exception("Connection Failed")
			self.disconnect(telepathy.CONNECTION_STATUS_REASON_AUTHENTICATION_FAILED)
			return

		_moduleLogger.info("Connected")
		self.StatusChanged(
			telepathy.CONNECTION_STATUS_CONNECTED,
			telepathy.CONNECTION_STATUS_REASON_REQUESTED
		)

	@misc_utils.log_exception(_moduleLogger)
	def Disconnect(self):
		"""
		For org.freedesktop.telepathy.Connection
		"""
		_moduleLogger.info("Kicking off disconnect")
		self.disconnect(telepathy.CONNECTION_STATUS_REASON_REQUESTED)

	@misc_utils.log_exception(_moduleLogger)
	def RequestChannel(self, type, handleType, handleId, suppressHandler):
		"""
		For org.freedesktop.telepathy.Connection

		@param type DBus interface name for base channel type
		@param handleId represents a contact, list, etc according to handleType

		@returns DBus object path for the channel created or retrieved
		"""
		self.check_connected()
		self.check_handle(handleType, handleId)

		h = self.get_handle_by_id(handleType, handleId) if handleId != 0 else None
		props = self.generate_props(type, h, suppressHandler)
		self._validate_handle(props)

		chan = self.__channelManager.channel_for_props(props, signal=True)
		path = chan._object_path
		_moduleLogger.info("RequestChannel Object Path (%s): %s" % (type.rsplit(".", 1)[-1], path))
		return path

	def generate_props(self, channelType, handleObj, suppressHandler, initiatorHandle=None):
		targetHandle = 0 if handleObj is None else handleObj.get_id()
		targetHandleType = telepathy.HANDLE_TYPE_NONE if handleObj is None else handleObj.get_type()
		props = {
			telepathy.CHANNEL_INTERFACE + '.ChannelType': channelType,
			telepathy.CHANNEL_INTERFACE + '.TargetHandle': targetHandle,
			telepathy.CHANNEL_INTERFACE + '.TargetHandleType': targetHandleType,
			telepathy.CHANNEL_INTERFACE + '.Requested': suppressHandler
		}

		if initiatorHandle is not None:
			props[telepathy.CHANNEL_INTERFACE + '.InitiatorHandle'] = initiatorHandle.id

		return props

	def disconnect(self, reason):
		_moduleLogger.info("Disconnecting")

		self._delayedConnect.cancel()
		self._timedDisconnect.stop()

		# Not having the disconnect first can cause weird behavior with clients
		# including not being able to reconnect or even crashing
		self.StatusChanged(
			telepathy.CONNECTION_STATUS_DISCONNECTED,
			reason,
		)

		for plumber in self._plumbing:
			plumber.stop()

		self.__channelManager.close()
		self.manager.disconnected(self)

		self.session.save(self.__cachePath)
		self.session.logout()
		self.session.close()

		# In case one of the above items takes too long (which it should never
		# do), we leave the starting of the shutdown-on-idle counter to the
		# very end
		self.manager.disconnect_completed()

		_moduleLogger.info("Disconnected")
