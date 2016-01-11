import platform

def default_platform():
    if platform.system() == 'Windows':      # Note ALL windows environment treated as 32-bit
        return 'Windows-x86'
    if platform.system() == 'Linux' and platform.architecture()[0] == '32bit' and platform.machine()[0:3] == 'ppc':
        return 'Linux-ppc32'
    if platform.system() == 'Linux' and platform.architecture()[0] == '32bit':
        if platform.machine() == 'armv7l':
            return 'Linux-armhf'
        else:
            return 'Linux-x86'
    if platform.system() == 'Linux' and platform.architecture()[0] == '64bit':
        return 'Linux-x64'
    if platform.system() == 'Darwin':
        if platform.architecture()[0] == '32bit':
            return 'Mac-x86'
        if platform.architecture()[0] == '64bit':
            return 'Mac-x64'
    return None
