# duetPrintGuard 2.1 – change notes

What changed since the 3.6 version (duetPrintGuard 1.0.0, for DWC / DSF 3.6), described by what it does rather than how the code does it. This is the work for the 3.7.x branch (DWC / DSF 3.7).

## At a glance

- **No setup file.** duetPrintGuard starts with working defaults and finds the printer by itself. Everything is set on the pages.
- **Runs without an SBC.** With a standalone board, it runs on another computer on the network, Linux or Windows. The plugin still needs an SBC.
- **New pages.** The pages are Detection, Settings, Configuration and Log, with the DWC look and DWC's light or dark theme, in English, French, German or Spanish.
- **Network cameras only.** Cameras are HTTP (stream and snapshot) or RTSP feeds. Brightness, contrast and focus are set on the camera feed.
- **Better detection controls.** Each camera has a sensitivity slider, and detection settings take effect at once.
- **Lighter.** It uses about 70% less memory, installs faster and works offline.

### What you need to do

- **Share USB or Pi cameras as network feeds.** Use multiCam or a similar camera server.
- **Enter your settings again.** There's no configuration file to copy. Set the printer and alerts on the Configuration page, and add the cameras on the Settings page.
- **Use Python 3.11 or later** when running it without an SBC.

## Installing and running

- **The plugin** asks DSF for fewer permissions: running commands, the object model, the network and its own files.
- **Standalone boards.** duetPrintGuard runs on another computer and connects to the board over the network. `run.sh` (Linux) and `run.bat` (Windows) set everything up and start it. They run it without a console, so it's stopped with the **Terminate the Program** button on the Detection page. `run.sh console` or `run.bat console` runs it in the terminal, showing its messages.
- **Windows** is supported, including Python from the Microsoft Store.
- **Opens the pages.** When run without the plugin, it opens its pages in the default browser at startup. This can be turned off.
- **Port.** A free port is chosen at startup unless one is set. The Configuration page shows the port in use.
- **Settings folder.** The settings and log are kept with the program if that folder can be written to. Otherwise, on Windows, they go in `%APPDATA%\duetPrintGuard`, or `Documents\duetPrintGuard` with Python from the Microsoft Store. A folder can also be given when starting it. The folder in use is logged at startup.
- **Works offline.** The detection model comes with duetPrintGuard, so nothing is downloaded when it starts.
- **Smaller and faster.** A smaller detection library uses about 70% less memory and makes the install much smaller and faster.
- **Python 3.11 or later.** `requirements1.txt` lists the package versions that work, with a section for each Python version.

## Settings

- **Set on the pages.** There's no configuration file to prepare. The Configuration page has General, Actions and Alerts tabs: the printer connection, port, logging, printer commands, macro, ntfy and Pushover. Cameras and the countdown are on the Settings page.
- **One Save** saves every tab. A tab with a setting that wasn't accepted is marked in red, and the page switches to it.
- **Passwords and keys** are hidden, with an eye button to show them. This covers the Pushover keys.
- **Settings survive damage.** The settings file has a checksum. If it's damaged, it's recreated with the defaults instead of stopping duetPrintGuard from starting.
- **Logging** is INFO or DEBUG.

## Cameras

- **Network feeds only.** HTTP cameras need a stream and a snapshot address. RTSP cameras need only the stream.
- **Checked when added.** If the stream or snapshot address doesn't work, the camera isn't added, and you're told which address failed.
- **Live view.** A camera that's detecting shows its live picture, up to 10 frames a second. Otherwise it shows a snapshot.
- **Full-rate feed.** Clicking a camera opens its feed in a new tab, straight from the camera.

## Detection

- **Sensitivity slider for each camera.** Normal is in the middle, more sensitive to the right and less to the left. It replaces the old Sensitivity setting.
- **Vote settings shown as a share.** The vote window slider comes first. The threshold slider runs up to the window, and shows the share of frames that must show a failure, for example "3 of 5 (60%)".
- **Changes apply at once.** Vote settings, countdown settings and Which Cameras take effect without restarting detection.
- **All cameras keep watching during a countdown,** so any other camera that sees the failure also shows DEFECT.

## When a defect is found

- **Pause, Resume and Cancel follow the printer's real state,** including a pause from DWC or from the countdown.
- **Paused prints.** While a print is paused, the cameras show "Paused". Detection starts again when the print is resumed.
- **Automatic alert text.** Leave the ntfy or Pushover title or message blank to get one that names the camera and the countdown action.
- **Alerts in the pages' language.** The automatic alert text, and the Paused, Resumed and Cancelled messages shown on the printer, are in the language the pages use. A title or message you set is sent as it is.
- **Alerts retry briefly** if the network drops, so a short Wi-Fi glitch doesn't lose an alert.

## The pages

- **Look.** The pages match DWC and follow its light or dark theme.
- **Languages.** English, French, German and Spanish. The language comes from the browser, or from `?lang=` in the address.
- **Printer banner.** While the printer isn't connected, every page shows why, whether it's retrying, and fields for the printer's address, port and password with **Save and connect**.
- **Quiet when hidden.** A page closes its camera feeds while it isn't on screen, so fewer connections are used. Detection carries on.
- **No-cameras prompt.** With no cameras set up, the Detection page asks you to add one, once the printer is connected.
- **Log page.** Shows the log as it's written. **Follow** keeps the newest line in view. There's a filter, reload, and a download of the whole file.

## Printer communication

- **Three ways to reach the printer,** found automatically: through DSF on the same computer (the plugin), or over the network to an SBC or a standalone board.
- **Changes are pushed with an SBC.** DSF sends printer changes as they happen, instead of duetPrintGuard asking every few seconds.

## Logging

- **Startup log.** From the start, messages go to the console and to `duetPrintGuard.startup.log` in the program's folder, which is new at each start. An early exit is recorded even with no console. Once the startup checks are done, logging switches to `duetPrintGuard.log`, which starts with what the startup log holds.
- **The end of a defect countdown** is logged at INFO, with the action taken.
- **Cameras by name.** Starting and stopping detection is logged with the cameras' names instead of their IDs.

## Unchanged from the 3.6 version

- Detection starts and stops by itself with the print.
- The defect countdown, with its Ignore, Pause and Cancel actions.
- Majority-vote detection.
- The Any or All camera choice.
- Printer control from the pages.

## Code structure

- **Style.** `.editorconfig` and `setup.cfg` (pycodestyle) are the same as duetLapse3's. The Python code uses 4-space indents and passes pycodestyle.
- **Releases** use the shared DWC-Tools workflow through `scripts/release.sh`. A version with a suffix (for example `-beta.1`) is a pre-release.
