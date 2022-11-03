#!/bin/env python

# This script fetches the dependencies listed in the file
# "projectdata/dependencies.json"

from __future__ import print_function
from ci_build import default_platform
from optparse import OptionParser
import dependencies
import getpass
import sys
import traceback

usage = """
usage: %prog [options] [dependency...]

Fetches named dependencies.

Dependencies are defined in projectdata/dependencies.json.
Overrides are defined in ../dependency_overrides.json.
A typical overrides file might look like this:

[
    {
        "name": "ohOs.App.V1",
        "archive-path": "../ohOs2/build/packages/ohOs.App.V1-AnyPlatform-${titlecase-debugmode}.zip"
    }
]

See 'ohDevTools/dependencies.py' for details.

""".strip()


def main():
    parser = OptionParser(usage=usage)
    parser.add_option('--linn-git-user', default=None, help='Username to use when connecting to core.linn.co.uk.')
    parser.add_option('--clean', action="store_true", default=False, help="Clean out the dependencies directory.")
    parser.add_option('--all', action="store_true", default=False, help="Fetch all regular dependencies.")
    parser.add_option('--source', action="store_true", default=False, help="Fetch source for listed dependencies.")
    parser.add_option('--release', action="store_const", const="Release", dest="debugmode", default="Release", help="")
    parser.add_option('--debug', action="store_const", const="Debug", dest="debugmode", default="Release", help="")
    parser.add_option('-v', '--verbose', action="store_true", default=False, help="Report more information in errors and for --list.")
    parser.add_option('--platform', default=None, help='Target platform.')
    parser.add_option('-l', '--list', action="store_true", default=False, help="Don't fetch anything, just list all dependencies.")
    parser.add_option('--no-overrides', action="store_true", default=False, help="Don't process ../dependency_overrides.json for local overrides.")
    options, args = parser.parse_args(sys.argv[2:])     # offset by 1 as routine called indirectly from 'go'
    if len(args) == 0 and not options.clean and not options.all and not options.source and not options.list:
        options.all = True
        print("No dependencies were specified. Default to:")
        print("    go fetch --all")
        inp = input("[Yn]? ")
        answer = inp.strip().upper()
        if answer not in ['', 'Y', 'YES', 'y', 'yes']:
            sys.exit(1)
    platform = options.platform or default_platform()
    linn_git_user = options.linn_git_user or getpass.getuser()
    try:
        dependencies.fetch_dependencies(
            dependency_names=None if options.all else args,
            platform=platform,
            env={'linn-git-user': linn_git_user,
                 'debugmode': options.debugmode,
                 'titlecase-debugmode': options.debugmode.title()},
            clean=options.clean and not args,
            fetch=(options.all or bool(args)) and not options.source,
            source=options.source,
            list_details=options.list,
            verbose=options.verbose,
            local_overrides=not options.no_overrides)
    except Exception as e:
        if options.verbose:
            traceback.print_exc()
        else:
            print(e)
        sys.exit(1)
