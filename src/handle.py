import logging
import weakref

import telepathy


_moduleLogger = logging.getLogger("handle")


class TheOneRingHandle(telepathy.server.Handle):
	"""
	Instances are memoized
	"""

	def __init__(self, connection, id, handleType, name):
		telepathy.server.Handle.__init__(self, id, handleType, name)
		self._conn = weakref.proxy(connection)

	def __repr__(self):
		return "<%s id=%u name='%s'>" % (
			type(self).__name__, self.id, self.name
		)

	id = property(telepathy.server.Handle.get_id)
	type = property(telepathy.server.Handle.get_type)
	name = property(telepathy.server.Handle.get_name)


class ConnectionHandle(TheOneRingHandle):

	def __init__(self, connection, id):
		handleType = telepathy.HANDLE_TYPE_CONTACT
		handleName = connection.username
		TheOneRingHandle.__init__(self, connection, id, handleType, handleName)

		self.profile = connection.username


def strip_number(prettynumber):
	"""
	function to take a phone number and strip out all non-numeric
	characters

	>>> strip_number("+012-(345)-678-90")
	'01234567890'
	"""
	import re
	uglynumber = re.sub('\D', '', prettynumber)
	return uglynumber


class ContactHandle(TheOneRingHandle):

	def __init__(self, connection, id, contactId, phoneNumber):
		handleType = telepathy.HANDLE_TYPE_CONTACT
		handleName = self.to_handle_name(contactId, phoneNumber)
		TheOneRingHandle.__init__(self, connection, id, handleType, handleName)

		self._contactId = contactId
		self._phoneNumber = phoneNumber

	@staticmethod
	def from_handle_name(handleName):
		parts = handleName.split("#")
		assert len(parts) == 2
		contactId, contactNumber = parts[0:2]
		return contactId, contactNumber

	@staticmethod
	def to_handle_name(contactId, contactNumber):
		handleName = "#".join((contactId, strip_number(contactNumber)))
		return handleName

	@property
	def contactID(self):
		return self._contactId

	@property
	def contactDetails(self):
		return self._conn.addressbook.get_contact_details(self._id)


class ListHandle(TheOneRingHandle):

	def __init__(self, connection, id, listName):
		handleType = telepathy.HANDLE_TYPE_LIST
		handleName = listName
		TheOneRingHandle.__init__(self, connection, id, handleType, handleName)


_HANDLE_TYPE_MAPPING = {
	'connection': ConnectionHandle,
	'contact': ContactHandle,
	'list': ListHandle,
}


def create_handle_factory():

	cache = weakref.WeakValueDictionary()

	def create_handle(connection, type, *args):
		Handle = _HANDLE_TYPE_MAPPING[type]
		key = Handle, connection.username, args
		try:
			handle = cache[key]
			isNewHandle = False
		except KeyError:
			# The misnamed get_handle_id requests a new handle id
			handle = Handle(connection, connection.get_handle_id(), *args)
			cache[key] = handle
			isNewHandle = True
		connection._handles[handle.get_type(), handle.get_id()] = handle
		handleStatus = "Is New!" if isNewHandle else "From Cache"
		_moduleLogger.info("Created Handle: %r (%s)" % (handle, handleStatus))
		return handle

	return create_handle


create_handle = create_handle_factory()
