import os
import tarfile
import zipfile
import re
import requests
import platform
import subprocess
import json
import shutil
import io
import tempfile
from default_platform import default_platform
import deps_cross_checker
import aws

# Master table of dependency types.

# A dependency definition can specify 'type' to inherit definitions from one of these.
# String values can depend on other string values from the dependency. For example,
# if 'name' is defined as 'Example' then '${name}.exe' will expand to 'Example.exe'.
# It does not matter which order the values are defined.
# String values can also depend on boolean values. For example, the string
# '${test-value?yes-result:no-result}' will get the value of the string named
# 'yes-result' if 'test-value' is a true boolean value, and the string named
# 'no-result' if 'test-value' is a false boolean value.
# Finally, string values can also depend on a lookup table defined as a JSON object.
# For example, given these definitions:
# {
#     "servertable":{
#         "Windows":"windows.openhome.org",
#         "Linux":"linux.openhome.org",
#         "*":"openhome.org"
#     },
#     "server":"${servertable[$system]}"
# }
# If 'system' is defined as 'Windows', then 'server' will be defined as
# 'windows.openhome.org'. The '*' entry is the default: if a lookup fails the default
# will be used instead.

# The principle string values that must be defined are 'archive-path' to point to the
# .tar.gz file with the dependency's binaries, 'dest' to specify where to untar it,
# and 'configure-args' to specify the list of arguments to pass to waf.

# In order for source control fetching to work, the string 'source-git' should point
# to the git repo and 'tag' should identify the git tag that corresponds to the
# fetched binaries.

DEPENDENCY_TYPES = {
    # Ignore dependencies
    #   - ignored - effectively 'comments' out entire dependency
    'ignore': {
        'ignore': True
    },

    # Openhome dependencies 
    #   - (legacy name - basically means that they are publicly visible and available)
    #   - generally have an associated git repo to allow us to fetch source code.
    #   - stored on AWS in the linn-artifacts-public bucket
    #
    # At a minimum must define:
    #     name
    #     version
    'openhome': {
        'archive-extension': '.tar.gz',
        'archive-prefix': '',
        'archive-suffix': '',
        'binary-repo': 's3://linn-artifacts-public/artifacts',
        'archive-directory': '${binary-repo}/${name}/',
        'archive-filename': '${archive-prefix}${name}-${version}-${archive-platform}${archive-suffix}${archive-extension}',
        'remote-archive-path': '${archive-directory}${archive-filename}',
        'use-local-archive': False,
        'archive-path': '${use-local-archive?local-archive-path:remote-archive-path}',
        'source-path': '${linn-git-user}@core.linn.co.uk:/home/git',
        'repo-name': '${name}',
        'source-git': '${source-path}/${repo-name}.git',
        'tag': '${repo-name}_${version}',
        'any-platform': 'AnyPlatform',
        'platform-specific': True,
        'host-platform': default_platform(),
        'archive-platform': '${platform-specific?platform:any-platform}',
        'dest': 'dependencies/${archive-platform}/',
        'configure-args': []
    },

    # Internal dependencies 
    #   - ony visible and available inside Linn
    #   - stored on AWS in the linn-artifacts-private bucket
    #
    # At a minimum must define:
    #     name
    #     version
    'internal': {
        'binary-repo': 's3://linn-artifacts-private',
        'source-git': None,
        'any-platform': 'AnyPlatform',
        'platform-specific': True,
        'archive-suffix': '',
        'archive-filename': '${name}-${version}-${platform}${archive-suffix}.tar.gz',
        'archive-platform': '${platform-specific?platform:any-platform}',
        'archive-path': '${binary-repo}/${name}/${archive-filename}',
        'host-platform': default_platform(),
        'dest': 'dependencies/${archive-platform}/',
        'configure-args': []
    },

    # External dependencies
    # 
    #   - publicly visible and available
    #   - no git repo that conforms to 'openhome standard'
    #   - stored on AWS in the linn-artifacts-public bucket
    #
    # At a minimum must define:
    #     name
    #     archive-filename
    'external': {
        'binary-repo': 's3://linn-artifacts-public/artifacts',
        'source-git': None,
        'any-platform': 'AnyPlatform',
        'platform-specific': True,
        'archive-platform': '${platform-specific?platform:any-platform}',
        'archive-path': '${binary-repo}/${archive-platform}/${archive-filename}',
        'host-platform': default_platform(),
        'dest': 'dependencies/${archive-platform}/',
        'configure-args': []
    },
}


