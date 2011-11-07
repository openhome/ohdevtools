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
    def __init__(self, name, action):
        self.name = name
        self.condition_sets = []
        self.is_optional = False
        self.is_enabled_by_default = True
        self.action = action
    def add_conditions(self, condition_set):
        self.condition_sets.append(condition_set)
    def set_default(self, enabled_by_default):
        self.is_enabled_by_default = enabled_by_default
    def set_optional(self, optional):
        self.is_optional = optional
    def test_conditions(self, env):
        if len(self.condition_sets) == 0:
            return True
        for conditions in self.condition_sets:
            if all(key in env and env[key]==value for (key, value) in conditions.items()):
                return True
        return False
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

def process_kwargs(func_name, kwarg_dict, defaults_dict):
    result = dict(defaults_dict)
    for key, value in kwarg_dict.items():
        if key in result:
            result[key] = value
        else:
            raise TypeError("{0}() got an unexpected keyword argument '{1}'".format(func_name, key))
    return result

class Builder(object):
    def __init__(self):
        self._steps = []
        self._optionParser = OptionParser()
        self._enabled_options = set()
        self._disabled_options = set()
        self._disable_all_options = False
        #self._context = BuildContext()
    def build_condition(self, name=None, **conditions):
        """Decorator applied to functions in the build_behaviour file."""
        def decorator_func(f):
            if not hasattr(f, "buildstep"):
                f.buildstep = BuildStep(name or f.__name__, f)
                self._steps.append(f.buildstep)
            f.buildstep.add_conditions(conditions)
            return f
        return decorator_func
    def build_step(self, name=None, optional=False, default=True):
        def decorator_func(f):
            if not hasattr(f, "buildstep"):
                f.buildstep = BuildStep(f.__name__, f)
                self._steps.append(f.buildstep)
            if name is not None:
                f.buildstep.name = name
            f.buildstep.set_optional(optional)
            f.buildstep.set_default(default)
            return f
        return decorator_func
    def get_optional_steps(self):
        return (step.name for step in self._steps if self.is_optional)
    def select_optional_steps(self, *args, **kwargs):
        kwargs = process_kwargs(
            "select_optional_steps",
            kwargs,
            {"disable_others":False})
        if kwargs["disable_others"]:
            self._enabled_options.clear()
            self._disable_all_options = True
        for name in args:
            if name.startswith("+"):
                name = name[1:]
                self._disabled_options.discard(name)
                self._enabled_options.add(name)
            elif name.startswith("-"):
                name = name[1:]
                self._enabled_options.discard(name)
                self._disabled_options.add(name)

    def run(self, argv=None):
        self._context = BuildContext()
        options, args = self._optionParser.parse_args(argv)
        self._context.options = options
        self._context.args = args
        self._context.env = dict(os.environ)
        for step in self._steps:
            if step.test_conditions(self._context.env):
                enabled = True
                if step.is_optional:
                    enabled = step.is_enabled_by_default
                    if self._disable_all_options:
                        enabled = False
                    if step.name in self._enabled_options:
                        enabled = True
                    if step.name in self._disabled_options:
                        enabled = False
                if enabled:
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
        kwargs = process_kwargs(
            "fetch_dependencies",
            kwargs,
            {"platform":None})
        dependencies = flatten_string_list(dependencies)
        platform = kwargs['platform'] or self._context.env["PLATFORM"]
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
        stdin, stdout, stderr = self.ssh.exec_command(args)
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
        self.ssh.close()

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
            'build_condition':builder.build_condition,
            'default_platform':default_platform,
            'get_vsvars_environment':get_vsvars_environment,
            'SshSession':SshSession,
            'select_optional_steps':builder.select_optional_steps
        }
    execfile(os.path.join('projectdata', buildname+'_behaviour.py'), behaviour_globals)
    builder.run(argv)
