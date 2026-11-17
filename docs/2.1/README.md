# duetPrintGuard 2.1

duetPrintGuard offers local, **real-time print failure detection** for 3D printing on Duet3D printers. It watches one or more camera feeds, and when a defect is found it sends alerts and, after a countdown, can pause or cancel the print. It uses the detection engine developed by @oliverbravery, and runs on edge devices such as a Raspberry Pi, with no external connections or subscriptions.

This is the documentation for duetPrintGuard 2.1, for DWC / DSF 3.7 ([other versions](../../README.md#versions)). It runs as a DWC plugin on an SBC (for example, a Raspberry Pi), with its own pages in DWC. It can also run on another computer for a standalone board - see [Standalone boards](Installation-Configuration.md#standalone-boards).

- [Installation and configuration](Installation-Configuration.md) - installing the plugin, running without an SBC, cameras, detection and defect settings, the Configuration page
- [Basic operation](Basic-Operation.md) - the Detection page, the defect countdown and autostart
- [Change notes](change-notes.md) - what changed since the 3.6 version

Code: the [3.7.x](https://github.com/stuartofmt/duetPrintGuard/tree/3.7.x) branch, release [v2.1.0-dwc3.7](https://github.com/stuartofmt/duetPrintGuard/releases/tag/v2.1.0-dwc3.7).
