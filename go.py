import sys, os, subprocess

HELP_SYNONYMS = ["--help", "-h", "/h", "/help", "/?", "-?", "h", "help", "commands"]

def get_command_details(command):
    try:
        commands_module = __import__('commands.'+command)
        command_module = getattr(commands_module, command)
    except:
        #print sys.exc_info()
        return Command(command, "", "[There was an error processing this command]", "")
    description = getattr(command_module, 'description', '[No description available]')
    group = getattr(command_module, 'command_group', '')
    synonyms = getattr(command_module, 'command_synonyms', [])
    return Command(command, group, description, synonyms)

class Command(object):
    def __init__(self, name, group, description, synonyms):
        self.name = name
        self.group = group
        self.description = description
        self.synonyms = list(synonyms)

def getcommandnames():
    dirpath, scriptname = os.path.split(os.path.abspath(__file__))
    filenames = os.listdir(os.path.join(dirpath, 'commands'))
    commands = [f[:-3] for f in filenames if f.endswith('.py')]
    commands = [c for c in commands if not c.startswith('_')]
    commands = [c for c in commands if not c.startswith('.')]
    return commands

def getcommands():
    commandnames = getcommandnames()
    return dict(
            (c, get_command_details(c))
            for c in commandnames)

def get_commands_and_synonyms():
    commands = getcommands()
    commands_and_synonyms = dict(commands)
    for cmd in commands.values():
        for synonym in cmd.synonyms:
            commands_and_synonyms[synonym] = cmd
    return commands_and_synonyms

def findcommand(command):
    command_names = getcommandnames()
    if command in command_names:
        return command
    commands = get_commands_and_synonyms()
    if command in commands:
        return commands[command].name
    print 'Unrecognized command.'
    print 'Try "go help" for a list of commands.'
    sys.exit(1)

def runcommand(command, args):
    commandname = findcommand(command)
    exitcode = subprocess.call([sys.executable, '-m', 'commands.'+commandname] + args)
    sys.exit(exitcode)

def showcommandhelp(command):
    commandname = findcommand(command)
    commanddetails = get_command_details(commandname)
    print 'Command: ' + commanddetails.name,
    if commanddetails.synonyms:
        print "(also %s)" % (", ".join(commanddetails.synonyms),)
    else:
        print
    print
    exitcode = subprocess.call([sys.executable, '-m', 'commands.'+commandname, '--help'])
    sys.exit(exitcode)

def showhelp():
    print
    print "Usage:"
    print
    print "  go COMMAND"
    print "  go help COMMAND"
    print
    print "Available commands:"
    commands = sorted(getcommands().items())
    maxlen = max(len(cmd) for (cmd,details) in commands)
    groups = {}
    for cmd, details in commands:
        groups.setdefault(details.group, []).append(details)
    for group, commandlist in sorted(groups.items()):
        print
        if group!="":
            print "  "+group
        for details in sorted(commandlist, key=lambda c:c.name):
            print "    %s   %s" % (details.name.ljust(maxlen), details.description)

def main():
    if len(sys.argv) < 2 or sys.argv[1] in HELP_SYNONYMS:
        if len(sys.argv) >= 3:
            showcommandhelp(sys.argv[2])
        else:
            showhelp()
    else:
        runcommand(sys.argv[1], sys.argv[2:])

if __name__=="__main__":
    main()

