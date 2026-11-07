"""
The printer through DSF's own socket, using dsf-python - for the plugin mode, when the printer's SBC is this computer.
A remote SBC or standalone board is reached over the network instead, by duet_printer.py.

The status is kept up to date by a subscription to state.status.  state.upTime is subscribed to as well: it changes
every second, so a patch arrives every second and a lost connection to DSF shows as a timeout within a few seconds.
"""

import json
import threading

from logger_module import logger

PLUGIN_ID = 'duetPrintGuard'
SUBSCRIBED = ['state/status', 'state/upTime']

onChange = None  # Called when the status changes, or the connection to DSF is lost

_status = None  # The printer status from the subscription - None when not connected
_stop = threading.Event()  # Ends the current subscription's reader


def connect():
	"""Connect to DSF on this computer and keep the status up to date in the background. Raises if DSF can not be reached."""
	global _status, _stop
	from dsf.connections import SubscribeConnection, SubscriptionMode  # Only imported when used - this mode is only for an SBC
	disconnect()
	subscription = SubscribeConnection(SubscriptionMode.PATCH, filter_list=SUBSCRIBED)
	try:
		subscription.connect()
		_status = json.loads(subscription.get_serialized_object_model())['state']['status']
	except Exception:
		subscription.close()
		raise
	_stop = threading.Event()
	threading.Thread(name='dsfSubscription', target=_reader, args=(subscription, _stop), daemon=True).start()


def disconnect():
	"""Stop using DSF - e.g. the printer settings changed."""
	global _status
	_stop.set()
	_status = None


def connected():
	return _status is not None


def getStatus():
	"""(status, '') - the same as duet_printer.getStatus.  'disconnected' if DSF can not be reached."""
	return (_status or 'disconnected'), ''


def _reader(subscription, stop):
	global _status
	try:
		while not stop.is_set():
			patch = json.loads(subscription.get_object_model_patch())  # Times out if DSF stops sending
			status = (patch.get('state') or {}).get('status')
			if status and not stop.is_set() and status != _status:
				_status = status
				if onChange is not None:
					onChange()
	except Exception as e:
		if not stop.is_set():
			logger.warning(f'Lost the connection to DSF: {e}')
			_status = None
			if onChange is not None:
				onChange()
	finally:
		subscription.close()


def _command(perform):
	"""Run perform(connection) on a new command connection to DSF."""
	from dsf.connections import CommandConnection
	connection = CommandConnection()
	try:
		connection.connect()
		return perform(connection)
	finally:
		connection.close()


def sendGcode(command):
	"""Send a G/M-code and wait for it to finish. Returns its reply, or None if it could not be sent."""
	try:
		reply = _command(lambda connection: connection.perform_simple_code(command))
		logger.debug(f'Reply to {command}: {reply}')
		return reply
	except Exception as e:
		logger.error(f'Could not send {command} to the printer through DSF: {e}')
		return None


def getVersion():
	"""The main board's firmware version, or 'unknown'."""
	try:
		reply = json.loads(_command(lambda connection: connection.get_serialized_object_model()))
		model = reply.get('result', reply)  # A command connection wraps it in {"success": ..., "result": ...}
		return model['boards'][0]['firmwareVersion']
	except Exception as e:
		logger.debug(f'Could not read the firmware version: {e}')
		return 'unknown'


def publishUiAddress(ip, port):
	"""Put the pages' address in the plugin data, where the DWC plugin page reads it. Only works when DSF started this program."""
	try:
		_command(lambda connection: [connection.set_plugin_data(PLUGIN_ID, key, value) for key, value in (('ip', ip), ('port', port))])
		logger.info(f'Published UI address {ip}:{port} to plugin data')
	except Exception as e:
		logger.warning(f'Could not publish UI address to plugin data: {e}')
