from optparse import OptionParser
from dependencies import read_dependencies_from_filename
import os
import platform
import threading
import sys
import subprocess
import shutil
import time
import ctypes
import datetime

VERSION = 5

DEFAULT_STEPS = "default"
ALL_STEPS = "all"
ILLEGAL_STEP_NAMES = [DEFAULT_STEPS, ALL_STEPS]

class BaseUserLock(object):
    def __init__(self, filename):
        self.filename = filename
        self.locktime = None
    def __enter__(self):
        dirname = os.path.split(os.path.abspath(self.filename))[0]
        if not os.path.exists(dirname):
            os.makedirs(dirname)
        while True:
            if self.tryacquire(self.filename):
                break
            print "Lockfile "+self.filename+" not available."
            print "Wait 30s..."
            time.sleep(30.0)
        self.locktime = datetime.datetime.now()
        print "Lock acquired at "+str(self.locktime)
    def __exit__(self, etype, einstance, etraceback):
        self.release()
        unlocktime = datetime.datetime.now()
        print "Lock released at "+str(unlocktime)
        print "Lock was held for "+str(unlocktime - self.locktime)

class WindowsUserLock(BaseUserLock):
    def __init__(self, name):
        BaseUserLock.__init__(self, os.environ["APPDATA"]+"\\openhome-build\\"+name+".lock")
    def tryacquire(self, filename):
        self.handle = ctypes.windll.kernel32.CreateFileA(filename,7,0,0,2,0x04000100,0)
        return self.handle != -1
    def release(self):
        ctypes.windll.kernel32.CloseHandle(self.handle)

class PosixUserLock(BaseUserLock):
    def __init__(self, name):
        BaseUserLock.__init__(self, os.environ["HOME"]+"/.openhome-build/"+name+".lock")
    def tryacquire(self, filename):
        import fcntl
        self.f = file(filename, "w")
        try:
            fcntl.lockf(self.f, fcntl.LOCK_EX)
            return True
        except IOError:
            self.f.close()
            return False
    def release(self):
        self.f.close()

def userlock(name):
    '''
    Acquire a lock scoped to the local user. Only one build at a time can run
    with the given name per user per machine. While waiting for the lock, prints
    a notice to stdout every 30s.
    '''
    if platform.system() == 'Windows':
        return WindowsUserLock(name)
    return PosixUserLock(name)

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
        if name in ILLEGAL_STEP_NAMES:
            fail("'{0}' is not allowed as a build step name.".format(name))
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

def flatten_comma_list(arglist):
    return sum([s.split(",") for s in arglist], [])

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
        self.add_bool_option("-v", "--verbose")
        self._enabled_options = set()
        self._disabled_options = set()
        self._disable_all_options = False
        self._enable_all_options = False
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
    def specify_optional_steps(self, *steps):
        '''
        Specify which optional steps to include in the build.
        "default" includes all default steps.
        "all" includes all steps.
        "foo" or "+foo" includes step foo.
        "-foo" excludes step foo, even if "default" or "all" is present.
        '''
        steps = flatten_string_list(steps)
        steps = flatten_comma_list(steps)
        self._enable_all_options = ALL_STEPS in steps
        #self._enable_default_options = DEFAULT_STEPS in steps
        self._disable_all_options = DEFAULT_STEPS not in steps
        self._disabled_options = set(s[1:] for s in steps if s.startswith("-"))
        self._enabled_options = set(s[1:] for s in steps if s.startswith("+"))
        self._enabled_options = self._enabled_options.union(
                s for s in steps if s[0] not in "+-")
    def modify_optional_steps(self, *steps):
        '''
        Add or remove optional steps in the build.
        "+foo" include step foo.
        "-foo" exclude step foo.
        '''
        for name in steps:
            if name.startswith("+"):
                name = name[1:]
                self._disabled_options.discard(name)
                self._enabled_options.add(name)
            elif name.startswith("-"):
                name = name[1:]
                self._enabled_options.discard(name)
                self._disabled_options.add(name)
            else:
                raise TypeError("Each step must be a string beginning with '+' or '-'.")

    def select_optional_steps(self, *args, **kwargs):
        '''
        Deprecated. Use specify_optional_steps or modify_optional_steps instead.
        '''
        kwargs = process_kwargs(
            "select_optional_steps",
            kwargs,
            {"disable_others":False})
        if kwargs["disable_others"]:
            self._enabled_options.clear()
            self._disable_all_options = True
        args = flatten_string_list(args)
        args = flatten_comma_list(args)
        self.modify_optional_steps(*args)

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

    def _check_call(self, *args, **kwargs):
        if self._context.options.verbose:
            argstring = [", ".join([repr(arg) for arg in args])]
            kwargstring = [", ".join(["%s=%r" % (k,v) for (k,v) in kwargs.items()])]
            print "subprocess.check_call(%s)" % (", ".join(argstring+kwargstring))
        subprocess.check_call(*args, **kwargs)

    def python(self, *args, **kwargs):
        args = flatten_string_list(args)
        self._check_call([sys.executable] + args, env=self._context.env, **kwargs)
    def shell(self, *args, **kwargs):
        args = flatten_string_list(args)
        self._check_call(args, env=self._context.env, shell=True, **kwargs)
    def rsync(self, *args, **kwargs):
        args = flatten_string_list(args)
        self._check_call(["rsync"] + args, **kwargs)
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
            if not dependency_collection.fetch(dependencies, self._context.env):
                raise AbortRunException()
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
    def call(self, *args, **kwargs):
        stdin, stdout, stderr = self.ssh.exec_command(*args, **kwargs)
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

class AbortRunException(Exception):
    def __init__(self, message="Aborted due to error.", exitcode=1):
        Exception.__init__(self, message)
        self.message = message
        self.exitcode = exitcode

def fail(*args, **kwargs):
    '''
    fail(message, exitcode=1)
    Abort the build with an error message.
    '''
    raise AbortRunException(*args, **kwargs)

def require_version(required_version):
    '''Fail if the version of ohDevTools is too old.'''
    if VERSION<required_version:
        fail("This build requires a newer version of ohDevTools. You have version {0}, but need version {1}.".format(VERSION, required_version),32)

def windows_program_exists(program):
    return subprocess.call(["where", "/q", program], shell=False)==0

def other_program_exists(program):
    nul = open(os.devnull, "w")
    return subprocess.call(["/bin/sh", "-c", "command -v "+program], shell=False, stdout=nul, stderr=nul)==0

program_exists = windows_program_exists if platform.platform().startswith("Windows") else other_program_exists

def scp(*args):
    program = None
    for p in ["scp", "pscp"]:
        if program_exists(p):
            program = p
            break
    if program is None:
        raise "Cannot find scp (or pscp) in the path."
    subprocess.check_call([program] + list(args))

def run(buildname="build", argv=None):
    builder = Builder()
    import ci
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
            'select_optional_steps':builder.select_optional_steps,
            'modify_optional_steps':builder.modify_optional_steps,
            'specify_optional_steps':builder.specify_optional_steps,
            'userlock':userlock,
            'fail':fail,
            'scp':scp,
            'require_version':require_version
        }
    for name, value in behaviour_globals.items():
        setattr(ci, name, value)
    try:
        execfile(os.path.join('projectdata', buildname+'_behaviour.py'), dict(behaviour_globals))
        builder.run(argv)
    except AbortRunException as e:
        print e.message
        sys.exit(e.exitcode)
    for name in behaviour_globals.keys():
        delattr(ci, name)
