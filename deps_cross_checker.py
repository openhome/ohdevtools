"""Class to perform cross check of dependency versions"""
import json
import os

kDepsFilename = 'dependencies.json'
kDepsPath     = 'dependencies'
kProjDataPath = 'projectdata'


class DepsCrossChecker:
    """Ensure version consistency (at major.minor level) across all dependencies"""

    def __init__( self, aTargetPlatform=None ):
        """Initialise class data"""
        self.targetPlatform = aTargetPlatform
        self.failures  = 0
        self.artifacts = {}

    def execute( self ):
        """Perform the check - return zero on success, number of mismatches on failure"""
        print('Cross-checking dependency versions')
        print('  Finding %s dependency definition files...' % kDepsFilename)
        for root, _dirs, files in os.walk( os.path.join( os.getcwd(), kDepsPath )):
            for name in files:
                if name == kDepsFilename:
                    if self.targetPlatform in root or 'AnyPlatform' in root:
                        self.artifacts[os.path.basename( root )] = self.parse_json( os.path.join( root, kDepsFilename ), self.targetPlatform)
        self.artifacts['projectdata'] = self.parse_json( os.path.join( kProjDataPath, kDepsFilename ), self.targetPlatform)

        projects = list( self.artifacts )
        while len(projects):
            project1 = projects[0]
            for project2 in projects:
                if project1 != project2:
                    self.check_versions( project1, project2 )
            projects.remove( project1 )
        return self.failures

    def check_versions( self, aProject1, aProject2 ):
        """Perform comparison between 2 specified projects"""
        print('    Checking %s against %s' % (aProject1, aProject2))
        for dependency in self.artifacts[aProject1]:
            if dependency in self.artifacts[aProject2]:
                version1 = self.artifacts[aProject1][dependency]
                version2 = self.artifacts[aProject2][dependency]
                if version1 == version2:
                    print('      %-16s %6s        --> OK' % (dependency.decode(), version1.decode()))
                else:
                    self.failures += 1
                    print('      %-16s %6s/%-6s --> FAILED' % (dependency.decode(), version1.decode(), version2.decode()))
                    print('%s != %s' % (version1, version2))

    @staticmethod
    def parse_json( aPath, aTargetPlatform ):
        """Read and parse the JSON dependencies file"""
        deps = {}
        if os.path.exists( aPath ):
            f = open( aPath, 'rt' )
            items = json.load( f )
            f.close()
            for item in items:
                try:
                    xCheck = True
                    if 'cross-check' in item:
                        xCheck = item['cross-check']
                    if xCheck:
                        name = item['name'].encode( 'ascii' )
                        vers =  item['version']
                        if '${' in vers and '}' in vers:
                            st = vers.index('${')
                            end = vers.index('}', st)
                            token = vers[(st+2):end]   
                            if '[' in token:
                                keystart = token.index('[')
                                keyend = token.index(']', keystart)
                                table = item[token[:keystart]]
                                keyvar = token[keystart+2:keyend]
                                if keyvar == 'platform':
                                    key = aTargetPlatform
                                else:               
                                    key = item[keyvar]
                                if key not in table and '*' in table:
                                    val = table['*']
                                else: 
                                    val = table[key]
                                vers = vers[:st] + val + vers[(end+1):]
                            else:
                                vers = vers[:st] + item[token] + vers[(end+1):]
                       
                        # TODO: maybe don't discard minor version here/make optional
                        ver = '.' . join( vers.split( '.' )[:-1] ).encode( 'ascii' )
                        deps[name] = ver
                except Exception as e:
                    print("Warning: %s(%s)" % (e.__class__.__name__, e))
                    pass
        return deps
