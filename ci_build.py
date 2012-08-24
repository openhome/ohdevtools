from optparse import OptionParser
from dependencies import read_json_dependencies_from_filename
import dependencies
import os
import platform
import threading
import sys
import subprocess
import shutil
import getpass
from userlocks import userlock
from default_platform import default_platform as _default_platform

# The version number of the API. Incremented whenever there
# are new features or bug fixes.
VERSION = 13

# The earliest API version that we're still compatible with.
# Changed only when a change breaks an existing API.
BACKWARD_VERSION = 13

DEFAULT_STEPS = "default"
ALL_STEPS = "all"
ILLEGAL_STEP_NAMES = [DEFAULT_STEPS, ALL_STEPS]


def get_vsvars_environment():
    """
    Returns a dictionary containing the environment variables set up by vsvars32.bat

    win32-specific
    """
    # Note:
    # This is 32-bit specific. It won't work if we want to use the 64-bit tools.
    # Sadly VC/bin/amd64/vcvars64.bat doesn't exist on a basic VS Express install.
    # Our best bet might be to invoke VCVarsQueryRegistry.bat and then assemble
    # PATH manually based on FrameworkDir64 and whatever other tools we need to
    # use.
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

def default_platform(fail_on_unknown=True):
    p = _default_platform()
    if p is None and fail_on_unknown:
        fail('No platform specified and unable to guess.')
    return p

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

NOT_SPECIFIED = object()
class CaseInsensitiveEnvironmentCopy(dict):
    def __contains__(self, key):
        return dict.__contains__(self, key.upper())
    def __getitem__(self, key):
        return dict.__getitem__(self, key.upper())
    def __setitem__(self, key, value):
        return dict.__setitem__(self, key.upper(), value)
    def __init__(self, *args):
        if len(args)==0:
            dict.__init__(self)
        elif len(args)==1:
            dict.__init__(self, [(k.upper(), v) for (k,v) in args[0].items()])
        else:
            raise ValueError()
    def get(self, key, default=None):
        return dict.get(self, key.upper(), default)
    def has_key(self, key):
        return dict.has_key(self, key.upper())
    def pop(self, key, *args):
        return dict.pop(self, key.upper(), *args)
    def setdefault(self, key, *args):
        return dict.setdefault(self, key.upper(), *args)
    def update(self, *args, **kwargs):
        if len(args)==0:
            primary={}
        elif len(args)==1:
            primary=CaseInsensitiveEnvironmentCopy(args[0])
        else:
            raise ValueError()
        secondary=CaseInsensitiveEnvironmentCopy(kwargs)
        return dict.update(self, primary, **secondary)

# This is the same mechanism Python uses to decide if os.environ is case-
# sensitive:
if os.name in ['nt', 'os2']:
    EnvironmentCopy = CaseInsensitiveEnvironmentCopy
else:
    EnvironmentCopy = dict



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
        self._context.env = EnvironmentCopy(os.environ)
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
        kwargs.setdefault('shell', True)
        kwargs.setdefault('env', self._context.env)
        self._check_call(args, **kwargs)
    def cli(self, *args, **kwargs):
        args = flatten_string_list(args)
        if platform.system() != "Windows":
            args = ["mono", "--runtime=v4.0.30319"] + args
        kwargs.setdefault('shell', False)
        kwargs.setdefault('env', self._context.env)
        self._check_call(args, **kwargs)
    def rsync(self, *args, **kwargs):
        args = flatten_string_list(args)
        self._check_call(["rsync"] + args, **kwargs)
    def _dependency_collection(self, env):
        return read_json_dependencies_from_filename(os.path.join('projectdata', 'dependencies.json'), env, logfile=sys.stdout)
    def _process_dependency_args(self, *selected, **kwargs):
        kwargs = process_kwargs(
            "fetch_dependencies",
            kwargs,
            {"env":None},)
        selected = flatten_string_list(selected)
        env = dict(kwargs['env'] or {})
        if "platform" not in env:
            env['platform'] = self._context.env["OH_PLATFORM"]
        if "linn-git-user" not in env:
            env['linn-git-user'] = getpass.getuser()
        return selected, env
    def fetch_dependencies(self, *selected, **kwargs):
        selected, env = self._process_dependency_args(*selected, **kwargs)
        try:
            dependencies.fetch_dependencies(
                    selected or None, platform=self._context.env["OH_PLATFORM"], env=env,
                    fetch=True, nuget=True, clean=True, source=False, logfile=sys.stdout )
        except Exception as e:
            print e
            raise AbortRunException()
    def read_dependencies(self, *selected, **kwargs):
        selected, env = self._process_dependency_args(*selected, **kwargs)
        return self._dependency_collection(env)
    def fetch_source(self, *selected, **kwargs):
        selected, env = self._process_dependency_args(*selected, **kwargs)
        dependency_collection = self._dependency_collection(env)
        return dependency_collection.checkout(selected)
    def get_dependency_args(self, *selected, **kwargs):
        selected, env = self._process_dependency_args(*selected, **kwargs)
        dependency_collection = self._dependency_collection(env)
        return dependency_collection.get_args(selected)


class SshConnection(object):
    def __init__(self, stdin, stdout, stderr):
        def pump_output_thread(source, destination):
            for line in source:
                destination.write(line)
                destination.flush()
        self.stdin = stdin
        self.stdout = stdout
        self.stderr = stderr
        self.stdout_thread = threading.Thread(target=pump_output_thread, args=(stdout, sys.stdout))
        self.stderr_thread = threading.Thread(target=pump_output_thread, args=(stderr, sys.stderr))
        self.stdout_thread.start()
        self.stderr_thread.start()
    def send(self, data):
        self.stdin.write(data)
        self.stdin.flush()
    def join(self):
        self.stdout_thread.join()
        self.stderr_thread.join()
        return self.stdout.channel.recv_exit_status()


class SshSession(object):
    def __init__(self, host, username):
        import paramiko
        self.ssh = paramiko.SSHClient()
        self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self.ssh.connect(host, username=username, look_for_keys='True')
    def call(self, *args, **kwargs):
        stdin, stdout, stderr = self.ssh.exec_command(*args, **kwargs)
        conn = SshConnection(stdin, stdout, stderr)
        return conn.join()
    def call_async(self, *args, **kwargs):
        stdin, stdout, stderr = self.ssh.exec_command(*args, **kwargs)
        return SshConnection(stdin, stdout, stderr)
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
    if required_version<BACKWARD_VERSION:
        fail("This build requires an older version of ohDevTools. You have version {0}, but need version {1}.".format(VERSION, required_version),32)

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
            'read_dependencies':builder.read_dependencies,
            'get_dependency_args':builder.get_dependency_args,
            'add_option':builder.add_option,
            'add_bool_option':builder.add_bool_option,
            'python':builder.python,
            'shell':builder.shell,
            'cli':builder.cli,
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
