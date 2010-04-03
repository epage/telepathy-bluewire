#!/usr/bin/python


import logging

import gobject

import util.misc as misc_utils
import util.go_utils as gobject_utils


_moduleLogger = logging.getLogger(__name__)


class Addressbook(gobject.GObject):

	__gsignals__ = {
		'contacts_changed' : (
			gobject.SIGNAL_RUN_LAST,
			gobject.TYPE_NONE,
			(gobject.TYPE_PYOBJECT, gobject.TYPE_PYOBJECT, gobject.TYPE_PYOBJECT),
		),
	}

	def __init__(self, backend, asyncPool):
		gobject.GObject.__init__(self)
		self._backend = backend
		self._addresses = {}
		self._asyncPool = asyncPool

	def update(self, force=False):
		if not force and self._addresses:
			return

		le = gobject_utils.AsyncLinearExecution(self._asyncPool, self._update)
		le.start()

	@misc_utils.log_exception(_moduleLogger)
	def _update(self):
		contacts = yield (
			self._backend.get_contacts,
			(),
			{},
		)
		oldContacts = self._addresses
		oldContactAddresses = set(self.get_addresses())

		self._addresses = self._populate_contacts(contacts)
		newContactAddresses = set(self.get_addresses())

		addedContacts = newContactAddresses - oldContactAddresses
		removedContacts = oldContactAddresses - newContactAddresses
		changedContacts = set(
			contactAddress
			for contactAddress in newContactAddresses.intersection(oldContactAddresses)
			if self._addresses[contactAddress] != oldContacts[contactAddress]
		)

		if addedContacts or removedContacts or changedContacts:
			message = self, addedContacts, removedContacts, changedContacts
			self.emit("contacts_changed", addedContacts, removedContacts, changedContacts)

	def get_addresses(self):
		return self._addresses.iterkeys()

	def get_contact_name(self, address):
		return self._addresses[address]["name"]

	def _populate_contacts(self, contacts):
		addresses = {}
		for address, deviceclass, name in contacts:
			_moduleLogger.debug("%r %r %r" % (address, deviceclass, name))
			addresses[address] = {
				"name": name,
				"class": deviceclass,
			}
		return addresses


gobject.type_register(Addressbook)
