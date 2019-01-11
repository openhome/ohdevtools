import email.mime.text
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
import urllib2

# ------------------------------------------------------------------------------
# Constants
# ------------------------------------------------------------------------------

# CDN locations - jenkins job runs on eng.linn.co.uk - need to relocate cdn directory if this changed
kCdnWwwDestination          = "linnapi@static.linnapi.com:/var/www.linnapi/public_html"
kCdnRsyncLocalDir           = "/local/share/cdn/"   # local location (eng) to sync with remote host
kCdnDirForUploadV2          = '/local/share/cdn/exaktV2'    # location for rsync with public server: \\eng.linn.co.uk\share\cdn\exaktV2\
kExaktJsonGenericDevCloudV2 = os.path.join(kCdnDirForUploadV2, 'devattributes.json')
kExaktJsonStableCloudV2     = os.path.join(kCdnDirForUploadV2, 'attributesV4.json')
kDirComponentsV2            = '/local/share/componentsV2'   # official location for software components: \\eng.linn.co.uk\share\componentsV2\
kLocalCloudFileName         = 'ExaktCloudDbV2.json'
kLocalCloudTempFileName     = 'ExaktMinimalTemp.json'
kLocalDevCloudTempFileName  = 'ExaktMinimalDevTemp.json'
# Repo locations
kExaktRepo                  = "ssh://joshh@core.linn.co.uk/home/git/exakt.git"  # would prefer to use artifacts user but it is not allowed to push. Requires membership in BUILTIN\users group, and  <usermod -a -G "BUILTIN\\users" artifacts> doesn't woprk from root
kProductRepo                = "ssh://joshh@core.linn.co.uk/home/git/product.git"    # would prefer to use artifacts user but it is not allowed to push. Requires membership in BUILTIN\users group, and  <usermod -a -G "BUILTIN\\users" artifacts> doesn't woprk from root
kReleaseUtilsRepo           = "ssh://joshh@core.linn.co.uk/home/git/releaseUtils.git"   # would prefer to use artifacts user but it is not allowed to push. Requires membership in BUILTIN\users group, and  <usermod -a -G "BUILTIN\\users" artifacts> doesn't woprk from root
kOhDevToolsRepo             = "ssh://joshh@core.linn.co.uk/home/git/ohdevtools.git"     # would prefer to use artifacts user but it is not allowed to push. Requires membership in BUILTIN\users group, and  <usermod -a -G "BUILTIN\\users" artifacts> doesn't woprk from root
kProductInfoRepo            = "ssh://joshh@core.linn.co.uk/home/git/ProductInfo.git"    # would prefer to use artifacts user but it is not allowed to push. Requires membership in BUILTIN\users group, and  <usermod -a -G "BUILTIN\\users" artifacts> doesn't woprk from root
# Kiboko details
kRemoteHost                 = 'products@kiboko.linn.co.uk'
kDevFileLocation            = '/var/www.products/VersionInfo/Downloads/Development/'
kBetaFileLocation           = '/var/www.products/VersionInfo/Downloads/Beta/'
kReleaseFileLocation        = '/var/www.products/VersionInfo/Downloads/Releases/'
kFeedLocation               = kRemoteHost + ':/var/www.products/VersionInfo/'
kDevMasterFeedFileName      = 'DevelopmentMasterFeed.json'
kDevFeedFileName            = 'DevelopmentVersionInfoV2.json'
kBetaFeedFileName           = 'LatestVersionInfoV2.json'
kReleaseUrlBase             = 'http://products.linn.co.uk/VersionInfo/'
# Misc
kDateAndTime                = time.strftime('%d %b %Y %H:%M:%S', time.localtime())  # returns: 25 Aug 2014 15:38:11
kProductSuppressedString    = 'DISABLED'
kExaktSuppressedString      = 'suppress'
# crash report related
kTicketUrlBase              = "http://core.linn.co.uk/network/ticket/"
kReportUrlBase              = "http://products.linn.co.uk/restricted/site/device/exception/"
# Aws S3
kAwsBucketPrivate           = 'linn-artifacts-private'
kAwsBucketPublic            = 'linn-artifacts-public'
kAwsProductBase             = 'Volkano2Products/'
kAwsHardwareBase            = 'hardware/'
kJenkinsHardwareBuildDir    = 'install/AppBoard/release/bin'
kAwsElfBase                 = '/artifacts/builds/Volkano2'
kElfFileFilter              = '*.elf'


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
    os.chmod(aJsonFile, 0664)  # NOQA  allow group to write this file as it may be manually updated occasionally


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
        recipients = [sender]
    else:
        ccList = ['josh.hahn@linn.co.uk', 'graham.douglas@linn.co.uk']
    mail = email.mime.text.MIMEText( aText )
    mail['Subject'] = aSubject
    mail['From'] = sender
    mail['To'] = ', '.join( recipients )
    mail['Cc'] = ', '.join( ccList )
    s = smtplib.SMTP( 'exchange.linn.co.uk' )
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
    recipients = ['Test_Team@linn.co.uk']
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
    print "Dependecies for " + aRepo + " @ " + aVersion
    for obj in jsonObjs:
        print "    " + obj['name'] + ": " + obj['version']
    return jsonObjs


