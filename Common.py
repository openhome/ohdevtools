import email.mime.text
import aws
import json
import os
import re
import requests
import sys
import shutil
import subprocess
import smtplib
import tempfile
import time
import json

try:
    # Python 3.
    import urllib.request as urllib2
except ImportError:
    # Fall back to Python 2.
    import urllib2

# ------------------------------------------------------------------------------
# Constants
# ------------------------------------------------------------------------------

# File Locations
kExaktDevCloudFileName      = 'devattributes.json'
kExaktStableCloudFileName   = 'attributesV4.json'
kLocalCloudFileName         = 'ExaktCloudDbV2.json'
kLocalCloudTempFileName     = 'ExaktMinimalTemp.json'
kLocalDevCloudTempFileName  = 'ExaktMinimalDevTemp.json'
# Repo locations
kExaktRepo                  = "ssh://git@core.linn.co.uk/home/git/exakt.git"
kProductRepo                = "ssh://git@core.linn.co.uk/home/git/product.git"
kReleaseUtilsRepo           = "ssh://git@core.linn.co.uk/home/git/releaseUtils.git"
kOhDevToolsRepo             = "ssh://git@core.linn.co.uk/home/git/ohdevtools.git"
kProductInfoRepo            = "ssh://git@core.linn.co.uk/home/git/ProductInfo.git"
kDsRepo                     = "ssh://git@core.linn.co.uk/home/git/ds.git"
kOhMediaPlayerRepo          = "ssh://git@core.linn.co.uk/home/git/ohMediaPlayer.git"
# Misc
kDateAndTime                = time.strftime('%d %b %Y %H:%M:%S', time.localtime())  # returns: 25 Aug 2014 15:38:11
kProductSuppressedString    = 'DISABLED'
kExaktSuppressedString      = 'suppress'
# crash report related
kTicketUrlBase              = "http://core.linn.co.uk/network/ticket/"
kReportUrlBase              = "http://products.linn.co.uk/restricted/site/device/exception/"
# Aws S3 - private
kAwsBucketPrivate           = 'linn-artifacts-private'
kAwsProductionBase          = 'Volkano2Products/'
kAwsHardwareBase            = 'hardware/'
kAwsElfBase                 = '/artifacts/builds/Volkano2'
kElfFileFilter              = '*.elf'
# Aws S3 - public
kAwsBucketPublic            = 'linn-artifacts-public' # linn public, no customers



# ------------------------------------------------------------------------------
# Support utilities
# ------------------------------------------------------------------------------
def Heading( aMsg ):
    """Display heading message"""
    print( '\n-------------------------------------------------------------------------------')
    print( aMsg )
    print( '-------------------------------------------------------------------------------')


def Info( aMsg ):
    """Display information message"""
    print( aMsg )


def GetJsonObjects( aJsonFile ):
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
    os.chmod(aJsonFile, 0o664)  # NOQA  allow group to write this file as it may be manually updated occasionally


def ReadJson(aJsonFile):
    return GetJsonObjects(aJsonFile)


def WriteJson(aData, aJsonFile, aSortKeys=True):
    CreateJsonFile(aData, aJsonFile, aSortKeys)


def GetLines(aTextFile):
    f = open(aTextFile, 'rt')
    data = f.readlines()
    f.close()
    return data


def CreateTextFile(aLines, aTextFile):
    f = open(aTextFile, 'wt')
    f.writelines(aLines)
    f.close()


def CompareVersions(aVersion1, aVersion2):
    # if aVersion1 > aVersion2 return true, otherwise return false

    try:
        v1valid = len(aVersion1.split('.')) == 3 and aVersion1.split('.')[0] != "0"
    except:
        v1valid = False
    try:
        v2valid = len(aVersion2.split('.')) == 3 and aVersion2.split('.')[0] != "0"
    except:
        v2valid = False

    if v1valid and not v2valid:
        return True
    elif v2valid and not v1valid:
        return False
    elif not v1valid and not v2valid:
        raise ValueError("Neither version to compare is valid")

    new = aVersion1.split('_')[0].split('.')
    old = aVersion2.split('_')[0].split('.')

    if int(new[0]) > int(old[0]):
        return True
    elif int(new[0]) == int(old[0]) and int(new[1]) > int(old[1]):
        return True
    elif int(new[0]) == int(old[0]) and int(new[1]) == int(old[1]) and int(new[2]) > int(old[2]):
        return True
    return False


