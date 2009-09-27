import telepathy


class LocationMixin(telepathy.server.ConnectionInterfaceLocation):

	def __init__(self):
		telepathy.server.ConnectionInterfaceLocation.__init__(self)

	@property
	def gvoice_backend(self):
		"""
		@abstract
		"""
		raise NotImplementedError()

	def GetLocations(self, contacts):
		"""
		@returns {Contact: {Location Type: Location}}
		"""
		raise NotImplementedError()

	def RequestLocation(self, contact):
		"""
		@returns {Location Type: Location}
		"""
		raise NotImplementedError()

	def SetLocation(self, location):
		"""
		Since presence is based off of phone numbers, not allowing the client to change it
		"""
		raise telepathy.errors.PermissionDenied()
