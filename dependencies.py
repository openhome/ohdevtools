import os
import tarfile
import re
import urllib
import urllib2
import platform
import subprocess
import json
import shutil
from glob import glob
from default_platform import default_platform

# Master table of dependency types.

# A dependency definition can specify 'type' to inherit definitions from one of these.
# String values can depend on other string values from the dependency. For example,
# if 'name' is defined as 'Example' then '${name}.exe' will expand to 'Example.exe'.
# It does not matter which order the values are defined.
# String values can also depend on boolean values. For example, the string
# '${test-value?yes-result:no-result}' will get the value of the string named
# 'yes-result' if 'test-value' is a true boolean value, and the string named
# 'no-result' if 'test-value' is a false boolean value.

# The principle string values that must be defined are 'archive-path' to point to the
# .tar.gz file with the dependency's binaries, 'dest' to specify where to untar it,
# and 'configure-args' to specify the list of arguments to pass to waf.

# In order for source control fetching to work, the string 'source-git' should point
# to the git repo and 'tag' should identify the git tag that corresponds to the
# fetched binaries.

DEPENDENCY_TYPES = {
    # Label a dependency with the 'ignore' type to prevent it being considered at all.
    # Can be useful to include comments. (Json has no comment syntax.)
    'ignore' : {
        'ignore': True     # This causes the entire dependency entry to be ignored. Useful for comments.
        },

    # Openhome dependencies generally have an associated git repo to allow us to
    # fetch source code. They also have a different directory layout to accomodate
    # the large number of versions created by CI builds.
    #
    # An openhome dependency, at minimum, must define:
    #     name
    #     version
    #
    # Commonly overridden:
    #     archive-suffix
    #     platform-specific
    #     configure-args
    'openhome' : {
        'archive-extension': '.tar.gz',
        'archive-prefix': '',
        'archive-suffix': '',
        'binary-repo': 'http://openhome.org/releases/artifacts',
        'archive-directory': '${binary-repo}/${name}/',
        'archive-filename': '${archive-prefix}${name}-${version}-${archive-platform}${archive-suffix}${archive-extension}',
        'archive-path': '${archive-directory}${archive-filename}',
        'source-path': '${linn-git-user}@core.linn.co.uk:/home/git',
        'source-git': '${source-path}/${name}.git',
        'tag': '${name}_${version}',
        'any-platform': 'AnyPlatform',
        'platform-specific': True,
        'archive-platform': '${platform-specific?platform:any-platform}',
        'dest': 'dependencies/${archive-platform}/',
        'configure-args': []
        },

    # External dependencies generally don't have a git repo, and even if they do,
    # it won't conform to our conventions.
    #
    # An external dependency, at minimum, must define:
    #     name
    #     archive-filename
    #
    # Commonly overriden:
    #     platform-specific
    #     configure-args
    'external' : {
        'binary-repo': 'http://openhome.org/releases/artifacts',
        'source-git': None,
        'any-platform': 'AnyPlatform',
        'platform-specific': True,
        'archive-platform': '${platform-specific?platform:any-platform}',
        'archive-path': '${binary-repo}/${archive-platform}/${archive-filename}',
        'dest': 'dependencies/${archive-platform}/',
        'configure-args': []
        },
    }









def default_log(logfile=None):
    return logfile if logfile is not None else open(os.devnull, "w")

def windows_program_exists(program):
    return subprocess.call(["which", "/q", program], shell=False)==0

def other_program_exists(program):
    return subprocess.call(["/bin/sh", "-c", "command -v "+program], shell=False, stdout=open(os.devnull), stderr=open(os.devnull))==0

program_exists = windows_program_exists if platform.platform().startswith("Windows") else other_program_exists



def scp(source, target):
    program = None
    for p in ["scp", "pscp"]:
        if program_exists(p):
            program = p
            break
    if program is None:
        raise "Cannot find scp (or pscp) in the path."
    subprocess.check_call([program, source, target])


def open_file_url(url):
    smb = False
    if url.startswith("smb://"):
        url = url[6:]
        smb = True
    elif url.startswith("file://"):
        url = url[7:]
    path = urllib.url2pathname(url).replace(os.path.sep, "/")
    if path[0]=='/':
        if path[1]=='/':
            # file:////hostname/path/file.ext
            # Bad remote path.
            remote = True
            legacy = True
            final_path = path.replace("/", os.path.sep)
        else:
            # file:///path/file.ext
            # Good local path.
            remote = False
            legacy = False
            if smb:
                raise Exception("Bad smb:// path")
            final_path = path[1:].replace("/", os.path.sep)
    else:
        # file://hostname/path/file.ext
        # Good remote path.
        remote = True
        legacy = False
        final_path = "\\\\" + path.replace("/", os.path.sep)
    if smb and (legacy or not remote):
        raise Exception("Bad smb:// path. Use 'smb://hostname/path/to/file.ext'")
    if (smb or remote) and not platform.platform().startswith("Windows"):
        raise Exception("SMB file access not supported on non-Windows platforms.")
    return open(final_path, "rb")

