import aws
import json
import os
import shutil
import subprocess
import tempfile
import Common

# ------------------------------------------------------------------------------
# Constants
# ------------------------------------------------------------------------------

kJsonManifestBaseTag    = "items"
kJsonManifestNameTag    = "name"
kJsonManifestMd5Tag     = "md5"
kJsonManifestSizeTag    = "bytes"
kJsonManifestUrlTag     = "url"
kJsonManifestSubdepsTag = "subdeps"
kJsonManifestTokenTag   = "token"
kTempDir                = tempfile.mkdtemp()
kJsonManifestFileName   = os.path.join( kTempDir, "component.json" )
kLinnHostPublic         = "https://cloud.linn.co.uk"  # "https://beta-cloud.linn.co.uk"
kLinnHostPrivate        = "https://artifacts.linn.co.uk"
kAwsHostPublic          = "s3://linn-artifacts-public"
kAwsHostPrivate         = "s3://linn-artifacts-private"

# ------------------------------------------------------------------------------
# Support utilities
# ------------------------------------------------------------------------------

def PublishFileToSsh( aSource, aDest, aDryRun=False ):   # NOQA
    """ Copies aSource file to aDest directory (where aDest is an SSH address).
        REQUIRES senders SSH key to be stored on destination (or requests password) """
    print( 'Publishing %s to %s' % (aSource, aDest) )
    flags = ''
    if aDryRun:
        flags = '--dry-run'
    exe = 'rsync -a {0} {1} {2}'.format( flags, aSource, aDest.rstrip('/') ).split()
    subprocess.check_call( exe )

def PublishFileToAws( aSource, aDest, aDryRun=False ):   # NOQA
    destDir = aDest.replace(kLinnHostPublic, kAwsHostPublic).replace(kLinnHostPrivate, kAwsHostPrivate)
    dest = os.path.join( destDir, os.path.basename(aSource) )
    print( 'Upload %s to AWS %s' % (aSource, dest) )
    if not aDryRun:
        aws.copy( aSource, dest )


def CreateRemoteDir( aRemoteDir, aDryRun=False ):
    host, path = aRemoteDir.split(':', 1)
    print( "Create %s on %s (if needed)" % (path, host) )
    if not aDryRun:
        exe = 'ssh {0} mkdir -p {1}/'.format( host, path ).split()  # -p option to ignore errors and create dirs and subdirs as needed (and do nothing if they already exist)
        subprocess.check_call( exe )


def RemoteDirExists( aRemoteDir ):
    import pipes
    host, path = aRemoteDir.split(':', 1)
    exe = 'ssh {0} test -d {1}'.format( host, pipes.quote( path ) ).split()
    status = subprocess.call( exe )
    return status == 0


def GetFileSize( aFilePath ):
    return os.path.getsize( aFilePath )


def GetFileBasename( aFilePath ):
    return os.path.basename( os.path.normpath( aFilePath ) )


def Cleanup( ):
    shutil.rmtree( kTempDir )


# ------------------------------------------------------------------------------
# The Good Stuff
# ------------------------------------------------------------------------------

def PublishComponent( aBuildOutputList, aDest, aSubDependenciesList=None, aDryRun=False ):     # NOQA
    """ Publish aBuildOutputList and aSubDependenciesList to aDest
        aBuildOutput: a list of tuples pairing a logical name with a localfile
        aSubDependenciesList: list of tuples pairing a name and token that will become the "subdeps" list (can be None)
        Publish corresponding json manifest as well """

    CreateComponent( aBuildOutputList, kJsonManifestFileName, aSubDependenciesList )

    if any(x in aDest for x in [kLinnHostPublic, kLinnHostPrivate, kAwsHostPublic, kAwsHostPrivate]):
        # use AWS
        for buildOutput in aBuildOutputList:
            PublishFileToAws( buildOutput[1], aDest, aDryRun )
        PublishFileToAws( kJsonManifestFileName, aDest, aDryRun )
    else:
        CreateRemoteDir( aDest, aDryRun )
        for buildOutput in aBuildOutputList:
            PublishFileToSsh( buildOutput[1], aDest, aDryRun )
        PublishFileToSsh( kJsonManifestFileName, aDest, aDryRun )

    Cleanup()


def CreateComponent( aBuildOutputList, aJsonFileName, aSubDependenciesList=None, aDryRun=False ):
    """ Create a json manifest file for the given list of files """

    jsonManifest = { kJsonManifestBaseTag: [] }
    if aSubDependenciesList is not None and len(aSubDependenciesList) > 0:
        jsonManifest[kJsonManifestSubdepsTag] = []
        for subdep in aSubDependenciesList:
            subdepDict = {}
            subdepDict[kJsonManifestNameTag] = subdep[0]
            subdepDict[kJsonManifestTokenTag] = subdep[1]
            jsonManifest[kJsonManifestSubdepsTag].append( subdepDict )
    for buildOutput in aBuildOutputList:
        localFile = buildOutput[1]
        buildOutDict = {}
        buildOutDict[kJsonManifestNameTag] = buildOutput[0]
        buildOutDict[kJsonManifestMd5Tag] = Common.Md5Hash( localFile )
        buildOutDict[kJsonManifestSizeTag] = GetFileSize( localFile )
        buildOutDict[kJsonManifestUrlTag] = "../" + GetFileBasename( localFile )
        jsonManifest[kJsonManifestBaseTag].append( buildOutDict )

    jsonManifest[kJsonManifestBaseTag] = sorted( jsonManifest[kJsonManifestBaseTag], key=lambda k: k['name'] )  # ensures json is always sorted by name
    Common.CreateJsonFile( jsonManifest, aJsonFileName )
    if aDryRun:
        print("--- %s ---" % aJsonFileName)
        print(json.dumps(jsonManifest, indent=4, sort_keys=True))
        print("---------------")


def PublishFile( aFile, aDest, aDryRun=False ):
    PublishFiles( [aFile], aDest, aDryRun )


def PublishFiles( aFileList, aDest, aDryRun=False ):
    if any(x in aDest for x in [kLinnHostPublic, kLinnHostPrivate, kAwsHostPublic, kAwsHostPrivate]):
        # use AWS
        for f in aFileList:
            PublishFileToAws( f, aDest, aDryRun )
    else:
        CreateRemoteDir( aDest, aDryRun )
        for f in aFileList:
            PublishFileToSsh( f, aDest, aDryRun )


# ------------------------------------------------------------------------------
# A Quick Test
# ------------------------------------------------------------------------------

testBuildOutput = [
    ('ver',  'version.py'),
    ('cmd',  'commands/hudson_build.py'),
    ('info', 'README')
]
testSubDependencies = [
    ('exakt', 3)
]
testDest = 'core.linn.co.uk/home/artifacts/public_html/testUpload/joshie/hahn'