def UploadFilesToCdn(aDryRun):
    Info( 'Upload files from %s to %s' % ( kCdnRsyncLocalDir,  kCdnWwwDestination) )
    rsyncOptions = ['--itemize-changes', '--recursive', '--cvs-exclude', '--delete', '--checksum', '--copy-links', '--perms', '--times', '--verbose', '--exclude=/konfig/assets.*', '--exclude=/konfig/devassets.*']  # --cvs-exclude suppresses .svn/ and much other junk
    exeRsync = 'rsync'.split()
    if aDryRun:
        exeRsync.append( '--dry-run')
    for option in rsyncOptions:
        exeRsync.append( option )
    exeRsync.append( kCdnRsyncLocalDir )
    exeRsync.append( kCdnWwwDestination )
    subprocess.check_call( exeRsync )


def CopyFileWithPermissions(aSource, aDestination):
    import grp
    subprocess.check_call(['sudo', 'cp', '--preserve=mode', aSource, aDestination])
    try:
        subprocess.check_call(['sudo', 'chown', '%d:%d' % (os.geteuid(), grp.getgrnam('products').gr_gid), aDestination])
    except:
        subprocess.check_call(['sudo', 'chown', '%d:%d' % (os.geteuid(), os.getegid()), aDestination])


def Md5Hash(aFile):
    cmdLineMd5 = ['/usr/bin/md5sum', aFile]
    p = subprocess.Popen(args=cmdLineMd5, stdout=subprocess.PIPE)
    md5Hash = p.stdout.read().split()[0]  # disregard filename
    retVal = p.wait()
    if retVal:
        raise ToolError(cmdLineMd5)
    return md5Hash


def GetBitstreamVersion(aBitstreamFile, aMajorNumber):
    """Extract version number from given bitstream file."""
    f = open(aBitstreamFile, 'rt')
    data = f.read()
    f.close()
    ver = re.search(r'[0-9]+\.[0-9]+\.[0-9]+', data)
    if ver:
        return ver.group(0)
    return 'Unknown'


def CreateHtmlFile( aHtml, aHtmlFile, aPrintToScreen ):
    print( "Created html output file: %s" % aHtmlFile )
    f = open(aHtmlFile, 'wt')
    f.write( aHtml.encode('utf-8') )
    f.close()

    if aPrintToScreen:
        print aHtml


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


try:
    import boto3
except:
    print('\nAWS fetch requires boto3 module')
    print("Please install this using 'pip install boto3'\n")
else:
    awsSlave = False
    try:
        resp = requests.get( 'http://169.254.169.254/latest/meta-data/iam/info' )
        meta = json.loads( resp.text )
        if 'InstanceProfileArn' in meta:
            if 'dev-tools-EC2SlaveInstanceProfile' in meta['InstanceProfileArn']:
                awsSlave = True
    except:
        pass

    if not awsSlave:
        # create AWS credentials file (if not already present)
        home = None
        if 'HOMEPATH' in os.environ and 'HOMEDRIVE' in os.environ:
            home = os.path.join(os.environ['HOMEDRIVE'], os.environ['HOMEPATH'])
        elif 'HOME' in os.environ:
            home = os.environ['HOME']
        if home:
            awsCreds = os.path.join(home, '.aws', 'credentials')
            if not os.path.exists(awsCreds):
                if sys.version_info[0] == 2:
                    from urllib2 import urlopen
                else:
                    from urllib.request import urlopen
                try:
                    os.mkdir(os.path.join(home, '.aws'))
                except:
                    pass
                try:
                    credsFile = urlopen('http://core.linn.co.uk/aws-credentials' )
                    creds = credsFile.read()
                    with open(awsCreds, 'wt') as f:
                        f.write(creds)
                except:
                    pass


