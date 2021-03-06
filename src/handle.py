import logging
import weakref

import telepathy

import tp


_moduleLogger = logging.getLogger(__name__)


class BluewireHandle(tp.Handle):
	"""
	Instances are memoized
	"""

	def __init__(self, connection, id, handleType, name):
		tp.Handle.__init__(self, id, handleType, name)
		self._conn = weakref.proxy(connection)

	def __repr__(self):
		return "<%s id=%u name='%s'>" % (
			type(self).__name__, self.id, self.name
		)

	id = property(tp.Handle.get_id)
	type = property(tp.Handle.get_type)
	name = property(tp.Handle.get_name)


class ConnectionHandle(BluewireHandle):

	def __init__(self, connection, id):
		handleType = telepathy.HANDLE_TYPE_CONTACT
		handleName = connection.username
		BluewireHandle.__init__(self, connection, id, handleType, handleName)

		self.profile = connection.username


class ContactHandle(BluewireHandle):

	def __init__(self, connection, id, address):
		self._address = address

		handleType = telepathy.HANDLE_TYPE_CONTACT
		handleName = self._address
		BluewireHandle.__init__(self, connection, id, handleType, handleName)

	@property
	def address(self):
		return self._address


class ListHandle(BluewireHandle):

	def __init__(self, connection, id, listName):
		handleType = telepathy.HANDLE_TYPE_LIST
		handleName = listName
		BluewireHandle.__init__(self, connection, id, handleType, handleName)


_HANDLE_TYPE_MAPPING = {
	'connection': ConnectionHandle,
	'contact': ContactHandle,
	'list': ListHandle,
}


def create_handle_factory():

	cache = weakref.WeakValueDictionary()

	def _create_handle(connection, type, *args):
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
		if isNewHandle:
			handleStatus = "Is New!" if isNewHandle else "From Cache"
			_moduleLogger.debug("Created Handle: %r (%s)" % (handle, handleStatus))
		return handle

	return _create_handle


create_handle = create_handle_factory()
