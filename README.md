Here's what changes for a user going from 3.6.x to 3.7.x.

**Setup and configuration**
- **No configuration file to prepare.** In 3.6.x you copied `duetPrintGuard.config.example`, then entered the printer's IP address and a port. 3.7.x starts with working defaults and finds the printer by itself.
- **A new Configuration UI** covers the port, logging, printer commands, macro, ntfy and Pushover. Cameras and the countdown are on the Settings UI.
- **The port is chosen automatically** unless you set one, and the Configuration UI shows which port is in use.
- **Settings survive damage:** a corrupted settings file is reset to defaults automatically, instead of stopping the plugin from starting.

**Cameras**
- **Cameras are network feeds only:** HTTP cameras (with a stream and a snapshot address) or RTSP cameras. USB cameras plugged into the Pi are no longer supported directly; use multiCam or similar to share them as network feeds.
- **Brightness, contrast and focus** are set on the camera feed itself, not in the plugin.
- **Adding a camera checks it works:** if the stream or snapshot address is wrong, it isn't added, and you're told which address failed.

**Detection**
- **Detection Sensitivity slider per camera:** normal in the middle, more sensitive to the right, less to the left. It replaces the old Sensitivity setting.
- **Changes apply immediately:** vote settings, countdown settings and "Which Cameras" take effect without restarting detection.
- **All cameras keep watching during a countdown,** so any camera that also sees the failure shows DEFECT too.

**When a defect is found**
- **Pause, Resume and Cancel follow the printer's real state,** including when the print was paused from DWC or by the countdown.
- **While a print is paused, cameras show "Paused",** and detection restarts automatically when you resume.
- **Notifications can use automatic text:** leave the ntfy or Pushover title or message blank to get a message that names the camera and the countdown action.
- **Notifications retry briefly** if the network drops out, so a passing Wi-Fi glitch doesn't lose an alert.

**The UIs**
- **A new look matching DWC,** with Detection, Settings and Configuration tabs, following DWC's light or dark theme.
- **Live view while detecting:** a camera that is detecting shows its live picture (up to 10 frames a second); otherwise it shows a snapshot.
- **Clicking a camera opens its full-rate feed in a new tab.**
- **UIs go quiet when you're not looking at them,** so camera feeds and connections are only used while a UI is on screen. Detection carries on regardless.

**Install and performance**
- **Uses about 70% less memory,** with a much smaller and faster install.
- **Works offline:** the detection model ships with the plugin, so nothing is downloaded when it starts.

**Unchanged from 3.6.x:**
- autostart and autostop of detection with the print;
- the defect countdown with its Ignore, Pause and Cancel actions;
- majority-vote detection;
- the Any or All camera choice;
- direct printer control from the plugin UI.