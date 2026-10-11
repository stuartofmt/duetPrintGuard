# Release notes

## 1.0.0

This is the initial release for DWC 3.7.x

### Changes from 3.6.x

- Uses DWC 3.7.x plugin APIs
- Changed UI to match Duet3d DWC style
- Removed inbuilt camera support
- Requires connection to camera feed(s): HTTP(s) feeds that provide a video stream and a snapshot, or RTSP streams (no snapshot URL needed)
- Camera feeds are responsible for settings such as brightness contrast etc.
- Configuration is via UI - no initial config needed
- uses dsf-python (lower CPU / network use)
- Automatically selects a port at startup (can be overridden in config)

### Included from 3.6.x

- Added autostart autostop of detection based on printer state
- Failure detection simplified to all / any if multiple cameras
- Many performance improvements to basic operation to reduce CPU load
- Added direct printer control to facilitate remote use (e.g. using Tailscale)