class FileFetcher(object):

    def __init__(self):
        pass

    def fetch(self, path):
        if path.startswith("file:") or path.startswith("smb:"):
            raise Exception("FETCH: File URLs deprecated")
        elif path.startswith("s3:"):
            return self.fetch_aws(path)
        elif re.match(r"[^\W\d]{2,8}:", path):
            raise Exception("FETCH: Legacy URLs no longer re-routed")
        return self.fetch_local(path)

    @staticmethod
    def fetch_aws(awspath):
        print('  from AWS %s' % awspath)
        temppath = tempfile.mktemp( suffix='.tmp' )
        try:
            aws.copy(awspath, temppath)
            return temppath
        except:
            raise Exception("FETCH: Unable to retrieve %s from AWS" % awspath)
            return None

    @staticmethod
    def fetch_local(path):
        print( '  from LOCAL PATH %s' % path)
        return path


class EnvironmentExpander(object):
    # template_regex matches
    template_regex = re.compile(r"""(?x)    # Enable whitespace and comments
        (?P<dollar>\$\$)|                   # Match $$
        (?P<word>\$[a-zA-Z_][a-zA-Z_0-9]*)| # Match $word
        (?P<parens>\$\{[^}]*\})             # Match ${any-thing}
        """)
    # Matches foo[bar]
    index_regex = re.compile(r"""(?x)       # Enable whitespace and comments
        ^                                   # Match only at start of string
        ([^][]*)                            # Match table name (no brackets allowed)
        \[                                  # Match one open bracket: [
        ([^][]*)                            # Match key (no brackets allowed)
        \]                                  # Match one close bracket: ]
        $
        """)

    def __init__(self, env_dict):
        self.env_dict = env_dict
        self.cache = {}
        self.expandset = set()

    def __getitem__(self, key):
        return self.expand(key)

    def getraw(self, key):
        return self.env_dict[key]

    def __contains__(self, key):
        return key in self.env_dict

    def keys(self):
        return self.env_dict.keys()

    def values(self):
        return [self.expand(key) for key in self.keys()]

    def items(self):
        return [(key, self.expand(key)) for key in self.keys()]

    def expand(self, key):
        if key in self.cache:
            return self.cache[key]
        if key in self.expandset:
            raise ValueError("Recursive expansion for key:", key)
        self.expandset.add(key)
        result = self._expand(key)
        self.cache[key] = result
        self.expandset.remove(key)
        return result

    def _expand(self, key):
        if key not in self.env_dict:
            raise KeyError("Key undefined:", key)
        value = self.env_dict[key]
        return self._expandvalue(value)

    def _expandvalue(self, value):
        if isinstance(value, ("".__class__, u"".__class__)):
            return self.expandstring(value)
            # return self.template_regex.sub(self.replacematch, value)
        elif isinstance(value, (list, tuple)):
            return [self._expandvalue(x) for x in value]
        elif isinstance(value, dict):
            return dict((k, self._expandvalue(v)) for (k, v) in value.items())
        return value

    def expandstring(self, value):
        firstmatch = self.template_regex.match(value)
        if firstmatch is not None and firstmatch.group(0) == value and value != "$$":
            # Special case: The entire string is a single expansion. In this case,
            # we allow the expansion to be *anything* (bool, int, list...),
            # not just a string.
            return self.replacematch(firstmatch)
        return self.template_regex.sub(self.replacematch, value)

    def replacematch(self, match):
        if match.group('dollar'):
            return '$'
        key = None
        if match.group('word'):
            key = match.group('word')[1:]
        if match.group('parens'):
            key = match.group('parens')[2:-1]
        assert key is not None
        key = key.strip()
        if '[' in key:
            return self.expandlookup(key)
        if '?' in key:
            return self.expandconditional(key)
        return self.expand(key)

    def expandlookup(self, key):
        match = self.index_regex.match(key)
        if match is None:
            raise ValueError('lookup must be of form ${table[key]}')
        tablename = match.group(1).strip()
        keyname = match.group(2).strip()
        table = self.expand(tablename)
        if keyname.startswith('$'):
            key = self.expand(keyname[1:])
        else:
            key = keyname
        if not isinstance(table, dict):
            raise ValueError("lookup table must expand to a JSON object (got {0!r} instead)".format(table))
        if not isinstance(key, ("".__class__, u"".__class__)):
            raise ValueError("lookup index must expand to a JSON string (got {0!r} instead)".format(key))
        if key not in table:
            if '*' in table:
                return table['*']
            raise KeyError("Key not in table, and no default '*' entry found: key={0!r}\ntable={1!r}".format(key, table))
        return table[key]

    def expandconditional(self, key):
        if '?' not in key:
            raise ValueError('conditional must be of form ${condition?result:alternative}')
        condition, rest = key.split('?', 1)
        if ':' not in rest:
            raise ValueError('conditional must be of form ${condition?result:alternative}')
        primary, alternative = rest.split(':', 1)
        condition, primary, alternative = [x.strip() for x in [condition, primary, alternative]]
        try:
            conditionvalue = self.expand(condition)
        except KeyError:
            conditionvalue = False
        if self.is_trueish(conditionvalue):
            return self.expand(primary)
        return self.expand(alternative)

    @staticmethod
    def is_trueish(value):
        if hasattr(value, "upper"):
            value = value.upper()
        return value in [1, "1", "YES", "Y", "TRUE", "ON", True]


