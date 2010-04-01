import os

__pretty_app_name__ = "Telepathy-Bluewire"
__app_name__ = "telepathy-bluewire"
__version__ = "0.1.0"
__build__ = 0
__app_magic__ = 0xdeadbeef
_data_path_ = os.path.join(os.path.expanduser("~"), ".telepathy-bluewire")
_user_settings_ = "%s/settings.ini" % _data_path_
_user_logpath_ = "%s/bluewire.log" % _data_path_
_telepathy_protocol_name_ = "bluetooth"
_telepathy_implementation_name_ = "bluewire"
