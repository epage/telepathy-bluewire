from __future__ import with_statement

import os
import cmd
import StringIO
import time
import datetime
import logging

import telepathy

import constants
import tp
import util.misc as misc_utils


_moduleLogger = logging.getLogger(__name__)


class DebugPromptChannel(tp.ChannelTypeText, cmd.Cmd):

	def __init__(self, connection, manager, props, contactHandle):
		self.__manager = manager
		self.__props = props

		cmd.Cmd.__init__(self, "Debug Prompt")
		self.use_rawinput = False
		tp.ChannelTypeText.__init__(self, connection, manager, props)
		self.__nextRecievedId = 0
		self.__lastMessageTimestamp = datetime.datetime(1, 1, 1)

		self.__otherHandle = contactHandle

	@misc_utils.log_exception(_moduleLogger)
	def Send(self, messageType, text):
		if messageType != telepathy.CHANNEL_TEXT_MESSAGE_TYPE_NORMAL:
			raise telepathy.errors.NotImplemented("Unhandled message type: %r" % messageType)

		self.Sent(int(time.time()), messageType, text)

		oldStdin, oldStdout = self.stdin, self.stdout
		try:
			self.stdin = currentStdin = StringIO.StringIO()
			self.stdout = currentStdout = StringIO.StringIO()
			self.onecmd(text)
		finally:
			self.stdin, self.stdout = oldStdin, oldStdout

		stdoutData = currentStdout.getvalue().strip()
		if stdoutData:
			self._report_new_message(stdoutData)

	@misc_utils.log_exception(_moduleLogger)
	def Close(self):
		self.close()

	def close(self):
		_moduleLogger.debug("Closing debug")
		tp.ChannelTypeText.Close(self)
		self.remove_from_connection()

	def _report_new_message(self, message):
		currentReceivedId = self.__nextRecievedId

		timestamp = int(time.time())
		type = telepathy.CHANNEL_TEXT_MESSAGE_TYPE_NORMAL

		self.Received(currentReceivedId, timestamp, self.__otherHandle, type, 0, message.strip())

		self.__nextRecievedId += 1

	def do_reset_state_machine(self, args):
		try:
			args = args.strip().lower()
			if not args:
				args  = "all"
			if args == "all":
				for machine in self._conn.session.stateMachine._machines:
					machine.reset_timers()
			elif args == "contacts":
				self._conn.session.addressbookStateMachine.reset_timers()
			else:
				self._report_new_message('Unknown machine "%s"' % (args, ))
		except Exception, e:
			self._report_new_message(str(e))

	def help_reset_state_machine(self):
		self._report_new_message("""Reset the refreshing state machine.
"reset_state_machine" - resets all
"reset_state_machine all"
"reset_state_machine contacts"
"reset_state_machine voicemail"
"reset_state_machine texts"
""")

	def do_get_state(self, args):
		if args:
			self._report_new_message("No arguments supported")
			return

		try:
			state = self._conn.session.stateMachine.state
			self._report_new_message(str(state))
		except Exception, e:
			self._report_new_message(str(e))

	def help_get_state(self):
		self._report_new_message("Print the current state the refreshing state machine is in")

	def do_get_polling(self, args):
		if args:
			self._report_new_message("No arguments supported")
			return
		self._report_new_message("\n".join((
			"Contacts:", repr(self._conn.session.addressbookStateMachine)
		)))

	def help_get_polling(self):
		self._report_new_message("Prints the frequency each of the state machines updates")

	def do_get_state_status(self, args):
		if args:
			self._report_new_message("No arguments supported")
			return
		self._report_new_message("\n".join((
			"Contacts:", str(self._conn.session.addressbookStateMachine)
		)))

	def help_get_state_status(self):
		self._report_new_message("Prints the current setting for the state machines")

	def help_version(self):
		self._report_new_message("Prints the version (hint: %s-%s)" % (constants.__version__, constants.__build__))

	def do_grab_log(self, args):
		if args:
			self._report_new_message("No arguments supported")
			return

		try:
			publishProps = self._conn.generate_props(telepathy.CHANNEL_TYPE_FILE_TRANSFER, self.__otherHandle, False)
			self._conn._channel_manager.channel_for_props(publishProps, signal=True)
		except Exception, e:
			self._report_new_message(str(e))

	def help_grab_log(self):
		self._report_new_message("Download the debug log for including with bug report")
		self._report_new_message("Warning: this may contain sensitive information")

	def do_save_log(self, args):
		if not args:
			self._report_new_message("Must specify a filename to save the log to")
			return

		try:
			filename = os.path.expanduser(args)
			with open(constants._user_logpath_, "r") as f:
				logLines = f.xreadlines()
				log = "".join(logLines)
			with open(filename, "w") as f:
				f.write(log)
		except Exception, e:
			self._report_new_message(str(e))

	def help_save_log(self):
		self._report_new_message("Save the log to a specified location")