class Dependency(object):

    def __init__(self, name, environment, fetcher, has_overrides=False):
        self.expander = EnvironmentExpander(environment)
        self.has_overrides = has_overrides
        self.fetcher = fetcher

    def fetch(self):
        remote_path = self.expander.expand('archive-path')
        local_path = os.path.abspath(self.expander.expand('dest'))
        fetched_path = None

        print("\nFetching '%s'" % self.name)
        try:
            fetched_path = self.fetcher.fetch(remote_path)
            statinfo = os.stat(fetched_path)
            if not statinfo.st_size:
                os.unlink(fetched_path)
                print("  **** WARNING - failed to fetch %s ****" % os.path.basename(remote_path))
                return False
        except IOError:
            print("  **** FAILED ****")
            return False

        try:
            os.makedirs(local_path)
        except OSError:
            # We get an error if the directory exists, which we are happy to
            # ignore. If something worse went wrong, we will find out very
            # soon when we try to extract the files.
            pass

        print("  unpacking to '%s'" % (local_path,))
        if os.path.splitext(remote_path)[1].upper() in ['.ZIP', '.NUPKG', '.JAR']:
            self.unzip(fetched_path, local_path)
        else:
            self.untar(fetched_path, local_path)

        if fetched_path:
            if fetched_path != remote_path:
                os.unlink(fetched_path)
        print("OK")
        return True

    @property
    def name(self):
        return self['name']

    def __getitem__(self, key):
        return self.expander.expand(key)

    def __contains__(self, key):
        return key in self.expander

    def items(self):
        return self.expander.items()

    def checkout(self):
        name = self['name']
        sourcegit = self['source-git']
        if sourcegit is None:
            print('No git repo defined for {0}'.format(name))
            return False
        print("Fetching source for '%s'\n  into '%s'" % (name, os.path.abspath('../' + name)))
        tag = self['tag']
        try:
            if not os.path.exists('../' + name):
                print('  git clone {0} {1}'.format(sourcegit, name))
                subprocess.check_call(['git', 'clone', sourcegit, name], cwd='..', shell=False)
            elif not os.path.isdir('../' + name):
                print('Cannot checkout {0}, because directory ../{0} already exists'.format(name))
                return False
            else:
                print('  git fetch origin')
                subprocess.check_call(['git', 'fetch', 'origin'], cwd='../' + name, shell=False)
            print("  git checkout {0}".format(tag))
            subprocess.check_call(['git', 'checkout', tag], cwd='../' + name, shell=False)
        except subprocess.CalledProcessError as cpe:
            print(str(cpe))
            return False
        return True

    @staticmethod
    def untar(source, dest):
        tf = tarfile.open(source, 'r')
        for f in tf:
            try:
                tf.extract(f.name, path=dest)
            except IOError:
                os.unlink( os.path.join(dest, f.name ))
                tf.extract(f.name, path=dest)
        tf.close()

    @staticmethod
    def unzip(source, dest):
        zf = zipfile.ZipFile(source, mode='r')
        zf.extractall(path=dest)
        zf.close()

    def expand_remote_path(self):
        return self.expander.expand('archive-path')

    def expand_local_path(self):
        return self.expander.expand('dest')

    def expand_configure_args(self):
        return self.expander.expand('configure-args')


