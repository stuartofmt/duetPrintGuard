# duetPrintGuard DWC Plugin

**Uses the detection engine developed by @oliverbravery**

duetPrintGuard offers local, **real-time print failure detection** for 3D printing on edge devices **(e.g. Raspberry Pi)**. It is self contained and does not require external connections or subscriptions.

## Basic Operation

The plugin monitors one or more camera feeds looking for patterns that indicate a possible defect in printing.  During the monitoring, each feed reports either *success* or *failure* using a frame-by-frame analysis.

Each camera feed has separate settings to determine if there is sufficient evidence to report a *defect*.  If the number of continuous failure frames in a given number of frames exceeds the settings for that camera - a *defect* is declared. If one or all camera feeds (depending on settings) declare a defect then a countdown is started and notification(s) are sent out.

At the end of the countdown period, if the user does not intervene, the countdown action (Ignore, Pause, Cancel) is executed.  If the user does intervene then the user's selected action is executed.

## Versions

Documentation for each version - installation, configuration, operation and change notes:

| duetPrintGuard | For DWC / DSF | Documentation | Code |
| --- | --- | --- | --- |
| 2.2 | 3.7 | [docs/2.2](docs/2.2/README.md) - in development | [3.7.x](https://github.com/stuartofmt/duetPrintGuard/tree/3.7.x) branch |
| 2.1 | 3.7 | [docs/2.1](docs/2.1/README.md) | [3.7.x](https://github.com/stuartofmt/duetPrintGuard/tree/3.7.x) branch, release `v2.1.0-dwc3.7` |
| 1.0 | 3.6 | In the [3.6.x](https://github.com/stuartofmt/duetPrintGuard/tree/3.6.x) branch | [3.6.x](https://github.com/stuartofmt/duetPrintGuard/tree/3.6.x) branch |

The 3.7 versions are configured on a Configuration page in the plugin. The 3.6 version uses a `duetPrintGuard.config` file, edited from DWC. All versions have configurable actions when a defect is detected and several notification types (Duet Macro, ntfy, Pushover).

The plugin zip files are on the [releases](https://github.com/stuartofmt/duetPrintGuard/releases) page.

> _The original project can be found [here](https://github.com/oliverbravery/PrintGuard)._