def SendEmail( aSubject, aText, aTo, aDryRun ):
    """Send email subject aSubject containing aText to aRecipients"""
    sender = 'josh.hahn@linn.co.uk'
    recipients = aTo
    ccList = []
    if aDryRun:
        recipients = [sender] # , 'IT_Infrastructure@linn.co.uk'
    else:
        ccList = ['josh.hahn@linn.co.uk', 'graham.douglas@linn.co.uk']
    mail = email.mime.text.MIMEText( aText )
    mail['Subject'] = aSubject
    mail['From'] = sender
    mail['To'] = ', '.join( recipients )
    mail['Cc'] = ', '.join( ccList )
    s = smtplib.SMTP( 'mail.linn.co.uk' )
    s.ehlo()
    # If we can encrypt this session, do it
    if s.has_extn('STARTTLS'):
        s.starttls()
        s.ehlo()  # re-identify ourselves over TLS connection
    s.sendmail( sender, recipients + ccList, mail.as_string() )
    s.quit()


def SendPublishedEmail( aExecutable, aVersion, aPlatform, aReleaseNotes=None, aDryRun=False ):
    subject = ""
    msg = ""
    ext = "tar.gz"
    if 'Windows-' in aPlatform:
        platformFriendly = aPlatform.split('-')[0]
        subject = '%s version %s published (%s)' % ( aExecutable, aVersion, platformFriendly )
        msg = 'The new version of %s for %s (%s) can be downloaded from here:\n\n' % ( aExecutable, platformFriendly, aVersion )
        msg += "https://linn-artifacts-private.s3-eu-west-1.amazonaws.com/{0}/{0}-{1}-{2}-Release.{3}".format( aExecutable, aVersion, aPlatform, ext )
    elif 'Mac-' in aPlatform or 'Linux-' in aPlatform:
        Info( "Don't bother sending publish email for: %s" % aPlatform )
        return
    else:
        subject = '%s version %s published' % ( aPlatform, aVersion )
        msg = 'The new version of %s (%s) can be downloaded from here:\n\n' % ( aPlatform, aVersion )
        if 'Volkano1' in aExecutable:
            ext = "zip"
            msg += "https://linn-artifacts-private.s3-eu-west-1.amazonaws.com/{0}/{1}-{2}.{3}".format( aExecutable, aPlatform, aVersion, ext )
        else:
            msg += "https://linn-artifacts-private.s3-eu-west-1.amazonaws.com/{0}/{0}-{1}-{2}.{3}".format( aExecutable, aPlatform, aVersion, ext )
    if aReleaseNotes is not None:
        msg += "\n\nRelease Notes:\n"
        msg += aReleaseNotes
    recipients = ['Productisation_Email_Group@linn.co.uk']
    Info( "Sending published email to: %s" % recipients )
    Info( "SUBJECT: %s" % subject )
    Info( "MESSAGE: %s" % msg )
    SendEmail( subject, msg, recipients, aDryRun )


