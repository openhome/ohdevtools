import os
import shlex
import tarfile
import string
import re
import urllib
import urllib2
import platform
import subprocess

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

class Dependency(object):
    def __init__(self, name, remotepath, localpath, configureargs, logfile=None):
        """
        name: A name to identify the dependency in hudson_build.py
        remotepath: The path of the dependency archive
        localpath: The path (relative to source root) to extract the archive
        configureargs: A list of arguments to append to the call to waf configure
        """
        self.name = name
        self.remotepath = remotepath
        self.localpath = localpath
        self.configureargs = configureargs
        self.logfile = default_log(logfile)
    def expand_remote_path(self, env):
        return string.Template(self.remotepath).substitute(env)
    def expand_local_path(self, env):
        return string.Template(self.localpath).substitute(env)
    def expand_configure_args(self, env):
        return [string.Template(arg).substitute(env) for arg in self.configureargs]
    def fetch(self, env):
        remote_path = self.expand_remote_path(env)
        local_path = os.path.abspath(self.expand_local_path(env))
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

class DependencyCollection(object):
    def __init__(self, dependencies, logfile):
        self.dependencies = dependencies
        self.logfile = logfile
    def _filter(self, subset):
        missing_dependencies = [name for name in subset if name not in self.dependencies]
        if len(missing_dependencies) > 0:
            raise Exception("No entries in dependency file named: " + ", ".join(missing_dependencies) + ".")
        return [self.dependencies[name] for name in subset]
    def get_args(self, subset, env):
        dependencies = self._filter(subset)
        configure_args=[d.expand_configure_args(env) for d in dependencies]
        return configure_args
    def fetch(self, subset, env):
        dependencies = self._filter(subset)
        failed_dependencies = []
        for d in dependencies:
            if not d.fetch(env):
                failed_dependencies.append(d.name)
        if failed_dependencies:
            self.logfile.write("Failed to fetch some dependencies: " + ' '.join(failed_dependencies) + '\n')
            return False
        return True

def read_dependencies(dependencyfile, logfile):
    dependencies = {}
    for index, line in enumerate(dependencyfile):
        lineelements = shlex.split(line, comments=True)
        if len(lineelements)==0:
            continue
        if len(lineelements)!=4:
            raise Exception("Bad format in dependencies file, line %s." % (index + 1))
        dependencies[lineelements[0]] = Dependency(
                name=lineelements[0],
                remotepath=lineelements[1],
                localpath=lineelements[2],
                configureargs=shlex.split(lineelements[3]),
                logfile=logfile)
    return DependencyCollection(dependencies, logfile)

def read_dependencies_from_filename(filename, logfile):
    dependencyfile = open(filename, "r")
    try:
        return read_dependencies(dependencyfile, logfile)
    finally:
        dependencyfile.close()

def fetch_dependencies(dependency_filename, dependency_names, env, logfile=None):
    """
    Fetch the specified dependencies.
    Return their concatenated configure arguments.
    """
    logfile = default_log(logfile)
    logfile.write("Required dependencies: " + ' '.join(dependency_names) + '\n')
    dependencies = read_dependencies_from_filename(dependency_filename, logfile)
    missing_dependencies = [name for name in dependency_names if name not in dependencies]
    if len(missing_dependencies) > 0:
        raise Exception("No entries in dependency file named: " + ", ".join(missing_dependencies) + ".")
    configure_args = []
    failed_dependencies = []
    for name in dependency_names:
        if not dependencies[name].fetch(env):
            failed_dependencies.append(name)
        configure_args.extend(dependencies[name].expand_configure_args(env))
    if failed_dependencies:
        logfile.write("Failed to fetch some dependencies: " + ' '.join(failed_dependencies) + '\n')
    return configure_args