def DownloadFromAws( aKey, aDestinationFile, aBucket=kAwsBucketPrivate ):
    print( 'Download from AWS s3://%s/%s to %s' % ( aBucket, aKey, os.path.abspath( aDestinationFile ) ) )
    s3 = boto3.resource( 's3' )
    bucket = s3.Bucket( aBucket )
    with open( aDestinationFile, 'wb' ) as data:
        bucket.download_fileobj( aKey, data)


def UploadToAws( aKey, aSourceFile, aBucket=kAwsBucketPrivate, aDryRun=False ):
    print( 'Upload %s to AWS s3://%s/%s' % ( os.path.abspath( aSourceFile ), aBucket, aKey ) )
    s3 = boto3.resource('s3')
    bucket = s3.Bucket( aBucket )
    with open( aSourceFile, 'rb' ) as data:
        if not aDryRun:
            ext = aSourceFile.split(".")[-1]
            if ext in ["txt", "json", "xml"]:
                bucket.upload_fileobj(data, aKey, ExtraArgs={'ContentType': 'text/plain'})
            else:
                bucket.upload_fileobj(data, aKey)


def UploadRecursiveToAws( aSrcDir, aDstDir, aFileFilter="*", aDryRun=False ):
    import glob
    for f in glob.glob( os.path.join(aSrcDir, aFileFilter) ):
        elfFileKey = os.path.join( aDstDir, os.path.basename(f) )
        UploadToAws( elfFileKey, f, kAwsBucketPrivate, aDryRun)


def UploadToAwsDir( aDir, aSourceFile, aBucket=kAwsBucketPrivate, aDryRun=False ):
    key = os.path.join( aDir, os.path.basename(aSourceFile) )
    UploadToAws( key, aSourceFile, aBucket, aDryRun )


def CopyOnAws( aSourceKey, aDestKey, aBucket=kAwsBucketPrivate, aDryRun=False ):
    print( 'Copy from AWS (%s) %s to %s' % ( aBucket, aSourceKey, aDestKey ) )
    client = boto3.client('s3')
    if not aDryRun:
        client.copy_object(Bucket=aBucket, CopySource="%s/%s" % ( aBucket, aSourceKey ), Key=aDestKey)


def CopyRecursiveOnAws( aSourceDir, aDestDir, aBucket=kAwsBucketPrivate, aDryRun=False ):
    print( 'Copy Recursive on AWS (%s) %s to %s' % ( aBucket, aSourceDir, aDestDir ) )
    client = boto3.client('s3')

    objs = client.list_objects_v2( Bucket=aBucket, Delimiter='|', Prefix=aSourceDir.strip("/") )['Contents']
    for obj in objs:
        sourceKey = obj['Key']
        sourceFile = os.path.basename( sourceKey )
        destKey = os.path.join( aDestDir.strip("/"), sourceFile )
        CopyOnAws( sourceKey, destKey, aBucket, aDryRun )


def MoveOnAws( aSourceKey, aDestKey, aBucket=kAwsBucketPrivate, aDryRun=False ):
    print( 'Move on AWS (%s) %s to %s' % ( aBucket, aSourceKey, aDestKey ) )
    client = boto3.client('s3')
    if not aDryRun:
        client.copy_object(Bucket=aBucket, CopySource="%s/%s" % ( aBucket, aSourceKey ), Key=aDestKey)
        client.delete_object(Bucket=aBucket, Key=aSourceKey)


def MoveRecursiveOnAws( aSourceDir, aDestDir, aBucket=kAwsBucketPrivate, aDryRun=False ):
    client = boto3.client('s3')

    objs = client.list_objects_v2( Bucket=aBucket, Delimiter='|', Prefix=aSourceDir.strip("/") )['Contents']
    for obj in objs:
        sourceKey = obj['Key']
        sourceFile = os.path.basename( sourceKey )
        destKey = os.path.join( aDestDir.strip("/"), sourceFile )
        MoveOnAws( sourceKey, destKey, aBucket, aDryRun )


