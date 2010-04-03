#!/usr/bin/python

import sys
sys.path.insert(0,"../src")
import logging

import protocol.backend as backend

def main():
	logging.basicConfig(level=logging.DEBUG)

	bb = backend.BluetoothBackend()
	bb.login()

	contacts = bb.get_contacts()
	for address, deviceclass, name in contacts:
		print address, name
		major, minor, services = backend.parse_device_class(deviceclass)
		print str(major), ":", str(minor), [str(service) for service in services]

	bb.logout()

if __name__ == "__main__":
	main()
