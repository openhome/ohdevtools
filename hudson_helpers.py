import platform
import subprocess
import os
import sys
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


class BuildBehaviour(object):
    def __init__(
            self,
            prebuild = None,
            postbuild = None,
            wipe_dependencies = True,
            dependencies_to_copy = (),
            run_configure = True,
            custom_test_func = None,
            extra_configure_args = (),
            env = {}):
        self.prebuild = prebuild if prebuild is not None else lambda env: None
        self.postbuild = postbuild if postbuild is not None else lambda env: None
        self.wipe_dependencies = wipe_dependencies
        self.dependencies_to_copy = dependencies_to_copy
        self.should_run_configure = run_configure
        self.custom_test_func = custom_test_func
        self.extra_configure_args = extra_configure_args
        self.env = env

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
