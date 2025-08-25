''' Common utilities used by Jenkins builder scripts'''
import aws
import os
import platform
import subprocess

kVcVars = 'C:\\Program Files\\Microsoft Visual Studio\\2022\\Professional\\VC\\Auxiliary\\Build\\vcvars32.bat'


def fetch(*args):
    if 'Windows' in platform.system():
        cmd = [os.path.abspath('go.bat'), 'fetch']
    else:
        cmd = [os.path.abspath('go'), 'fetch']
    cmd.extend(args)
    print(f'\n{cmd}')
    subprocess.check_call(cmd)


def waf(*args):
    cmd = ['python', os.path.abspath('waf')]
    cmd.extend(args)
    print(f'\n{cmd}')
    subprocess.check_call(cmd)


def awsCopy(src, dst):
    if 's3://' in dst:
        print(f'Upload {src} to AWS {dst}')
    elif 's3://' in src:
        print(f'Download AWS {src} to {dst}')
    else:
        print(f'Copy {src} to {dst}')
    aws.copy(src, dst)        


def setupEnv(target):
    if 'Windows' in platform.system():
        print(f'\nSetting up VC using {kVcVars}')
        if os.path.isfile(kVcVars):
            arch = 'x86' if 'x86' in target else 'x64'
            process = subprocess.Popen(f'("{kVcVars}" {arch} > nul) && python -c "import os; print(os.environ)"', stdout=subprocess.PIPE, shell=True)
            stdout, _ = process.communicate()
            exitcode = process.wait()
            if exitcode == 0:
                print('\n\nEnvironment:')
                envVars = eval(stdout.decode('utf8').strip('environ'))
                for e in envVars:
                    print(f'    {e}: {envVars[e]}')
                    os.environ[e] = envVars[e]

