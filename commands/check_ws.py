import sys
import os
import re
from optparse import OptionParser

description = "Check files for consistency of line-endings and indentation."
command_group = "Developer tools"

# State machine for analysing text files
class Machine(object):
    has_cr=False        # Has a line ending with a lone CR
    has_lf=False        # Has a line ending with a lone LF
    has_crlf=False      # Has a line ending with a CRLF
    tabindent=False     # Has a line starting with a tab
    spaceindent=False   # Has a line starting with a space
    tabafterspace=False # Has a line starting with spaces immediately followed by a tab
    spaceaftertab=False # Has a line starting with tabs immediately followed by a space
    def checklineend(self, ch):
        if ch=="\r":
            return self.cr
        if ch=="\n":
            self.has_lf=True
            return self.linestart
        return None
    def linestart(self, ch):
        lineend = self.checklineend(ch)
        if lineend:
            return lineend
        if ch==" ":
            self.spaceindent=True
            return self.spacedlinestart
        if ch=="\t":
            self.tabindent=True
            return self.tabbedlinestart
        return self.inline
    def cr(self, ch):
        if ch=="\n":
            self.has_crlf=True
            return self.linestart
        self.has_cr=True
        return self.linestart(ch)
    def spacedlinestart(self, ch):
        if ch=="\t":
            self.tabafterspace=True
            return self.inline
        if ch==" ":
            return self.spacedlinestart
        return self.inline(ch)
    def tabbedlinestart(self, ch):
        if ch==" ":
            self.spaceaftertab=True
            return self.inline
        if ch=="\t":
            return self.tabbedlinestart
        return self.inline(ch)
    def inline(self, ch):
        lineend = self.checklineend(ch)
        if lineend:
            return lineend
        return self.inline
    def __init__(self):
        self.state = self.linestart
    def nextchar(self, ch):
        self.state = self.state(ch)

BUFFSIZE=8192

def analyze_file(filename):
    m = Machine()
    with open(filename, 'rb') as f:
        while 1:
            buff = f.read(BUFFSIZE)
            if buff == "":
                break
            for ch in buff:
                m.nextchar(ch)
    indentstatus = (
        "NONE" if not m.tabindent and not m.spaceindent else
        "TABS" if m.tabindent and not m.spaceindent else
        "SPACES" if m.spaceindent and not m.tabindent else
        "BROKEN" if m.tabafterspace else
        "MESSY" if m.spaceaftertab else
        "MIXED")
    lineendingstatus = (
        "NONE" if not m.has_cr and not m.has_lf and not m.has_crlf else
        "UNIX" if m.has_lf and not m.has_cr and not m.has_crlf else
        "DOS" if m.has_crlf and not m.has_lf and not m.has_cr else
        "MAC" if m.has_cr and not m.has_lf and not m.has_crlf else
        "BROKEN")
    return indentstatus, lineendingstatus

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
    usage = (
        "\n"+
        "    %prog [options] FILE_SPEC...\n"+
        "\n"+
        "Analyse the whitespace in text files, checking indentation and line-endings.\n"+
        "FILE_SPEC can be a filename or an Ant-style glob using *, ? and ** wildcards.\n"+
        "Multiple FILE_SPECs can be provided. Exit code is 0 if any files matched, 1\n"+
        "if no files matched, and 2 if FILE_SPEC did not specify any files.\n"+
        "\n"+
        "Indentation states:\n"+
        "    NONE     - No lines are indented\n"+
        "    SPACES   - Only spaces are used for indentation\n"+
        "    TABS     - Only tabs are used for indentation\n"+
        "    MIXED    - Some lines use only spaces, others only tabs\n"+
        "    MESSY    - Tabs and spaces are used, but spaces never precede tabs\n"+
        "    BROKEN   - Tabs and spaces are used, sometimes with spaces before tabs\n"+
        "\n"+
        "Line ending states:\n"+
        "    NONE     - There are no line endings at all\n"+
        "    UNIX     - LF is used consistently\n"+
        "    DOS      - CRLF is used consistently\n"+
        "    MAC      - CR is used consistently\n"+
        "    BROKEN   - Line endings are mixed inconsistently")
    parser = OptionParser(usage=usage)
    parser.add_option("-t", "--tabs",      dest="indent",  action="store_const", const="TABS",                      help="List files that use only tabs for indentation")
    parser.add_option("-T", "--notabs",    dest="indent",  action="store_const", const="SPACES|BROKEN|MESSY|MIXED", help="List files that don't only use tabs for indentation")
    parser.add_option("-l", "--laxtabs",   dest="indent",  action="store_const", const="TABS|MESSY",                help="List files that use only tabs or tabs followed by spaces for indentation")
    parser.add_option("-L", "--nolaxtabs", dest="indent",  action="store_const", const="SPACES|BROKEN|MIXED",       help="List files that do not use only tabs or tabs followed by spaces for indentation")
    parser.add_option("-i", "--impure",    dest="indent",  action="store_const", const="BROKEN|MESSY|MIXED",        help="List files that don't stick to purely spaces or purely tabs for indentation")
    parser.add_option("-s", "--spaces",    dest="indent",  action="store_const", const="SPACES",                    help="List files that use only spaces for indentation")
    parser.add_option("-S", "--nospaces",  dest="indent",  action="store_const", const="TABS|BROKEN|MESSY|MIXED",   help="List files that don't only use spaces for indentation")
    parser.add_option("-u", "--unix",      dest="endings", action="store_const", const="UNIX",                      help="List files that have Unix line-endings")
    parser.add_option("-U", "--nounix",    dest="endings", action="store_const", const="DOS|MAC|BROKEN",            help="List files that don't have Unix line-endings")
    parser.add_option("-d", "--dos",       dest="endings", action="store_const", const="DOS",                       help="List files that have DOS line-endings")
    parser.add_option("-D", "--nodos",     dest="endings", action="store_const", const="UNIX|MAC|BROKEN",           help="List files that don't have DOS line-endings")
    parser.add_option("-b", "--broken",    dest="endings", action="store_const", const="BROKEN",                    help="List files that have inconsistent line-endings")
    parser.add_option("-v", "--verbose",   dest="verbose", action="store_true",  default=False,                     help="Report status of all listed files")
    parser.set_defaults(indent="", endings="")
    return parser.parse_args()

def match(value, target_string):
    for target in target_string.split("|"):
        if target=="":
            return True
        if target==value:
            return True
    return False

def main():
    options, args = parse_args()
    files_found = 0
    files_matched = 0
    for pattern in args:
        for fname in ant_glob(pattern):
            files_found += 1
            indent, endings = analyze_file(fname)
            should_show = (options.indent=="" and options.endings=="") or (match(indent, options.indent) and match(endings, options.endings))
            if should_show:
                files_matched += 1
                if (options.indent=="" and options.endings=="") or options.verbose:
                    print indent, "\t", endings, "\t", fname
                else:
                    print fname
    sys.exit(0 if files_matched>0 else 1 if files_found>0 else 2)

if __name__ == "__main__":
    main()