def CommitAndPushFiles( aRepo, aFileList, aCommitMessage, aDryRun, aBranch=None ):
    from git import Repo
    clonePath = tempfile.mkdtemp()
    if aBranch is not None and len(aBranch) > 0:
        Info( "Locally clone %s (%s) to %s" % ( aRepo, aBranch, clonePath ) )
        localRepo = Repo.clone_from( aRepo, clonePath, branch=aBranch )
    else:
        Info( "Locally clone %s to %s" % ( aRepo, clonePath ) )
        localRepo = Repo.clone_from( aRepo, clonePath )

    repoName = os.path.basename( aRepo ).split('.')[0]
    for file in aFileList:
        # copy locally changed files to clone
        parentDir = os.path.abspath(os.path.join(file, os.pardir))
        fileDir = os.path.basename( parentDir )
        if fileDir == repoName:
            fileDir = ""
        relPath = os.path.join( fileDir, os.path.basename( file ) )
        fullPath = os.path.join( clonePath, relPath )
        Info( "Copy %s to %s " % ( file, fullPath ) )
        shutil.copy2( file, fullPath )
        localRepo.index.add( [relPath] )  # add changes

    if localRepo.is_dirty():  # check if any changes to commit
        Info( "Committing changed files..." )
        Info( "%s" % localRepo.git.status() )
        if not aDryRun:
            localRepo.index.commit( "%s" % aCommitMessage )  # commit changes
        Info( "Pushing changes to %s" % aRepo )
        if not aDryRun:
            localRepo.git.push()
    else:
        Info( "No changed files to commit!" )

    shutil.rmtree( clonePath )  # remove temp clone


def PushNewTag( aRepo, aNewTag, aExistingTag, aDryRun ):
    from git import Repo
    clonePath = tempfile.mkdtemp()
    Info( "Locally clone %s to %s" % ( aRepo, clonePath ) )
    localRepo = Repo.clone_from( aRepo, clonePath )
    Info( "Adding new tag %s to existing tag %s" % ( aNewTag, aExistingTag ) )
    newTag = None
    if not aDryRun:
        newTag = localRepo.create_tag( aNewTag, ref=aExistingTag )
    Info( "Pushing new tag to %s" % aRepo )
    if not aDryRun:
        localRepo.remotes.origin.push( newTag )
    shutil.rmtree( clonePath )  # remove temp clone


def GetDependenciesJson( aRepo, aVersion ):
    from git import Repo
    clonePath = tempfile.mkdtemp()
    Info( "Locally clone %s to %s" % ( aRepo, clonePath ) )
    localRepo = Repo.clone_from( aRepo, clonePath )
    prefix = "release"
    if aVersion.split('.')[1] == "0":
        prefix = "nightly"
    localRepo.git.checkout( "%s_%s" % ( prefix, aVersion ) )
    depFile = os.path.join( clonePath, "projectdata", "dependencies.json")
    jsonObjs = GetJsonObjects( depFile )
    shutil.rmtree( clonePath )  # remove temp clone
    print( "Dependecies for " + aRepo + " @ " + aVersion )
    for obj in jsonObjs:
        print( "    " + obj['name'] + ": " + obj['version'] )
    return jsonObjs

def CopyFileWithPermissions(aSource, aDestination):
    shutil.copy2(aSource, aDestination)
    # BELOW WAS REQUIRED FOR COPYING ON ENG - could be removed next time anyone looks at this
    #import grp
    #subprocess.check_call(['sudo', 'cp', '--preserve=mode', aSource, aDestination])
    #try:
    #    subprocess.check_call(['sudo', 'chown', '%d:%d' % (os.geteuid(), grp.getgrnam('products').gr_gid), aDestination])
    #except:
    #    subprocess.check_call(['sudo', 'chown', '%d:%d' % (os.geteuid(), os.getegid()), aDestination])


def Md5Hash(aFile):
    cmdLineMd5 = ['/usr/bin/md5sum', aFile]
    p = subprocess.Popen(args=cmdLineMd5, stdout=subprocess.PIPE)
    md5Hash = p.stdout.read().split()[0]  # disregard filename
    retVal = p.wait()
    if retVal:
        raise ToolError(cmdLineMd5)
    md5Hash = md5Hash.decode()
    return md5Hash


def GetBitstreamVersion(aBitstreamFile):
    """Extract version number from given bitstream file."""
    f = open(aBitstreamFile, 'rt')
    data = f.read()
    f.close()
    ver = re.search(r'[0-9]+\.[0-9]+\.[0-9]+', data)
    if ver:
        return ver.group(0)
    return 'Unknown'


