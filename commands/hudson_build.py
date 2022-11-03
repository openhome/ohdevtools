#!/usr/bin/env python

# Build script invoked by our Hudson build server to perform our continuous integration builds.
#
# Fetches dependencies from a network share, then configures, builds and tests ohwidget.
#
# Run with --help to list arguments.
#
# You can run this on a developer machine, but you may need to help the script find the
# network share by using the -a argument.

from ci_build import run
import sys


def hudson_build():
    buildname = "build"
    if len(sys.argv) >= 3:
        if not sys.argv[2].startswith("-"):
            buildname = sys.argv[2]
            sys.argv[2:] = sys.argv[3:]
    run(buildname, sys.argv[2:])
