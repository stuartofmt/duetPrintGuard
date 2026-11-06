"""
Shared state for duet_printer.py and printer_control.py.

Every module does `import state` and reads / writes `state.<name>`.
Never use `from state import <name>` - that copies the value at import
time and later changes will not be seen.

The real values are set by printer_control.start_printer_monitor() and loginPrinter().
"""

duet = None  # Printer address
duet_port = None  # Printer port
duet_password = None  # Printer password, encoded for a url
plugin = None  # True if running as the DSF plugin
pid = None  # pid of this program

apiModel = None  # 'SBC', 'rr_model' (standalone), or '' when not connected
connectionState = None
urlHeaders = None  # SBC session key
terminateState = None  # 1 while terminating
lastStatusCall = None
lastMessageSeq = None  # duetLapse3's M3291 commands - not used by duetPrintGuard