def CreateFile(aData, aFile):
    f = open(aFile, 'wt')
    f.write(aData)
    f.close()


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
    libdsVer = spotifyVer = libdsKey = spotifyKey = libdsFile = spotifyFile = None
    versionId = aVersion.split('.')[1]
    localDirTop = '%s-TestDs' % aVersion
    if not os.path.exists( localDirTop ):
        os.makedirs( localDirTop )

    for et in kEmulatorTypes:
        print "Emulator info: %s" % et
        localDirEt = os.path.join( localDirTop, '%s' % et["os"] )
        if not os.path.exists( localDirEt ):
            os.makedirs( localDirEt )
        for obj in jsonObjs:
            if obj['name'] == 'libds':
                libdsVer = obj['version']  # earliest windows variant is 0.102.723 as we weren't publishing this by default
                libdsFile = "libds-%s-%s-Release.tar.gz" % ( libdsVer, et["os"] )
                libdsKey = "libds/%s" % libdsFile
                libdsFile = os.path.join( localDirEt, libdsFile )
            elif obj['name'] == 'Spotify':
                spotifyVer = obj['version']
                spotifyFile = "spotify_embedded-v%s-%s-Release.tar.gz" % ( spotifyVer, et["os"] )
                spotifyKey = "spotify/repackaged/%s" % spotifyFile
                spotifyFile = os.path.join( localDirEt, spotifyFile )

        fail = False
        errorMsg = ''
        try:
            DownloadFromAws( libdsKey, libdsFile )
        except:
            errorMsg = "Could not download libds artifact from AWS: %s" % libdsKey
            fail = True

        try:
            DownloadFromAws( spotifyKey, spotifyFile )
        except:
            errorMsg = "Could not download Spotify artifact from AWS: %s" % spotifyFile
            fail = True

        if fail:
            print "\nERROR: %s" % errorMsg
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
            FROM ubuntu:16.04 AS libds_base

            RUN apt-get update; apt-get install -y libc6-i386 lib32stdc++6

            FROM libds_base

            ENV ROOM="davaar-{0}"
            ENV NAME="davaar-{0}"
            ENV DUMMY_BOARD_INDEX=80
            ENV SUBDOMAIN_PREFIX="beta"

            ADD libds-{1}-{3}-Release.tar.gz /opt
            # Extracted from spotify_embedded-v{2}-{3}-Release.tar.gz
            ADD libspotify_embedded_shared.so /opt/libds/bin
            RUN chmod +x /opt/libds/bin/TestDs

            WORKDIR /opt/libds

            ENTRYPOINT ./bin/TestDs --ui ui/AkurateIcons/ --cloud ${{DUMMY_BOARD_INDEX}} --name ${{NAME}} --room ${{ROOM}} --cloud-sub-domain ${{SUBDOMAIN_PREFIX}}
            """.format( versionId, libdsVer, spotifyVer, et["os"] )

            CreateFile( dockerData, os.path.join( localDirEt, 'Dockerfile' ) )
        else:
            tar = tarfile.open( libdsFile )
            tar.extractall( localDirEt )
            tar.close()
            os.remove( libdsFile )

            txtData = "libds\\bin\\TestDs.exe -r TestDs-%s -n SoftPlayer -l --ui libds\\ui\\AkurateIcons\\" % aVersion
            CreateFile( txtData, os.path.join( localDirEt, 'TestDs.bat' ) )

    if aCheckOnly:
        print "TestDs Emulator check succeeded"
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
        print "TestDs Emulator for %s available here: %s" % ( aVersion, os.path.abspath( tarOutputFile ) )
        if aDryRun:
            os.remove( tarOutputFile )
    else:
        uploadKey = 'Volkano2Products/%s' % tarOutputFile
        UploadToAws( uploadKey, tarOutputFile, aDryRun=aDryRun )

        os.remove( tarOutputFile )

        to = [ 'Robbie.Singer@linn.co.uk', 'Gareth.Griffiths@linn.co.uk', 'Simon.Chisholm@linn.co.uk' ]
        subj = "TestDs Emulator for %s Now Available" % aVersion
        text = "Download here: https://s3-eu-west-1.amazonaws.com/linn-artifacts-private/%s" % uploadKey
        SendEmail( subj, text, to, aDryRun )

# PublishTestDsEmulatorLocal( "4.63.223", aDryRun=False )
# SendPublishedEmail( 'Volkano1Fallback', '1.2.3', 'Volkano1FallbackAte', '', True )
