# Release notes

## 1.0.0

This is the initial release for DWC 3.7.x

### Changes from 3.6.x

- Uses DWC 3.7.x plugin APIs
- Changed UI to match Duet3d DWC style
- Removed inbuilt camera support to simplify code base (see multiCam)
- Camera feed(s) must be : HTTP feeds that provide a video stream and a snapshot, or RTSP streams (no snapshot URL needed)
- Camera feeds are responsible for settings such as brightness contrast etc.
- Configuration is via UI - no initial config needed
- Settings are kept in one file next to the log (`system/duetPrintGuard/duetPrintGuard.json`). If the file is damaged it is recreated from the defaults
- ntfy and Pushover titles and messages can be left blank to use system text that reflects the camera and countdown settings
- Logging level can be INFO or DEBUG
- uses dsf-python (lower CPU / network use)
- Automatically selects a port at startup (can be overridden in config)
- Requests fewer DSF permissions (command execution, object model, network and file system access only)
- Swapped out an underlying library. uses about 70% less memory, with a much smaller and faster install
- The detection model is embedded in the plugin - nothing is downloaded at startup
- updated python modules to latest compatible versions
- Camera stream and snapshot URLs are checked when a camera is added
- Detection page shows a live view (up to 10 fps) while a camera is detecting, and a snapshot otherwise. Clicking a camera opens its feed in a new tab, directly from the camera at its full frame rate
- Pages close their camera streams while hidden, to keep connections to the plugin low. Detection carries on in the background
- Each camera has a Detection Sensitivity slider - normal in the middle, less sensitive to the left (far left: almost nothing fails), more sensitive to the right (far right: almost everything fails)
- Majority vote settings, countdown settings and Which Cameras take effect immediately, without restarting detection
- Pause / Resume follows the printer's actual state, and cameras show `Paused` while the print is paused
- Configuration page has a Save button on each card

### Included from 3.6.x

- Added autostart autostop of detection based on printer state
- Failure detection simplified to all / any if multiple cameras
- Many performance improvements to basic operation to reduce CPU load
- Added direct printer control to facilitate remote use (e.g. using Tailscale)
