# Notice and acknowledgments

canvas-harness is created by **Jeffrey Lai** and released under the
[MIT License](LICENSE). If you use, copy or adapt it, keep the copyright
notice in `LICENSE`. A mention such as "based on canvas-harness by Jeffrey Lai"
in your README is appreciated.

## What this repository contains

All code in this repository is original to canvas-harness. It bundles
**no third-party code or libraries**: the Python code uses only the Python
standard library.

The Claude Code guard hooks in `.claude/hooks/` were adapted from Jeffrey
Lai's own agent operating-system specification and are covered by the same
MIT License.

## Software and services it works with (not included here)

Each of these is used through its public interface. None is distributed with
this repository, and each remains under its own license and terms.

| project | owner | how canvas-harness uses it | license / terms |
|---|---|---|---|
| [Python](https://www.python.org/) and its standard library | Python Software Foundation | runtime for the CLI and hooks | [PSF License](https://docs.python.org/3/license.html) |
| [Canvas LMS](https://github.com/instructure/canvas-lms) and its [REST API](https://canvas.instructure.com/doc/api/) | Instructure, Inc. | the API this tool sends requests to | Canvas LMS is AGPL-3.0; API use is subject to your institution's Canvas terms |
| [Claude Code](https://www.anthropic.com/claude-code) | Anthropic | the agent harness that runs the skills and hooks | [Anthropic terms](https://www.anthropic.com/legal) |
| [Google Chrome](https://www.google.com/chrome/) / [Chromium](https://www.chromium.org/) | Google / The Chromium Authors | optional headless rendering for `canvas-harness pdf` | Chrome: Google terms; Chromium: BSD-3-Clause and others |

## Development

Parts of this project were written with the help of Claude (Anthropic) through
Claude Code. Commits made that way are marked `Co-Authored-By: Claude`.

## Trademarks

Canvas and Instructure are trademarks of Instructure, Inc. Claude is a
trademark of Anthropic, PBC. Chrome is a trademark of Google LLC.
canvas-harness is an independent project and is not affiliated with, endorsed
by, or sponsored by any of them.
