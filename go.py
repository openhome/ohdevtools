import commands.fetch_dependencies as fetch
import commands.hudson_build as build
import version
import sys


def main(aArgs):
    version.check_version()
    cmd = None
    args = []
    if len(aArgs) > 1:
        cmd = aArgs[1]
    # if len(aArgs) > 2:
    #     args = aArgs[2:]

    if cmd in ('fetch', 'fetch-dependencies', 'fetch_dependencies'):
        fetch.main()
    elif cmd in ('build', 'ci-build', 'hudson_build'):
        build.hudson_build()
    else:
        print('')
        print('Usage:')
        print('    go fetch: fetch dependencies specified by project')
        print('    go build: perform automated build')
        print('    go <command> --help: display command specific help page')
        print('')


if __name__ == "__main__":
    main(sys.argv)
