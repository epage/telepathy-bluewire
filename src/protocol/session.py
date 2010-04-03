#!/usr/bin/env python

import logging

import backend
import addressbook
import state_machine

import util.go_utils as gobject_utils
import util.misc as misc_utils


_moduleLogger = logging.getLogger(__name__)


class Session(object):

	_DEFAULTS = {
		"contacts": (12, "hours"),
	}

	_MINIMUM_MESSAGE_PERIOD = state_machine.to_seconds(minutes=30)

	def __init__(self, defaults = None):
		if defaults is None:
			defaults = self._DEFAULTS
		else:
			for key, (quant, unit) in defaults.iteritems():
				if quant == 0:
					defaults[key] = (self._DEFAULTS[key], unit)
				elif quant < 0:
					defaults[key] = (state_machine.UpdateStateMachine.INFINITE_PERIOD, unit)

		self._asyncPool = gobject_utils.AsyncPool()
		self._backend = backend.BluetoothBackend()

		if defaults["contacts"][0] == state_machine.UpdateStateMachine.INFINITE_PERIOD:
			contactsPeriodInSeconds = state_machine.UpdateStateMachine.INFINITE_PERIOD
		else:
			contactsPeriodInSeconds = state_machine.to_seconds(
				**{defaults["contacts"][1]: defaults["contacts"][0],}
			)
		self._addressbook = addressbook.Addressbook(self._backend, self._asyncPool)
		self._addressbookStateMachine = state_machine.UpdateStateMachine([self.addressbook], "Addressbook")
		self._addressbookStateMachine.set_state_strategy(
			state_machine.StateMachine.STATE_DND,
			state_machine.NopStateStrategy()
		)
		self._addressbookStateMachine.set_state_strategy(
			state_machine.StateMachine.STATE_IDLE,
			state_machine.NopStateStrategy()
		)
		self._addressbookStateMachine.set_state_strategy(
			state_machine.StateMachine.STATE_ACTIVE,
			state_machine.ConstantStateStrategy(contactsPeriodInSeconds)
		)

		self._masterStateMachine = state_machine.MasterStateMachine()
		self._masterStateMachine.append_machine(self._addressbookStateMachine)

		self._lastDndCheck = 0
		self._cachedIsDnd = False

	def close(self):
		self._masterStateMachine.close()

	def login(self, on_success, on_error):
		self._asyncPool.start()

		le = gobject_utils.AsyncLinearExecution(self._asyncPool, self._login)
		le.start(on_success, on_error)

	@misc_utils.log_exception(_moduleLogger)
	def _login(self, on_success, on_error):
		try:
			isLoggedIn = yield (
				self._backend.login,
				(),
				{},
			)
		except Exception, e:
			on_error(e)
			return

		self._masterStateMachine.start()
		on_success(isLoggedIn)

	def logout(self):
		self._asyncPool.stop()
		self._masterStateMachine.stop()
		self._backend.logout()

	def is_logged_in(self):
		return self._backend.is_logged_in()

	@property
	def backend(self):
		"""
		Login enforcing backend
		"""
		assert self.is_logged_in(), "User not logged in"
		return self._backend

	@property
	def addressbook(self):
		return self._addressbook

	@property
	def stateMachine(self):
		return self._masterStateMachine

	@property
	def addressbookStateMachine(self):
		return self._addressbookStateMachine
