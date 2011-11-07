import os
import shlex
import tarfile
import string

def default_log(logfile=None):
    return logfile if logfile is not None else open(os.devnull, "w")

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
        self.logfile.write("Fetching '%s' from '%s' and unpacking to '%s'... " % (self.name, remote_path, local_path))
        try:
            tar = tarfile.open(remote_path)
        except IOError:
            self.logfile.write("Failed to fetch '%s' from '%s'!" % (self.name, remote_path))
            return False
        try:
            os.makedirs(local_path)
        except OSError:
            # We get an error if the directory exists, which we are happy to
            # ignore. If something worse went wrong, we will find out very
            # soon when we try to extract the files.
            pass
        tar.extractall(local_path)
        tar.close()
        self.logfile.write("Done.\n")
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
