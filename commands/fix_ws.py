import sys
import os
import re
import shutil
from optparse import OptionParser

description = "Re-write files to change line-endings and/or indentation."
command_group = "Developer tools"

# State machine for analysing text files
class LineEndingMachine(object):
    def checklineend(self, ch):
        if ch=="\r":
            return True, "", self.cr
        if ch=="\n":
            self.has_lf=True
            self.indent = 0
            return True, self.lineending, self.linestart
        return False, None, None
    def linestart(self, ch):
        lineend, output, nextstate = self.checklineend(ch)
        if lineend:
            return output, nextstate
        return ch, self.linestart
    def cr(self, ch):
        if ch=="\n":
            return self.lineending, self.linestart
        return self.lineending+ch, self.linestart
    def __init__(self, lineending):
        self.state = self.linestart
        self.lineending = lineending
    def nextchar(self, ch):
        outputch, self.state = self.state(ch)
        return outputch

BUFFSIZE=8192

def fix_file(filename, lineending="\n"):
    m = LineEndingMachine(lineending)
    with open(filename, 'rb') as f:
        with open(filename+".fixedendings", 'wb') as f2:
            while 1:
                buff = f.read(BUFFSIZE)
                obuff = []
                if buff == "":
                    break
                for ch in buff:
                    obuff.append(m.nextchar(ch))
                f2.write(''.join(obuff))
    shutil.copystat(filename, filename+".fixedendings")
    if os.path.exists(filename+".oldendings"):
        os.remove(filename+".oldendings")
    os.rename(filename, filename+".oldendings")
    os.rename(filename+".fixedendings", filename)
    os.remove(filename+".oldendings")

def fragment_to_regex(f):
    if "*" in f:
        return onestar_regex.join(fragment_to_regex(ff) for ff in f.split("*"))
    if "?" in f:
        return qmark_regex.join(fragment_to_regex(ff) for ff in f.split("?"))
    return re.escape(f)

twostars_regex = "(?:.*/)*"
onestar_regex = "[^/]*"
qmark_regex = "[^/]"

def fragments_to_regex(fragments):
    regex_str_pieces = []
    for fragment in fragments:
        if fragment == "":
            regex_str_pieces.append("/")
        elif fragment == "**":
            regex_str_pieces.append(twostars_regex)
        else:
            regex_str_pieces.append(fragment_to_regex(fragment))
            regex_str_pieces.append("/")
    if len(regex_str_pieces)>0 and regex_str_pieces[-1]=="/":
        regex_str_pieces.pop()
    regex_str_pieces.append("$")
    return "".join(regex_str_pieces)

def ant_glob(pattern):
    pattern = pattern.replace("\\", "/")
    fragments = pattern.split("/")
    leftfragments=[]
    for i in xrange(len(fragments)):
        if "*" in fragments[i] or "?" in fragments[i]:
            leftfragments=fragments[:i]
            rightfragments=fragments[i:]
            break
    else:
        leftfragments=fragments[:-1]
        rightfragments=fragments[-1:]
    if len(leftfragments)==0:
        leftfragments = ["."] + leftfragments
        fragments = ["."] + fragments
    if leftfragments==[""]:
        basedir = "/"
    else:
        basedir = "/".join(leftfragments)
    regex_str = fragments_to_regex(fragments)
    regex = re.compile(regex_str)
    for (directory, subdirs, filenames) in os.walk(basedir):
        directory = directory.replace("\\", "/")
        for filename in filenames:
            if regex.match(directory+"/"+filename) is not None:
                yield directory+"/"+filename

def parse_args():
    parser = OptionParser()
    parser.add_option("-u", "--unix",      dest="endings", action="store_const", const="\n",   help="Convert to Unix line-endings (LF).")
    parser.add_option("-d", "--dos",       dest="endings", action="store_const", const="\r\n", help="Convert to DOS line-endings (CRLF).")
    parser.add_option("-m", "--mac",       dest="endings", action="store_const", const="\r",   help="Convert to Max line-endings (CR).")
    parser.set_defaults(indent="", endings="\n")
    return parser.parse_args()

def main():
    options, args = parse_args()
    for pattern in args:
        for fname in ant_glob(pattern):
            fix_file(fname, options.endings)
            print fname

if __name__ == "__main__":
    main()
