#!/bin/env python

# This script is specific to Linn's network environment. It copies the
# Smarties dependencies from a known location on the network into the
# dependencies folder. After running this, you should be able to run
# "waf configure" and it should detect all the dependencies.

# If you are building Smarties without access to the Linn network, you
# are responsible for building or downloading the dependencies and
# either placing them in the dependencies folder or specifying their
# locations elsewhere when you invoke "waf configure".

from ci_build import run
from sys import argv

description = "Fetch ohWidget dependencies from a network share."
command_group = "Developer tools"
command_synonyms = ["fetch", "fetch-dependencies"]

def main():
    run("build", ["--fetch-only"] + argv[1:])

if __name__ == "__main__":
    main()
