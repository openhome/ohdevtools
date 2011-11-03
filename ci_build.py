from optparse import OptionParser
from dependencies import read_dependencies_from_filename
import os
import platform
import sys
import subprocess
import shutil

def get_vsvars_environment():
    """
    Returns a dictionary containing the environment variables set up by vsvars32.bat

    win32-specific
    """
    vs100comntools = os.environ['VS100COMNTOOLS']
    if vs100comntools is None:
        raise Exception("VS100COMNTOOLS is not set in environment.")
    vsvars32 = os.path.join(vs100comntools, 'vsvars32.bat')
    python = sys.executable
    process = subprocess.Popen('("%s">nul)&&"%s" -c "import os; print repr(os.environ)"' % (vsvars32, python), stdout=subprocess.PIPE, shell=True)
    stdout, _ = process.communicate()
    exitcode = process.wait()
    if exitcode != 0:
        raise Exception("Got error code %s from subprocess!" % exitcode)
    return eval(stdout.strip())

def default_platform():
    if platform.system() == 'Windows':
        return 'Windows-x86'
    if platform.system() == 'Linux' and platform.architecture()[0] == '32bit':
        return 'Linux-x86'
    if platform.system() == 'Linux' and platform.architecture()[0] == '64bit':
        return 'Linux-x64'
    return None

def delete_directory(path, logfile=None):
    if logfile is None:
        logfile = open(os.devnull, "w")
    path = os.path.abspath(path)
    logfile.write('Deleting "'+path+'"... ')
    shutil.rmtree(path, ignore_errors=True)
    if os.path.isdir(path):
        logfile.write('\nFailed.\n')
        raise Exception('Failed to delete "%s"' % path)
    logfile.write('\nDone.\n')

class BuildStep(object):
    def __init__(self, name, conditions, action):
        self.name = name
        self.conditions = conditions
        self.action = action
    def test_conditions(self, env):
        return all(key in env and env[key]==value for (key, value) in self.conditions.items())
    def run(self, context):
        return self.action(context)

class BuildContext(object):
    pass

def flatten_string_list(arglist):
    """
    Assemble a list of string, such as for a subprocess call.
    Input should be a string or a list containing only
    strings or similar lists.
    Output will be a list containing only strings.
    """
    if isinstance(arglist, (str, unicode)):
        return [arglist]
    return sum([flatten_string_list(x) for x in arglist], [])

class Builder(object):
    def __init__(self):
        self._steps = []
        self._optionParser = OptionParser()
        #self._context = BuildContext()
    def build_step(self, **conditions):
        """Decorator applied to functions in the build_behaviour file."""
        def decorator_func(f):
            self._steps.append(BuildStep(f.__name__, conditions, f))
            return f
        return decorator_func
    def run(self, argv=None):
        self._context = BuildContext()
        options, args = self._optionParser.parse_args(argv)
        self._context.options = options
        self._context.args = args
        self._context.env = dict(os.environ)
        for step in self._steps:
            if step.test_conditions(self._context.env):
                print step.name
                step.run(self._context)
    def add_bool_option(self, *args, **kwargs):
        kwargs=dict(kwargs)
        kwargs["default"] = False
        kwargs["action"] = "store_true"
        self.add_option(*args, **kwargs)
    def add_option(self, *args, **kwargs):
        self._optionParser.add_option(*args, **kwargs)

    def python(self, *args):
        args = flatten_string_list(args)
        subprocess.check_call([sys.executable] + args, env=self._context.env)
    def shell(self, *args):
        args = flatten_string_list(args)
        subprocess.check_call(args, env=self._context.env, shell=True)
    def rsync(self, *args):
        args = flatten_string_list(args)
        subprocess.check_call(["rsync"] + args)
    def _dependency_collection(self):
        return read_dependencies_from_filename(os.path.join('projectdata', 'dependencies.txt'), logfile=sys.stdout)
    def fetch_dependencies(self, *dependencies, **kwargs):
        dependencies = flatten_string_list(dependencies)
        if 'platform' in kwargs:
            platform = kwargs['platform']
        else:
            platform = self._context.env["PLATFORM"]
        dependency_collection = self._dependency_collection()
        delete_directory(os.path.join('dependencies', platform), logfile=sys.stdout)
        if len(dependencies) > 0:
            dependency_collection.fetch(dependencies, self._context.env)
    def get_dependency_args(self, *dependencies):
        dependencies = flatten_string_list(dependencies)
        dependency_collection = self._dependency_collection()
        return dependency_collection.get_args(dependencies, self._context.env)

class SshSession(object):
    def __init__(self, host, username):
        import paramiko
        self.ssh = paramiko.SSHClient()
        self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self.ssh.connect(host, username=username, look_for_keys='True')
    def call(self, *args):
        stdin, stdout, stderr = self.ssh.exec_command(cmd)
        def pump_output_thread(source, destination):
            for line in source:
                destination.write(line)
                destination.flush()
        stdout_thread = threading.Thread(target=pump_output_thread, args=(stdout, sys.stdout))
        stderr_thread = threading.Thread(target=pump_output_thread, args=(stderr, sys.stderr))
        stdout_thread.start()
        stderr_thread.start()
        stdout_thread.join()
        stderr_thread.join()
        return stdout.channel.recv_exit_status()
    def __call__(self, *args):
        return self.call(*args)
    def __enter__(self):
        return self
    def __exit__(self, ex_type, ex_value, ex_traceback):
        self.ssh.slose()

def run(buildname="build", argv=None):
    builder = Builder()
    behaviour_globals = {
            'fetch_dependencies':builder.fetch_dependencies,
            'get_dependency_args':builder.get_dependency_args,
            'add_option':builder.add_option,
            'add_bool_option':builder.add_bool_option,
            'python':builder.python,
            'shell':builder.shell,
            'rsync':builder.rsync,
            'build_step':builder.build_step,
            'default_platform':default_platform,
            'get_vsvars_environment':get_vsvars_environment,
            'SshSession':SshSession
        }
    execfile(os.path.join('projectdata', buildname+'_behaviour.py'), behaviour_globals)
    builder.run(argv)