def get_opener_for_path(path):
    if path.startswith("file:") or path.startswith("smb:"):
        return open_file_url
    if re.match("[^\W\d]{2,8}:", path):
        return urllib2.urlopen
    return lambda fname: open(fname, mode="rb")


class EnvironmentExpander(object):
    # template_regex matches 
    template_regex = re.compile(r"""
        (?x)                                # Enable whitespace and comments
        (?P<dollar>\$\$)|                   # Match $$
        (?P<word>\$[a-zA-Z_][a-zA-Z_0-9]*)| # Match $word
        (?P<parens>\$\{[^}]*\})             # Match ${any-thing}
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
        if isinstance(value, (str, unicode)):
            return self.template_regex.sub(self.replacematch, value)
        elif isinstance(value, (list, tuple)):
            return [self._expandvalue(x) for x in value]
        elif isinstance(value, dict):
            return dict((k, self.expandvalue(v)) for (k,v) in value.items())
        return value
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
        if '?' in key:
            return self.expandconditional(key)
        return self.expand(key)
    def expandconditional(self, key):
        if '?' not in key:
            raise ValueError('conditional must be of form ${condition?result:alternative}')
        condition, rest = key.split('?', 1)
        if ':' not in rest:
            raise ValueError('conditional must be of form ${condition?result:alternative}')
        primary, alternative = rest.split(':', 1)
        condition, primary, alternative = [x.strip() for x in [condition, primary, alternative]]
        conditionvalue = self.expand(condition)
        if conditionvalue:
            return self.expand(primary)
        return self.expand(alternative)

class Dependency(object):
    def __init__(self, name, environment, logfile=None):
        self.expander = EnvironmentExpander(environment)
        self.logfile = default_log(logfile)
    def fetch(self):
        remote_path = self.expander.expand('archive-path')
        local_path = os.path.abspath(self.expander.expand('dest'))
        self.logfile.write("Fetching '%s'\n  from '%s'\n" % (self.name, remote_path))
        try:
            opener = get_opener_for_path(remote_path)
            remote_file = opener(remote_path)
            tar = tarfile.open(name=remote_path, fileobj=remote_file, mode="r|*")
        except IOError:
            self.logfile.write("  FAILED\n")
            return False
        try:
            os.makedirs(local_path)
        except OSError:
            # We get an error if the directory exists, which we are happy to
            # ignore. If something worse went wrong, we will find out very
            # soon when we try to extract the files.
            pass
        self.logfile.write("  unpacking to '%s'\n" % (local_path,))
        tar.extractall(local_path)
        tar.close()
        remote_file.close()
        self.logfile.write("  OK\n")
        return True
    @property
    def name(self):
        return self['name']
    def __getitem__(self, key):
        return self.expander.expand(key)
    def __contains__(self, key):
        return key in self.expander
    def checkout(self):
        name = self['name']
        sourcegit = self['source-git']
        if sourcegit is None:
            self.logfile.write('No git repo defined for {0}.\n'.format(name))
            return False
        self.logfile.write("Fetching source for '%s'\n  into '%s'\n" % (name, os.path.abspath('../'+name)))
        tag = self['tag']
        try:
            if not os.path.exists('../'+name):
                self.logfile.write('  git clone {0} {1}\n'.format(sourcegit, name))
                subprocess.check_call(['git', 'clone', sourcegit, name], cwd='..', shell=True)
            elif not os.path.isdir('../'+name):
                self.logfile.write('Cannot checkout {0}, because directory ../{0} already exists\n'.format(name))
                return False
            else:
                self.logfile.write('  git fetch origin\n')
                subprocess.check_call(['git', 'fetch', 'origin'], cwd='../'+name, shell=True)
            self.logfile.write("  git checkout {0}\n".format(tag))
            subprocess.check_call(['git', 'checkout', tag], cwd='../'+name, shell=True)
        except subprocess.CalledProcessError as cpe:
            self.logfile.write(str(cpe)+'\n')
            return False
        return True
    def expand_remote_path(self):
        return self.expander.expand('archive-path')
    def expand_local_path(self):
        return self.expander.expand('dest')
    def expand_configure_args(self):
        return self.expander.expand('configure-args')


class DependencyCollection(object):
    def __init__(self, env, logfile=None):
        self.logfile = default_log(logfile)
        self.base_env = env
        self.dependency_types = DEPENDENCY_TYPES
        self.dependencies = {}
    def create_dependency(self, dependency_definition):
        defn = dependency_definition
        env = {}
        env.update(self.base_env)
        if 'type' in defn:
            dep_type = defn['type']
            env.update(self.dependency_types[dep_type])
        env.update(defn)
        if 'ignore' in env and env['ignore']:
            return
        if 'name' not in env:
            raise ValueError('Dependency definition contains no name')
        name = env['name']
        new_dependency = Dependency(name, env, logfile=self.logfile)
        self.dependencies[name] = new_dependency
    def __getitem__(self, key):
        return self.dependencies[key]
    def _filter(self, subset=None):
        if subset is None:
            return self.dependencies.values()
        missing_dependencies = [name for name in subset if name not in self.dependencies]
        if len(missing_dependencies) > 0:
            raise Exception("No entries in dependency file named: " + ", ".join(missing_dependencies) + ".")
        return [self.dependencies[name] for name in subset]
    def get_args(self, subset=None):
        dependencies = self._filter(subset)
        configure_args=sum((d.expand_configure_args() for d in dependencies), [])
        return configure_args
    def fetch(self, subset=None):
        dependencies = self._filter(subset)
        failed_dependencies = []
        for d in dependencies:
            if not d.fetch():
                failed_dependencies.append(d.name)
        if failed_dependencies:
            self.logfile.write("Failed to fetch some dependencies: " + ' '.join(failed_dependencies) + '\n')
            return False
        return True
    def checkout(self, subset=None):
        dependencies = self._filter(subset)
        failed_dependencies = []
        for d in dependencies:
            if not d.checkout():
                failed_dependencies.append(d.name)
        if failed_dependencies:
            self.logfile.write("Failed to check out some dependencies: " + ' '.join(failed_dependencies) + '\n')
            return False
        return True

def read_json_dependencies(dependencyfile, env, logfile):
    collection = DependencyCollection(env, logfile=logfile)
    dependencies = json.load(dependencyfile)
    for d in dependencies:
        collection.create_dependency(d)
    return collection

def read_json_dependencies_from_filename(filename, env, logfile):
    dependencyfile = open(filename, "r")
    try:
        return read_json_dependencies(dependencyfile, env, logfile)
    finally:
        dependencyfile.close()

def cli(args):
    if platform.system() != "Windows":
        args = ["mono", "--runtime=v4.0.30319"] + args
    subprocess.check_call(args, shell=False)

def clean_dir(dirname):
    if os.path.isdir(dirname):
        try:
            shutil.rmtree(dirname)
        except Exception as e:
            raise Exception("Failed to remove directory. Try closing applications that might be using it. (E.g. Visual Studio.)\n"+str(e))

def fetch_dependencies(dependency_names=None, platform=None, env=None, fetch=True, nuget=True, clean=True, source=False, logfile=None):
    '''
    Fetch all the dependencies defined in projectdata/dependencies.json and in
    projectdata/packages.config.
    platform:
        Name of target platform. E.g. 'Windows-x86', 'Linux-x64', 'Mac-x64'...
    env:
        Extra variables referenced by the dependencies file.
    fetch:
        True to fetch the listed dependencies, False to skip.
    nuget:
        True to fetch nuget packages listed in packages.config, False to skip.
    clean:
        True to clean out directories before fetching, False to skip.
    source:
        True to fetch source for the listed dependencies, False to skip.
    logfile:
        File-like object for log messages.
    '''
    if env is None:
        env = {}
    if platform is not None:
        env['platform'] = platform
    if 'platform' not in env:
        platform = env['platform'] = default_platform()
    if platform is None:
        raise Exception('Platform not specified and unable to guess.')
    if clean:
        if fetch:
            clean_dir('dependencies/AnyPlatform')
            clean_dir('dependencies/'+platform)
        if nuget:
            clean_dir('dependencies/nuget')
    dependencies = read_json_dependencies_from_filename('projectdata/dependencies.json', env=env, logfile=logfile)
    if fetch:
        dependencies.fetch(dependency_names)
    if nuget:
        nuget_exe = os.path.normpath(list(glob('dependencies/AnyPlatform/NuGet.[0-9]*/NuGet.exe'))[0])
        cli([nuget_exe, 'install', 'projectdata/packages.config', '-OutputDirectory', 'dependencies/nuget'])
    if source:
        dependencies.checkout(dependency_names)
    return dependencies


