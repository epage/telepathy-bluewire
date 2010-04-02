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
		# first validate that no other handle types are included
		handleId, alias = None, None
		for handleId, alias in aliases.iteritems():
			h = self.get_handle_by_id(telepathy.HANDLE_TYPE_CONTACT, handleId)
			if isinstance(h, handle.ConnectionHandle):
				break
		else:
			raise telepathy.errors.PermissionDenied("No user customizable aliases")

		uglyNumber = misc_utils.normalize_number(alias)
		if len(uglyNumber) == 0:
			# Reset to the original from login if one was provided
			uglyNumber = self.callbackNumberParameter
		if not misc_utils.is_valid_number(uglyNumber):
			raise telepathy.errors.InvalidArgument("Invalid phone number %r" % (uglyNumber, ))

		# Update callback
		self.session.backend.set_callback_number(uglyNumber)

		# Inform of change
		userAlias = make_pretty(uglyNumber)
		changedAliases = ((handleId, userAlias), )
		self.AliasesChanged(changedAliases)

	def _get_alias(self, handleId):
		h = self.get_handle_by_id(telepathy.HANDLE_TYPE_CONTACT, handleId)
		if isinstance(h, handle.ConnectionHandle):
			aliasNumber = self.session.backend.get_callback_number()
			userAlias = make_pretty(aliasNumber)
			return userAlias
		else:
			number = h.phoneNumber
			try:
				contactAlias = self.session.addressbook.get_contact_name(number)
			except KeyError:
				contactAlias = make_pretty(number)
			return contactAlias