def CreateHtmlFile( aHtml, aHtmlFile, aPrintToScreen ):
    print( "Creating html output file: %s" % aHtmlFile )

    htmlFile = aHtmlFile
    if "@" in aHtmlFile:
        htmlFile = "TempHtmlFile.html"

    f = open(htmlFile, 'wt')
    f.write( aHtml.encode('utf-8') )
    f.close()

    if "@" in aHtmlFile:
        cmd = "scp %s %s" % ( htmlFile, aHtmlFile )
        resp = subprocess.call(cmd.split())
        os.unlink( htmlFile )
        if resp != 0:
            Info( "    SCP call failed with exit code %d" % resp )
            sys.exit(resp)

    if aPrintToScreen:
        print( aHtml )


def TitleToId( aTitle ):
    id = aTitle.replace(" ", "")
    id = id.replace("-", "")
    id = id.replace("(", "")
    id = id.replace(")", "")
    id = id.replace("[", "")
    id = id.replace("]", "")
    id = id.replace("<", "")
    id = id.replace(">", "")
    id = id.replace("+", "Plus")
    id = id.replace(".", "d")
    return id


def DownloadFromAws( aKey, aDestinationFile, aBucket=kAwsBucketPrivate ):
    print( 'Download from AWS s3://%s/%s to %s' % ( aBucket, aKey, os.path.abspath( aDestinationFile ) ) )
    aws.cp( 's3://%s/%s' % (aBucket, aKey), aDestinationFile )


def UploadToAws( aKey, aSourceFile, aBucket=kAwsBucketPrivate, aDryRun=False ):
    print( 'Upload %s to AWS s3://%s/%s' % ( os.path.abspath( aSourceFile ), aBucket, aKey ) )
    if not aDryRun:
        aws.cp( aSourceFile, 's3://%s/%s' % (aBucket, aKey) )

def DeleteFromAws( aKey, aBucket=kAwsBucketPrivate, aDryRun=False ):
    print( 'Delete from AWS s3://%s/%s' % ( aBucket, aKey ) )
    if not aDryRun:
        aws.delete( 's3://%s/%s' % (aBucket, aKey) )

def DeleteRecursiveFromAws( aDstDir, aBucket=kAwsBucketPrivate, aFileFilter=None, aDryRun=False ):
    filelist = aws.lsr( 's3://%s/%s' % (aBucket, aDstDir) )
    for f in filelist:
        if aFileFilter == None or aFileFilter in f:
            if not f.endswith("/"):
                DeleteFromAws( f, aBucket, aDryRun)

def UploadRecursiveToAws( aSrcDir, aDstDir, aBucket=kAwsBucketPrivate, aFileFilter="*", aDryRun=False ):
    import glob
    for f in glob.glob( os.path.join(aSrcDir, aFileFilter) ):
        fileKey = os.path.join( aDstDir, os.path.basename(f) )
        UploadToAws( fileKey, f, aBucket, aDryRun)

def UploadToAwsDir( aDir, aSourceFile, aBucket=kAwsBucketPrivate, aDryRun=False ):
    key = os.path.join( aDir, os.path.basename(aSourceFile) )
    UploadToAws( key, aSourceFile, aBucket, aDryRun )


def CopyOnAws( aSourceKey, aDestKey, aBucket=kAwsBucketPrivate, aDryRun=False ):
    print( 'Copy on AWS (%s) %s to %s' % ( aBucket, aSourceKey, aDestKey ) )
    if not aDryRun:
        aws.cp( 's3://%s/%s' % (aBucket, aSourceKey), 's3://%s/%s' % (aBucket, aDestKey) )

def CopyOnAwsCrossBucket( aSourceKey, aSourceBucket, aDestKey, aDestBucket, aDryRun=False ):
    print( 'Copy cross bucket on AWS (%s) %s to (%s) %s' % ( aSourceBucket, aSourceKey, aDestBucket, aDestKey ) )
    if not aDryRun:
        aws.cp( 's3://%s/%s' % (aSourceBucket, aSourceKey), 's3://%s/%s' % (aDestBucket, aDestKey) )

