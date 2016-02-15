"""Class to perform cross check of dependency versions"""
import json
import os

kDepsFilename = 'dependencies.json'

class DepsCrossChecker:
    """Ensure version consistency (at major.minor level) across all dependencies"""

    def __init__( self ):
        """Initialise class data"""
        self.failures  = 0
        self.artifacts = {}

    def execute( self ):
        """Perform the check - return zero on success, number of mismatches on failure"""
        print 'Cross-checking dependency versions'
        print '  Finding %s dependency definition files...' % kDepsFilename
        for root, dirs, files in os.walk( os.path.join( os.getcwd(), kDepsPath )):
            for name in files:
                if name == kDepsFilename:
                    self.artifacts[os.path.basename( root )] = self.parse_json( os.path.join( root, kDepsFilename ))
        self.artifacts['projectdata'] = self.parse_json( os.path.join( kProjDataPath, kDepsFilename ))

        projects = self.artifacts.keys()
        for project1 in projects:
            for project2 in projects:
                if project1 != project2:
                    self.check_versions( project1, project2 )
            projects.remove( project1 )
        return self.failures

    def check_versions( self, aProject1, aProject2 ):
        """Perform comparison between 2 specified projects"""
        print '    Checking %s against %s' % (aProject1, aProject2)
        for dependency in self.artifacts[aProject1]:
            if dependency in self.artifacts[aProject2]:
                version1 = self.artifacts[aProject1][dependency]
                version2 = self.artifacts[aProject2][dependency]
                if version1==version2:
                    print '      %-16s %6s        --> OK' % (dependency, version1)
                else:
                    self.failures += 1
                    print '      %-16s %6s/%-6s --> FAILED' % (dependency, version1, version2)

    @staticmethod
    def parse_json( aPath ):
        """Read and parse the JSON dependencies file"""
        deps = {}
        if os.path.exists( aPath ):
            f = open( aPath, 'rt' )
            items = json.load( f )
            f.close()
            for item in items:
                try:
                    name = item['name'].encode( 'ascii' )
                    ver = '.' . join( item['version'].split( '.' )[:-1] ).encode( 'ascii' )
                    deps[name] =  ver
                except:
                    pass
        return deps
