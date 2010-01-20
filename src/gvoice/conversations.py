#!/usr/bin/python

from __future__ import with_statement

import logging

try:
	import cPickle
	pickle = cPickle
except ImportError:
	import pickle

import util.coroutines as coroutines
import util.misc as util_misc


_moduleLogger = logging.getLogger("gvoice.conversations")


class Conversations(object):

	def __init__(self, getter):
		self._get_raw_conversations = getter
		self._conversations = {}

		self.updateSignalHandler = coroutines.CoTee()

	@property
	def _name(self):
		return repr(self._get_raw_conversations.__name__)

	def load(self, path):
		assert not self._conversations
		try:
			with open(path, "rb") as f:
				self._conversations = pickle.load(f)
		except (pickle.PickleError, IOError):
			_moduleLogger.exception("While loading for %s" % self._name)

	def save(self, path):
		try:
			with open(path, "wb") as f:
				pickle.dump(self._conversations, f, pickle.HIGHEST_PROTOCOL)
		except (pickle.PickleError, IOError):
			_moduleLogger.exception("While saving for %s" % self._name)

	def update(self, force=False):
		if not force and self._conversations:
			return

		oldConversationIds = set(self._conversations.iterkeys())

		updateConversationIds = set()
		conversations = list(self._get_raw_conversations())
		conversations.sort()
		for conversation in conversations:
			key = util_misc.normalize_number(conversation.number)
			try:
				mergedConversations = self._conversations[key]
			except KeyError:
				mergedConversations = MergedConversations()
				self._conversations[key] = mergedConversations

			try:
				mergedConversations.append_conversation(conversation)
				isConversationUpdated = True
			except RuntimeError, e:
				if False:
					_moduleLogger.info("%s Skipping conversation for %r because '%s'" % (self._name, key, e))
				isConversationUpdated = False

			if isConversationUpdated:
				updateConversationIds.add(key)

		if updateConversationIds:
			message = (self, updateConversationIds, )
			self.updateSignalHandler.stage.send(message)

	def get_conversations(self):
		return self._conversations.iterkeys()

	def get_conversation(self, key):
		return self._conversations[key]

	def clear_conversation(self, key):
		try:
			del self._conversations[key]
		except KeyError:
			_moduleLogger.info("%s Conversation never existed for %r" % (self._name, key, ))

	def clear_all(self):
		self._conversations.clear()


class MergedConversations(object):

	def __init__(self):
		self._conversations = []

	def append_conversation(self, newConversation):
		self._validate(newConversation)
		for similarConversation in self._find_related_conversation(newConversation.id):
			self._update_previous_related_conversation(similarConversation, newConversation)
			self._remove_repeats(similarConversation, newConversation)
		self._conversations.append(newConversation)

	@property
	def conversations(self):
		return self._conversations

	def _validate(self, newConversation):
		if not self._conversations:
			return

		for constantField in ("number", ):
			assert getattr(self._conversations[0], constantField) == getattr(newConversation, constantField), "Constant field changed, soemthing is seriously messed up: %r v %r" % (
				getattr(self._conversations[0], constantField),
				getattr(newConversation, constantField),
			)

		if newConversation.time <= self._conversations[-1].time:
			raise RuntimeError("Conversations got out of order")

	def _find_related_conversation(self, convId):
		similarConversations = (
			conversation
			for conversation in self._conversations
			if conversation.id == convId
		)
		return similarConversations

	def _update_previous_related_conversation(self, relatedConversation, newConversation):
		for commonField in ("isRead", "isSpam", "isTrash", "isArchived"):
			newValue = getattr(newConversation, commonField)
			setattr(relatedConversation, commonField, newValue)

	def _remove_repeats(self, relatedConversation, newConversation):
		newConversationMessages = newConversation.messages
		newConversation.messages = [
			newMessage
			for newMessage in newConversationMessages
			if newMessage not in relatedConversation.messages
		]
		_moduleLogger.debug("Found %d new messages in conversation %s (%d/%d)" % (
			len(newConversationMessages) - len(newConversation.messages),
			newConversation.id,
			len(newConversation.messages),
			len(newConversationMessages),
		))
		assert 0 < len(newConversation.messages), "Everything shouldn't have been removed"
