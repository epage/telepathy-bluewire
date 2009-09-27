import weakref
import logging

import telepathy

import constants
import gv_backend
import handle
import channel_manager
import simple_presence


class TheOneRingConnection(telepathy.server.Connection, simple_presence.SimplePresenceMixin):

	MANDATORY_PARAMETERS = {
		'account' : 's',
		'password' : 's'
	}
	OPTIONAL_PARAMETERS = {
	}
	PARAMETER_DEFAULTS = {
	}

	def __init__(self, manager, parameters):
		try:
			self.check_parameters(parameters)
			account = unicode(parameters['account'])

			telepathy.server.Connection.__init__(
				self,
				constants._telepathy_protocol_name_,
				account,
				constants._telepathy_implementation_name_
			)

			self._manager = weakref.proxy(manager)
			self._credentials = (
				parameters['account'].encode('utf-8'),
				parameters['password'].encode('utf-8'),
			)
			self._channelManager = channel_manager.ChannelManager(self)

			cookieFilePath = "%s/cookies.txt" % constants._data_path_
			self._backend = gv_backend.GVDialer(cookieFilePath)

			self.set_self_handle(handle.create_handle(self, 'connection'))

			logging.info("Connection to the account %s created" % account)
		except Exception, e:
			logging.exception("Failed to create Connection")
			raise

	@property
	def manager(self):
		return self._manager

	@property
	def gvoice_backend(self):
		return self._backend

	@property
	def username(self):
		self._credentials[0]

	def handle(self, handleType, handleId):
		self.check_handle(handleType, handleId)
		return self._handles[handleType, handleId]

	def Connect(self):
		"""
		For org.freedesktop.telepathy.Connection
		"""
		self.StatusChanged(
			telepathy.CONNECTION_STATUS_CONNECTING,
			telepathy.CONNECTION_STATUS_REASON_REQUESTED
		)
		try:
			self._backend.login(*self._credentials)
		except gv_backend.NetworkError:
			self.StatusChanged(
				telepathy.CONNECTION_STATUS_DISCONNECTED,
				telepathy.CONNECTION_STATUS_REASON_NETWORK_ERROR
			)
		except Exception:
			self.StatusChanged(
				telepathy.CONNECTION_STATUS_DISCONNECTED,
				telepathy.CONNECTION_STATUS_REASON_AUTHENTICATION_FAILED
			)
		else:
			self.StatusChanged(
				telepathy.CONNECTION_STATUS_CONNECTED,
				telepathy.CONNECTION_STATUS_REASON_REQUESTED
			)

	def Disconnect(self):
		"""
		For org.freedesktop.telepathy.Connection
		"""
		try:
			self._backend.logout()
			logging.info("Disconnected")
		except Exception:
			logging.exception("Disconnecting Failed")
		self.StatusChanged(
			telepathy.CONNECTION_STATUS_DISCONNECTED,
			telepathy.CONNECTION_STATUS_REASON_REQUESTED
		)

	def RequestChannel(self, type, handleType, handleId, suppressHandler):
		"""
		For org.freedesktop.telepathy.Connection

		@param type DBus interface name for base channel type
		@param handleId represents a contact, list, etc according to handleType

		@returns DBus object path for the channel created or retrieved
		"""
		self.check_connected()

		channel = None
		channelManager = self._channelManager
		handle = self.handle(handleType, handleId)

		if type == telepathy.CHANNEL_TYPE_CONTACT_LIST:
			channel = channelManager.channel_for_list(handle, suppressHandler)
		elif type == telepathy.CHANNEL_TYPE_TEXT:
			if handleType != telepathy.HANDLE_TYPE_CONTACT:
				raise telepathy.NotImplemented("Only Contacts are allowed")
			contact = handle.contact
			channel = channelManager.channel_for_text(handle, None, suppressHandler)
		else:
			raise telepathy.NotImplemented("unknown channel type %s" % type)

		return channel._object_path

	def RequestHandles(self, handleType, names, sender):
		"""
		For org.freedesktop.telepathy.Connection
		"""
		self.check_connected()
		self.check_handleType(handleType)

		handles = []
		for name in names:
			name = name.encode('utf-8')
			if handleType == telepathy.HANDLE_TYPE_CONTACT:
				h = self._create_contact_handle(name)
			elif handleType == telepathy.HANDLE_TYPE_LIST:
				h = handle.create_handle(self, 'list', name)
			elif handleType == telepathy.HANDLE_TYPE_GROUP:
				h = handle.create_handle(self, 'group', name)
			else:
				raise telepathy.NotAvailable('Handle type unsupported %d' % handleType)
			handles.append(h.id)
			self.add_client_handle(handle, sender)
		return handles

	def _create_contact_handle(self, name):
		requestedContactId, requestedContactName = handle.field_split(name)

		contacts = self._backend.get_contacts()
		contactsFound = [
			(contactId, contactName) for (contactId, contactName) in contacts
			if contactName == name
		]

		if 0 < len(contactsFound):
			contactId, contactName = contactsFound[0]
			h = handle.create_handle(self, 'contact', contactId, contactName)
		else:
			h = handle.create_handle(self, 'contact', requestedContactId, requestedContactName)
