import logging

import telepathy

import util.misc as misc_utils
import tp
import handle
import protocol.state_machine as state_machine


_moduleLogger = logging.getLogger(__name__)


class BluewirePresence(object):

	# Note: these strings are also in the bluewire.profile file
	ONLINE = 'available'
	AWAY = 'away'
	HIDDEN = 'hidden'
	OFFLINE = 'offline'

	TO_PRESENCE_TYPE = {
		ONLINE: telepathy.constants.CONNECTION_PRESENCE_TYPE_AVAILABLE,
		AWAY: telepathy.constants.CONNECTION_PRESENCE_TYPE_AWAY,
		HIDDEN: telepathy.constants.CONNECTION_PRESENCE_TYPE_HIDDEN,
		OFFLINE: telepathy.constants.CONNECTION_PRESENCE_TYPE_OFFLINE,
	}

	@property
	def session(self):
		"""
		@abstract
		"""
		raise NotImplementedError()

	def Disconnect(self):
		"""
		@abstract
		"""
		raise NotImplementedError("Abstract function called")

	def get_handle_by_id(self, handleType, handleId):
		"""
		@abstract
		"""
		raise NotImplementedError("Abstract function called")

	def get_presences(self, contactIds):
		"""
		@return {ContactHandle: (Status, Presence Type, Message)}
		"""
		presences = {}
		for handleId in contactIds:
			h = self.get_handle_by_id(telepathy.HANDLE_TYPE_CONTACT, handleId)
			if isinstance(h, handle.ConnectionHandle):
				isListening = self.session.backend.is_listening()
				if not isListening:
					presence = BluewirePresence.HIDDEN
				else:
					state = self.session.stateMachine.state
					if state == state_machine.StateMachine.STATE_ACTIVE:
						presence = BluewirePresence.ONLINE
					elif state == state_machine.StateMachine.STATE_IDLE:
						presence = BluewirePresence.AWAY
					else:
						raise telepathy.errors.InvalidArgument("Unsupported state on the state machine: %s" % state)
				presenceType = BluewirePresence.TO_PRESENCE_TYPE[presence]
			else:
				presence = BluewirePresence.ONLINE
				presenceType = BluewirePresence.TO_PRESENCE_TYPE[presence]

			presences[h] = (presenceType, presence)
		return presences

	def set_presence(self, status):
		if status == self.OFFLINE:
			self.Disconnect()
		elif status == self.HIDDEN:
			if self.session.backend.is_listening():
				self.session.backend.enable_listening(False)
			else:
				_moduleLogger.debug("Setting presence to hidden but already listening for connections")
		else:
			if status == self.ONLINE:
				self.session.stateMachine.set_state(state_machine.StateMachine.STATE_ACTIVE)
			elif status == self.AWAY:
				self.session.stateMachine.set_state(state_machine.StateMachine.STATE_IDLE)
			else:
				raise telepathy.errors.InvalidArgument("Unsupported status: %r" % status)

			if not self.session.backend.is_listening():
				self.session.backend.enable_listening(True)
			else:
				_moduleLogger.debug(
					"Setting presence to %s but already listening for connections" % status
				)
		_moduleLogger.info("Setting Presence to '%s'" % status)


class SimplePresenceMixin(tp.ConnectionInterfaceSimplePresence, BluewirePresence):

	def __init__(self):
		tp.ConnectionInterfaceSimplePresence.__init__(self)
		BluewirePresence.__init__(self)

		self._implement_property_get(
			tp.CONNECTION_INTERFACE_SIMPLE_PRESENCE,
			{'Statuses' : self._get_statuses}
		)

	@misc_utils.log_exception(_moduleLogger)
	def GetPresences(self, contacts):
		"""
		@return {ContactHandle: (Status, Presence Type, Message)}
		"""
		personalMessage = u""
		return dict(
			(h, (presenceType, presence, personalMessage))
			for (h, (presenceType, presence)) in self.get_presences(contacts).iteritems()
		)

	@misc_utils.log_exception(_moduleLogger)
	def SetPresence(self, status, message):
		if message:
			raise telepathy.errors.InvalidArgument("Messages aren't supported")

		self.set_presence(status)

	def _get_statuses(self):
		"""
		Property mapping presence statuses available to the corresponding presence types

		@returns {Name: (Telepathy Type, May Set On Self, Can Have Message)}
		"""
		return dict(
			(localType, (telepathyType, True, False))
			for (localType, telepathyType) in self.TO_PRESENCE_TYPE.iteritems()
		)
