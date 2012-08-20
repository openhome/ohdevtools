#!/bin/env python

# This script fetches the dependencies listed in the file
# "projectdata/dependencies.json"

from ci_build import default_platform
from optparse import OptionParser
import dependencies
import getpass
import sys
import traceback

description = "Fetch ohWidget dependencies from the Internet."
command_group = "Developer tools"
command_synonyms = ["fetch", "fetch-dependencies"]

def main():
    usage = "usage: %prog [options] [dependency...]\n\nFetches named dependencies."
    parser = OptionParser(usage=usage)
    parser.add_option('--linn-git-user', default=None, help='Username to use when connecting to core.linn.co.uk.')
    parser.add_option('--clean', action="store_true", default=False, help="Clean out the dependencies directory.")
    parser.add_option('--all', action="store_true", default=False, help="Fetch all regular dependencies.")
    parser.add_option('--nuget', action="store_true", default=False, help="Fetch all nuget dependencies.")
    parser.add_option('--source', action="store_true", default=False, help="Fetch source for listed dependencies.")
    parser.add_option('-v', '--verbose', action="store_true", default=False, help="Report more information on errors.")
    parser.add_option('--platform', default=None, help='Target platform.')
    options, args = parser.parse_args()
    if len(args)==0 and not options.clean and not options.nuget and not options.all and not options.source:
        print "No dependencies were specified. Default to:"
        print "    go fetch --clean --all --nuget"
        print "[Yn]?",
        answer = raw_input().strip().upper()
        if answer not in ["","Y","YES"]:
            sys.exit(1)
        options.clean = True
        options.all = True
        options.nuget = True
    platform = options.platform or default_platform()
    linn_git_user = options.linn_git_user or getpass.getuser()
    try:
        dependencies.fetch_dependencies(
                dependency_names=None if options.all else args,
                platform=platform,
                env={'linn-git-user':linn_git_user},
                nuget=options.nuget and not args,
                clean=options.clean and not args,
                fetch=(options.all or bool(args)) and not options.source,
                source=options.source,
                logfile=sys.stdout)
    except Exception as e:
        if options.verbose:
            traceback.print_exc()
        else:
            print e
        sys.exit(1)
    '''
    dependencies = read_json_dependencies_from_filename('projectdata/dependencies.json', env={
        'linn-git-user':linn_git_user,
        'platform':platform}, logfile=sys.stdout)
    try:
        dependencies.fetch(args or None)
    except Exception as e:
        print e
    '''

if __name__ == "__main__":
    main()