def ListRecursiveOnAws( aDestDir, aBucket=kAwsBucketPrivate, aFileFilter=None ):
    print( 'List Recursive on AWS (%s) %s' % ( aBucket, aDestDir ) )
    destDir = aDestDir.lstrip( '/' )
    awsItems = aws.lsr( 's3://%s/%s' % (aBucket, destDir) )
    items = []
    for i in awsItems:
        if aFileFilter == None or aFileFilter in i:
            items.append(i)
    return items

def CopyRecursiveOnAws( aSourceDir, aDestDir, aBucket=kAwsBucketPrivate, aDryRun=False ):
    print( 'Copy Recursive on AWS (%s) %s to %s' % ( aBucket, aSourceDir, aDestDir ) )
    cpcnt = 0
    sourceDir = aSourceDir.lstrip( '/' )
    destDir = aDestDir.lstrip( '/' )
    items = aws.lsr( 's3://%s/%s' % (aBucket, sourceDir) )
    for item in items:
        if item[-1] != '/':
            cpcnt += 1
            CopyOnAws( item, item.replace( sourceDir, destDir ), aBucket, aDryRun )
    return cpcnt

def CopyRecursiveOnAwsCrossBucket( aSourceDir, aSourceBucket, aDestDir, aDestBucket, aDryRun=False ):
    print( 'Copy Recursive cross bucket on AWS (%s) %s to (%s) %s' % ( aSourceBucket, aSourceDir, aDestBucket, aDestDir ) )
    cpcnt = 0
    sourceDir = aSourceDir.lstrip( '/' )
    destDir = aDestDir.lstrip( '/' )
    items = aws.lsr( 's3://%s/%s' % (aSourceBucket, sourceDir) )
    for item in items:
        if item[-1] != '/':
            cpcnt += 1
            CopyOnAwsCrossBucket( item, aSourceBucket, item.replace( sourceDir, destDir ), aDestBucket, aDryRun )
    return cpcnt

def MoveOnAws( aSourceKey, aDestKey, aBucket=kAwsBucketPrivate, aDryRun=False ):
    print( 'Move on AWS (%s) %s to %s' % ( aBucket, aSourceKey, aDestKey ) )
    if not aDryRun:
        aws.mv( 's3://%s/%s' % (aBucket, aSourceKey), 's3://%s/%s' % (aBucket, aDestKey) )


def MoveRecursiveOnAws( aSourceDir, aDestDir, aBucket=kAwsBucketPrivate, aDryRun=False ):
    if not aDryRun:
        sourceDir = aSourceDir.lstrip( '/' )
        destDir = aDestDir.lstrip( '/' )
        items = aws.lsr( 's3://%s/%s' % (aBucket, sourceDir.lstrip( '/' )) )
        for item in items:
            if item[-1] != '/':
                aws.mv( 's3://%s/%s' % (aBucket, item), 's3://%s/%s' % (aBucket, item.replace( sourceDir, destDir )) )


def CreateFile(aData, aFile):
    f = open(aFile, 'wt')
    f.write(aData)
    f.close()

def GetExaktDevFeed( aLocalFilePath ):
    return GetExaktFeed( aLocalFilePath, kExaktDevCloudFileName )

def GetExaktStableFeed( aLocalFilePath ):
    return GetExaktFeed( aLocalFilePath, kExaktStableCloudFileName )

def GetExaktFeed( aLocalFilePath, aFeedName ):
    key = "exakt/feeds/%s" % (aFeedName)
    f = os.path.join( aLocalFilePath, aFeedName )
    try:
        DownloadFromAws( key, f, aBucket=kAwsBucketPublic )
    except:
        f = None
    return f

def GetExaktComponent( aLocalFilePath, aComponentName ):
    key = "exakt/components/%s" % (aComponentName)
    f = os.path.join( aLocalFilePath, aComponentName )
    try:
        DownloadFromAws( key, f, aBucket=kAwsBucketPublic )
    except:
        f = None
    return f

def GetExaktComponentList( aIncludeVersion ):
    exaktCompList = aws.ls('s3://' + kAwsBucketPublic + '/exakt/components/')

    if not aIncludeVersion:
        uniqueList = []
        for comp in exaktCompList:
            unique = comp.split("_")[-1]
            if unique not in uniqueList:
                uniqueList.append( unique )
        return uniqueList
    else:
        return exaktCompList

