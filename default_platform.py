import os
import platform


def default_platform():
    if platform.system() == 'Windows':
        if platform.architecture()[0] == '64bit':
            return 'Windows-x64'
        else:
            return 'Windows-x86'
    if platform.system() == 'Linux':
        if platform.architecture()[0] == '32bit':
            if platform.machine()[0:3] == 'ppc':
                return 'Linux-ppc32'
            elif platform.machine() == 'armv7l':
                if os.path.exists('/sys/firmware/devicetree/base/model'):
                    with open('/sys/firmware/devicetree/base/model', 'r') as f:
                        info = f.read()
                    if 'Raspberry Pi' in info:
                        return 'Linux-rpi'
                return 'Linux-armhf'      
            else:
                return 'Linux-x86'
    if platform.system() == 'Linux' and platform.architecture()[0] == '64bit':
        if platform.machine() in ['armv8', 'aarch64']:
            return 'Linux-aarch64'
        else:
            return 'Linux-x64'
    if platform.system() == 'Darwin':
        if platform.machine() == 'arm64':
            return 'Mac-arm64'
        else:
            return 'Mac-x64'
    return None
