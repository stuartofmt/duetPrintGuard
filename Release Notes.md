# Release notes


## 1.0.0
This is the initial release for DWC 3.7.x

*Changes from 3.6.x*
- Uses DWC 3.7.x plugin APIs
- Changed UI to match Duet3d DWC style
- Removed inbuilt camera support
- Requires connection to HTTP(s) feed(s) that provide a video stream and snapshot
- Camera feeds are responsible for settings such as brightness contrast etc.
- Configuration is via UI - no initial config needed
- uses dsf-python (lower CPU / network use)
- AUtomatically selects a port at startup (can be overridden in config)

*Included from 3.6.x*
- Added autostart autostop of detection based on printer state
- Failure detection simplified to all / any if multiple cameras
- Many performance improvements to basic operation to reduce CPU load 
- Added direct printer control to facilitate remote use (e.g. using Tailscale)
