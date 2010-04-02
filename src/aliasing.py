import logging

import telepathy

import tp
import util.misc as misc_utils
import handle


_moduleLogger = logging.getLogger(__name__)


class AliasingMixin(tp.ConnectionInterfaceAliasing):

	def __init__(self):
		tp.ConnectionInterfaceAliasing.__init__(self)

	@property
	def session(self):
		"""
		@abstract
		"""
		raise NotImplementedError("Abstract property called")

	@property
	def username(self):
		"""
		@abstract
		"""
		raise NotImplementedError("Abstract property called")

	def get_handle_by_id(self, handleType, handleId):
		"""
		@abstract
		"""
		raise NotImplementedError("Abstract function called")

	@misc_utils.log_exception(_moduleLogger)
	def GetAliasFlags(self):
		return 0

	@misc_utils.log_exception(_moduleLogger)
	def RequestAliases(self, contactHandleIds):
		_moduleLogger.debug("Called RequestAliases")
		return [self._get_alias(handleId) for handleId in contactHandleIds]

	@misc_utils.log_exception(_moduleLogger)
	def GetAliases(self, contactHandleIds):
		_moduleLogger.debug("Called GetAliases")

		idToAlias = dict(
			(handleId, self._get_alias(handleId))
			for handleId in contactHandleIds
		)
		return idToAlias

	@misc_utils.log_exception(_moduleLogger)
	def SetAliases(self, aliases):
		_moduleLogger.debug("Called SetAliases")
		raise telepathy.errors.PermissionDenied("No user customizable aliases")

	def _get_alias(self, handleId):
		h = self.get_handle_by_id(telepathy.HANDLE_TYPE_CONTACT, handleId)
		if isinstance(h, handle.ConnectionHandle):
			return self.username
		else:
			try:
				contactAlias = self.session.addressbook.get_contact_name(h.address)
			except KeyError:
				contactAlias = h.address
			return contactAlias
