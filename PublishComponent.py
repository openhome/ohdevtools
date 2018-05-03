import aws
import json
import os
import sys
import shutil
import subprocess
import tempfile

CORE_LCU = 'core.linn.co.uk'
AWS_BUCKET = 'linn-artifacts-private'

# ------------------------------------------------------------------------------
# Constants
# ------------------------------------------------------------------------------

kJsonManifestBaseTag    = "items"
kJsonManifestNameTag    = "name"
kJsonManifestMd5Tag     = "md5"
kJsonManifestSizeTag    = "bytes"
kJsonManifestUrlTag     = "url"
kTempDir                = tempfile.mkdtemp()
kJsonManifestFileName   = os.path.join( kTempDir, "component.json" )
kSupportedHostsAndUsers = { "core.linn.co.uk": "artifacts" }

# ------------------------------------------------------------------------------
# Support utilities
# ------------------------------------------------------------------------------

def PublishFile( aSource, aDest, aDryRun=False ):   # NOQA
    """ Copies aSource file to aDest directory (where aDest is an SSH address).
        REQUIRES senders SSH key to be stored on destination (or requests password) """
    print( 'Publishing %s to %s' % (aSource, aDest) )
    if CORE_LCU in aDest:
        dest = 's3://' + AWS_BUCKET + '/'
        dest += aDest.split( 'artifacts/' )[-1]
        dest += '/'
        dest += aSource.split( '/' )[-1]
        print( 'Upload %s to AWS %s' % (aSource, dest) )
        if not aDryRun:
            aws.copy( aSource, dest )
    else:
        flags = ''
        if aDryRun:
            flags = '--dry-run'
        exe = 'rsync -a {0} {1} {2}'.format( flags, aSource, aDest.rstrip('/') ).split()
        subprocess.check_call( exe )


def CreateRemoteDir( aRemoteDir, aDryRun=False ):
    host, path = aRemoteDir.split(':', 1)
    if CORE_LCU in host:
        # AWS buckets work by keys (so no folder to create)
        pass
    else:
        print( "Create %s on %s (if needed)" % (path, host) )
        if not aDryRun:
            exe = 'ssh {0} mkdir -p {1}/'.format( host, path ).split()  # -p option to ignore errors and create dirs and subdirs as needed (and do nothing if they already exist)
            subprocess.check_call( exe )


def RemoteDirExists( aRemoteDir ):
    if CORE_LCU in aRemoteDir:
        # AWS works by keys, so directory concept not really valid
        return True
    else:
        import pipes
        host, path = aRemoteDir.split(':', 1)
        exe = 'ssh {0} test -d {1}'.format( host, pipes.quote( path ) ).split()
        status = subprocess.call( exe )
        return status == 0


def GetFileSize( aFilePath ):
    return os.path.getsize( aFilePath )


def GetFileBasename( aFilePath ):
    return os.path.basename( os.path.normpath( aFilePath ) )


def Md5Hash(aFile):
    cmdLineMd5 = ['/usr/bin/md5sum', aFile]
    p = subprocess.Popen(args=cmdLineMd5, stdout=subprocess.PIPE)
    md5Hash = p.stdout.read().split()[0]  # disregard filename
    retVal = p.wait()
    if retVal:
        raise ToolError(cmdLineMd5)
    return md5Hash


def GetJsonObjects(aJsonFile):
    f = open(aJsonFile, 'rt')
    data = f.read()
    f.close()
    return json.loads(data)  # performs validation as well


def CreateJsonFile(aJsonObjs, aJsonFile, aSortKeys=True):
    data = json.dumps(aJsonObjs, sort_keys=aSortKeys, indent=4, separators=(',', ': '))  # creates formatted json file and validates
    # print( os.path.basename( aJsonFile ) + ":\n" + data )
    f = open(aJsonFile, 'wt')
    f.write(data)
    f.close()
    os.chmod(aJsonFile, 0664)  # allow group to write this file as it may be manually updated occasionally


def Cleanup( ):
    shutil.rmtree( kTempDir )


def PublishInfo( aDestUrl ):
    host, path = aDestUrl.split("//")[-1].split("/", 1)
    path = "/" + path
    if host not in kSupportedHostsAndUsers:
        print( "[FAIL]    %s: PublishComponent does not currently support this host" % host )
        sys.exit(2)
    user = kSupportedHostsAndUsers[host]
    fullDest = "{0}@{1}:{2}".format( user, host, path )
    return { "dest": fullDest, 'user': user, 'host': host, 'path': path }

# ------------------------------------------------------------------------------
# The Good Stuff
# ------------------------------------------------------------------------------

def PublishComponent( aBuildOutputList, aDest, aDryRun=False ):     # NOQA
    """ Publish aBuildOutputList to aDest (aBuildOutput is a list of tuples pairing a logical name with a localfile)
        Publish corresponding json manifest as well """

    publishInfo = PublishInfo( aDest )
    # if not RemoteDirExists( publishInfo['dest'] ): # remove for now as it takes a long time, use mkdir with -p option instead
    CreateRemoteDir( publishInfo['dest'], aDryRun )

    jsonManifest = { kJsonManifestBaseTag: [] }
    for buildOutput in aBuildOutputList:
        localFile = buildOutput[1]
        buildOutDict = {}
        buildOutDict[kJsonManifestNameTag] = buildOutput[0]
        buildOutDict[kJsonManifestMd5Tag] = Md5Hash( localFile )
        buildOutDict[kJsonManifestSizeTag] = GetFileSize( localFile )
        buildOutDict[kJsonManifestUrlTag] = "../" + GetFileBasename( localFile )
        # buildOutDict[kJsonManifestUrlTag] = "http://" + publishInfo['host'] + publishInfo['path'] + GetFileBasename( localFile )
        jsonManifest[kJsonManifestBaseTag].append( buildOutDict )
        PublishFile( localFile, publishInfo['dest'], aDryRun )

    jsonManifest[kJsonManifestBaseTag] = sorted( jsonManifest[kJsonManifestBaseTag], key=lambda k: k['name'] )  # ensures json is always sorted by name
    CreateJsonFile( jsonManifest, kJsonManifestFileName )
    PublishFile( kJsonManifestFileName, publishInfo['dest'], aDryRun )
    Cleanup()


def CreateComponent( aBuildOutputList, aJsonFileName ):
    """ Create a json manifest file for the given list of files """

    jsonManifest = { kJsonManifestBaseTag: [] }
    for buildOutput in aBuildOutputList:
        localFile = buildOutput[1]
        buildOutDict = {}
        buildOutDict[kJsonManifestNameTag] = buildOutput[0]
        buildOutDict[kJsonManifestMd5Tag] = Md5Hash( localFile )
        buildOutDict[kJsonManifestSizeTag] = GetFileSize( localFile )
        buildOutDict[kJsonManifestUrlTag] = "../" + localFile
        jsonManifest[kJsonManifestBaseTag].append( buildOutDict )

    jsonManifest[kJsonManifestBaseTag] = sorted( jsonManifest[kJsonManifestBaseTag], key=lambda k: k['name'] )  # ensures json is always sorted by name
    CreateJsonFile( jsonManifest, aJsonFileName )


# ------------------------------------------------------------------------------
# A Quick Test
# ------------------------------------------------------------------------------

testBuildOutput = [
    ('ver',  'version.py'),
    ('cmd',  'commands/hudson_build.py'),
    ('info', 'README')
]
testDest = 'core.linn.co.uk/home/artifacts/public_html/testUpload/josh/hahn'

# PublishComponent( testBuildOutput, testDest, False )
# CreateComponent( testBuildOutput, "component.json" )