def GetLatestExaktVersion():
    exaktFeedList = aws.ls('s3://' + kAwsBucketPublic + '/exakt/feeds/')
    versionList = []
    latestVersion = None
    for feedFile in exaktFeedList:
        if '_Cloud.json' in feedFile:
            versionList.append( os.path.basename(feedFile).split('_')[0] )
    if len(versionList) > 0:
        mostRecentVersion = '0.0.0'
        for version in versionList:
            versionSplit = map(int, version.split('.'))
            mostRecentVersionSplit = map(int, mostRecentVersion.split('.'))
            if (versionSplit[0] > mostRecentVersionSplit[0]) or (versionSplit[0] == mostRecentVersionSplit[0] and versionSplit[1] > mostRecentVersionSplit[1]) or (versionSplit[0] == mostRecentVersionSplit[0] and versionSplit[1] == mostRecentVersionSplit[1] and versionSplit[2] > mostRecentVersionSplit[2]):
                mostRecentVersion = version
        if mostRecentVersion != '0.0.0':
            latestVersion = mostRecentVersion
    return  latestVersion

def UploadExaktFeedToAws( aFeedName, aLocalFeedFile, aDryRun ):
    UploadToAws( 'exakt/feeds/%s' % ( aFeedName ), aLocalFeedFile, kAwsBucketPublic, aDryRun )

def UploadExaktComponentToAws( aComponentName, aLocalComponentFile, aDryRun ):
    UploadToAws( 'exakt/components/%s' % ( aComponentName ), aLocalComponentFile, kAwsBucketPublic, aDryRun )

def PublishTestDsEmulatorAws( aVersion, aDryRun=False ):
    CreateTestDsEmulator( aVersion, False, False, aDryRun )


def PublishTestDsEmulatorLocal( aVersion, aDryRun=False ):
    CreateTestDsEmulator( aVersion, False, True, aDryRun )


def CheckPublishTestDsEmulatorAws( aVersion, aDryRun=False ):
    CreateTestDsEmulator( aVersion, True, False, aDryRun )


def CheckPublishTestDsEmulatorLocal( aVersion, aDryRun=False ):
    CreateTestDsEmulator( aVersion, True, True, aDryRun )