class DependencyCollection(object):

    def __init__(self, env):
        fetcher = FileFetcher()
        self.base_env = env
        self.dependency_types = DEPENDENCY_TYPES
        self.dependencies = {}
        self.fetcher = fetcher

    def create_dependency(self, dependency_definition, overrides={}):
        defn = dependency_definition
        env = {}
        env.update(self.base_env)
        if 'type' in defn:
            dep_type = defn['type']
            env.update(self.dependency_types[dep_type])
        else:
            # default to an 'external' dependency type if none specified
            dep_type = 'external'
            env.update(self.dependency_types[dep_type])
        env.update(defn)
        env.update(overrides)
        if 'name' not in env:
            raise ValueError('Dependency definition contains no name')
        name = env['name']
        new_dependency = Dependency(name, env, self.fetcher, has_overrides=len(overrides) > 0)
        if 'ignore' in new_dependency and new_dependency['ignore']:
            return
        self.dependencies[name] = new_dependency

    def __contains__(self, key):
        return key in self.dependencies

    def __getitem__(self, key):
        return self.dependencies[key]

    def items(self):
        return self.dependencies.items()

    def _filter(self, subset=None):
        if subset is None:
            return self.dependencies.values()
        missing_dependencies = [name for name in subset if name not in self.dependencies]
        if len(missing_dependencies) > 0:
            raise Exception("No entries in dependency file named: " + ", ".join(missing_dependencies) + ".")
        return [self.dependencies[name] for name in subset]

    def get_args(self, subset=None):
        dependencies = self._filter(subset)
        configure_args = sum((d.expand_configure_args() for d in dependencies), [])
        return configure_args

    def fetch(self, subset=None):
        dependencies = self._filter(subset)
        failed_dependencies = []
        filename = self.fetched_deps_filename(dependencies)
        fetched_deps = self.load_fetched_deps(filename)
        for d in dependencies:
            do_fetch = True
            name = ''
            path = ''
            dest = ''
            if 'name' in d.expander:
                name = d.expander.expand('name')
            if 'archive-path' in d.expander:
                path = d.expander.expand('archive-path')
                if 'latest' in path.lower():
                    # substitute highest numbered number
                    del(d.expander.cache['archive-path'])
                    d.expander.env_dict['archive-path'] = self.substitute_latest(path)
            if 'dest' in d.expander:
                dest = d.expander.expand('dest')
            lookup = dest.rstrip( '/' ) + '/' + name
            version = os.path.basename(path)
            if lookup in fetched_deps:
                if fetched_deps[lookup] == version:
                    print("Skipping fetch of %s as unchanged (%s)" % (name, version))
                    do_fetch = False
            if do_fetch:
                if not d.fetch():
                    failed_dependencies.append(d.name)
                else:
                    fetched_deps[lookup] = version
            if filename:
                self.save_fetched_deps(filename, fetched_deps)
        if failed_dependencies:
            print("Failed to fetch some dependencies: " + ' '.join(failed_dependencies))
            return False
        return True
    
    @staticmethod
    def substitute_latest(path):

        def by_version(arg):
            val = 0
            try:
                fields = arg.split('-')
                for field in fields:
                    if field[0] in '0123456789':
                        break
                ver = field.split('.')
                val = 1e8 * int(ver[0]) + 1e4 * int(ver[1]) + int(ver[2])
            except:
                pass
            return val

        matches = []
        dir, base = os.path.split(path)
        pattern = base.replace('latest', '.*')
        files = aws.ls(dir)
        for f in files:
            base_name = os.path.basename(f)
            if re.fullmatch(pattern, base_name):
                matches.append(base_name)
        matches.sort(reverse=True, key=by_version)
        # return f'{dir}/{matches[0]}'  not supported by Jenkins version of python
        return dir + '/' + matches[0]
    
    @staticmethod
    def fetched_deps_filename(deps):
        filename = None
        for d in deps:
            if 'dest' in d.expander:
                filename = os.path.join(d.expander.expand('dest').split('/')[0], 'loadedDeps.json')
                break
        return filename

    def load_fetched_deps(self, filename):
        loaded_deps = {}
        if filename and os.path.isfile(filename):
            try:
                f = open(filename, 'rt')
                loaded_deps = json.load(f)
                f.close()
            except:
                print("Error with current fetched dependency file: %s" % filename)
        return loaded_deps

    @staticmethod
    def save_fetched_deps(filename, deps):
        f = open(filename, 'wt')
        json.dump(deps, f)
        f.close()

    def checkout(self, subset=None):
        dependencies = self._filter(subset)
        failed_dependencies = []
        for d in dependencies:
            if not d.checkout():
                failed_dependencies.append(d.name)
        if failed_dependencies:
            print("Failed to check out some dependencies: " + ' '.join(failed_dependencies))
            return False
        return True


