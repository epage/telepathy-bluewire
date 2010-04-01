#!/usr/bin/python


import logging

import gobject


_moduleLogger = logging.getLogger(__name__)


class Addressbook(object):

	__gsignals__ = {
		'contacts_changed' : (
			gobject.SIGNAL_RUN_LAST,
			gobject.TYPE_NONE,
			(gobject.TYPE_OBJECT, gobject.TYPE_OBJECT, gobject.TYPE_OBJECT, gobject.TYPE_OBJECT),
		),
	}

	def __init__(self, backend):
		self._backend = backend
		self._addresses = {}

	def update(self, force=False):
		if not force and self._addresses:
			return
		oldContacts = self._addresses
		oldContactAddresses = set(self.get_addresses())

		self._addresses = {}
		self._populate_contacts()
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
			self.emit("contacts_changed", self, addedContacts, removedContacts, changedContacts)

	def get_addresses(self):
		return self._addresses.iterkeys()

	def _populate_contacts(self):
		if self._addresses:
			return
		contacts = self._backend.get_contacts()
		for contact in contacts:
			self._addresses[contact] = {}


gobject.type_register(Addressbook)