def CreateTestDsEmulator( aVersion, aCheckOnly, aLocalOnly, aDryRun ):
    kEmulatorTypes = [ { "os": "Linux-x86",   "spotify": "spotify_embedded/lib/libspotify_embedded_shared.so" },
                       { "os": "Windows-x86", "spotify": "spotify_embedded/lib/spotify_embedded_shared.dll" } ]  # Core-ppc32?
    jsonObjs = GetDependenciesJson( kProductRepo, aVersion )
    dsVer = spotifyVer = dsKey = spotifyKey = dsFile = spotifyFile = None
    versionId = aVersion.split('.')[1]
    localDirTop = '%s-TestDs' % aVersion
    if not os.path.exists( localDirTop ):
        os.makedirs( localDirTop )

    for et in kEmulatorTypes:
        print( "Emulator info: %s" % et )
        localDirEt = os.path.join( localDirTop, '%s' % et["os"] )
        if not os.path.exists( localDirEt ):
            os.makedirs( localDirEt )
        for obj in jsonObjs:
            if obj['name'] == 'ds':
                dsVer = obj['version']  # earliest windows variant is 0.102.723 as we weren't publishing this by default
                if dsVer == '1.33.263': # temporary hack to get Davaar 88 released with a working TestDs at Simon's request
                    dsVer = '1.33.265'
                dsFile = "ds-%s-%s-Release.tar.gz" % ( dsVer, et["os"] )
                dsKey = "ds/%s" % dsFile
                dsFile = os.path.join( localDirEt, dsFile )
            elif obj['name'] == 'Spotify':
                spotifyVer = obj['version']
                spotifyFile = "spotify_embedded-v%s-%s-Release.tar.gz" % ( spotifyVer, et["os"] )
                spotifyKey = "spotify/repackaged/%s" % spotifyFile
                spotifyFile = os.path.join( localDirEt, spotifyFile )

        fail = False
        errorMsg = ''
        try:
            DownloadFromAws( dsKey, dsFile )
        except:
            errorMsg = "Could not download ds artifact from AWS: %s" % dsKey
            fail = True

        try:
            DownloadFromAws( spotifyKey, spotifyFile )
        except:
            errorMsg = "Could not download Spotify artifact from AWS: %s" % spotifyFile
            fail = True

        if fail:
            print( "\nERROR: %s" % errorMsg )
            SendEmail( "WARNING: TestDs Emulator Cannot be Created (%s)" % aVersion, errorMsg, ['Simon.Chisholm@linn.co.uk'], aDryRun )
            shutil.rmtree( localDirTop )
            return

        import tarfile
        tar = tarfile.open( spotifyFile )
        member = tar.getmember( et["spotify"] )
        member.name = os.path.basename( member.name )
        tar.extract( member, localDirEt )
        tar.close()
        os.remove( spotifyFile )

        if "Linux" in et["os"]:
            dockerData = """
            FROM ubuntu:16.04 AS ds_base

            RUN apt-get update; apt-get install -y libc6-i386 lib32stdc++6

            FROM ds_base

            ENV ROOM="davaar-{0}"
            ENV NAME="davaar-{0}"
            ENV DUMMY_BOARD_INDEX=80
            ENV SUBDOMAIN_PREFIX="beta"

            ADD ds-{1}-{3}-Release.tar.gz /opt
            # Extracted from spotify_embedded-v{2}-{3}-Release.tar.gz
            ADD libspotify_embedded_shared.so /opt/ds/bin
            RUN chmod +x /opt/ds/bin/TestDs

            WORKDIR /opt/ds

            ENTRYPOINT ./bin/TestDs --ui ui/AkurateIcons/ --cloud ${{DUMMY_BOARD_INDEX}} --name ${{NAME}} --room ${{ROOM}} --cloud-sub-domain ${{SUBDOMAIN_PREFIX}}
            """.format( versionId, dsVer, spotifyVer, et["os"] )

            CreateFile( dockerData, os.path.join( localDirEt, 'Dockerfile' ) )
        else:
            tar = tarfile.open( dsFile )
            tar.extractall( localDirEt )
            tar.close()
            os.remove( dsFile )

            txtData = "ds\\bin\\TestDs.exe -r TestDs-%s -n SoftPlayer -l --ui ds\\ui\\AkurateIcons\\" % aVersion
            CreateFile( txtData, os.path.join( localDirEt, 'TestDs.bat' ) )

    if aCheckOnly:
        print( "TestDs Emulator check succeeded" )
        shutil.rmtree( localDirTop )
        return

        # will only end up here on a publish request (local or Aws)

    tarOutputFile = localDirTop + ".tar.gz"
    if os.path.exists( tarOutputFile ):
        os.remove( tarOutputFile )
    with tarfile.open( tarOutputFile, "w:gz" ) as tarOut:
        tarOut.add( localDirTop, arcname=os.path.basename( localDirTop ) )

    shutil.rmtree( localDirTop )

    if aLocalOnly:
        print( "TestDs Emulator for %s available here: %s" % ( aVersion, os.path.abspath( tarOutputFile ) ) )
        if aDryRun:
            os.remove( tarOutputFile )
    else:
        uploadKey = '%s%s' % ( kAwsProductionBase, tarOutputFile )
        UploadToAws( uploadKey, tarOutputFile, aDryRun=aDryRun )

        os.remove( tarOutputFile )

        to = [ 'Iain.Mcleod@linn.co.uk', 'Simon.Chisholm@linn.co.uk' ]
        subj = "TestDs Emulator for %s Now Available" % aVersion
        text = "Download here: https://s3-eu-west-1.amazonaws.com/linn-artifacts-private/%s" % uploadKey
        SendEmail( subj, text, to, aDryRun )