def read_json_dependencies(dependencyfile, overridefile, env):
    collection = DependencyCollection(env)
    dependencies = json.load(dependencyfile)
    overrides = json.load(overridefile)
    overrides_by_name = dict((dep['name'], dep) for dep in overrides)
    for d in dependencies:
        name = d['name']
        override = overrides_by_name.get(name, {})
        collection.create_dependency(d, override)
    return collection


def read_json_dependencies_from_filename(dependencies_filename, overrides_filename, env):
    try:
        dependencyfile = open(dependencies_filename, "r")
        with open(dependencies_filename) as dependencyfile:
            if overrides_filename is not None and os.path.isfile(overrides_filename):
                with open(overrides_filename) as overridesfile:
                    return read_json_dependencies(dependencyfile, overridesfile, env)
            else:
                return read_json_dependencies(dependencyfile, io.StringIO(u'[]'), env)
    except (OSError, IOError) as e:
        if e.errno != 2:
            raise
        return DependencyCollection(env)


def clean_dirs(dir):
    """Remove the specified directory tree - don't remove anything if it would fail"""
    if os.path.isdir( dir ):
        locked = []
        for dirName, _subdirList, fileList in os.walk(dir):
            for fileName in fileList:
                filePath = os.path.join(dirName, fileName)
                try:
                    if not os.path.islink( filePath ):
                        openAtt = 'r'
                        if platform.system().lower() == 'windows':
                            openAtt = 'a'
                        f = open(filePath, openAtt)
                        f.close()
                except:
                    locked.append(filePath)
        if locked:
            for f in locked:
                print('Locked file:- ', f)
            raise Exception('Failed to clean dependencies\n')
        else:
            shutil.rmtree(dir)


def fetch_dependencies(dependency_names=None, platform=None, env=None, fetch=True, clean=True, source=False, list_details=False, local_overrides=True, verbose=False):
    '''
    Fetch all the dependencies defined in projectdata/dependencies.json and in
    projectdata/packages.config.
    platform:
        Name of target platform. E.g. 'Windows-x86', 'Linux-x64', 'Mac-x64'...
    env:
        Extra variables referenced by the dependencies file.
    fetch:
        True to fetch the listed dependencies, False to skip.
    clean:
        True to clean out directories before fetching, False to skip.
    source:
        True to fetch source for the listed dependencies, False to skip.
    '''
    if env is None:
        env = {}

    if platform is not None:
        env['platform'] = None
        fName = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'platforms.txt')
        f = open(fName, 'rt')
        supported = f.readlines()
        f.close()
        for entry in supported:
            if platform in entry:
                env['platform'] = platform
        if not env['platform']:
            raise Exception('Platform not supported (%s) - see %s for list of supported platforms' % (platform, fName))
    if 'platform' not in env:
        platform = env['platform'] = default_platform()
    if '-' in platform:
        env['system'], env['architecture'] = platform.split('-', 2)
    if platform is None:
        raise Exception('Platform not specified and unable to guess.')

    if clean and not list_details:
        try:
            os.unlink('dependencies/loadedDeps.json')
        except:
            pass
        clean_dirs('dependencies')

    overrides_filename = '../dependency_overrides.json' if local_overrides else None
    dependencies = read_json_dependencies_from_filename('projectdata/dependencies.json', overrides_filename, env=env)
    if list_details:
        for name, dependency in dependencies.items():
            print("Dependency '{0}':".format(name))
            print("    fetches from:     {0!r}".format(dependency['archive-path']))
            print("    unpacks to:       {0!r}".format(dependency['dest']))
            print("    local override:   {0}".format("YES (see '../dependency_overrides.json')" if dependency.has_overrides else 'no'))
            if verbose:
                print("    all keys:")
                for key, value in sorted(dependency.items()):
                    print("        {0} = {1!r}".format(key, value))
            print("")
    else:
        if fetch:
            if not dependencies.fetch(dependency_names):
                raise Exception("Failed to load requested dependencies")

        if source:
            dependencies.checkout(dependency_names)

    # Finally perform cross-check of (major.minor) dependency versions to ensure that these are in sync
    # across this (current) repo and all its pulled-in dependencies. Done as totally seperate operation
    # to isolate from the main fetcher code to assist with any future maintenance
    if not clean:
        xcheck = deps_cross_checker.DepsCrossChecker( platform )
        result = xcheck.execute()
        if result != 0:
            raise Exception( 'Failed: dependency cross-checker detected problem(s)' )

    return dependencies
