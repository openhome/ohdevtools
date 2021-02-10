""" Interface to AWS S3 storage"""
import json
import os
import requests
import shutil

kAwsBucketPrivate   = 'linn-artifacts-private'
kAwsLinnCredsUri    = 'http://core.linn.co.uk/aws-credentials'
kAwsMetadataService = 'http://169.254.169.254/latest/meta-data/iam/info'

try:
    import boto3
except:
    print('\nAWS fetch requires boto3 module')
    print("Please install this using 'pip install boto3'\n")
else:
    awsSlave = False
    try:
        resp = requests.get(kAwsMetadataService, timeout=1)
        meta = json.loads(resp.text)
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
                try:
                    os.mkdir(os.path.join(home, '.aws'))
                except:
                    pass
                try:
                    resp = requests.get(kAwsLinnCredsUri)
                    if resp.status_code == 200:
                        creds = resp.text
                        with open(awsCreds, 'wt') as f:
                            f.write(creds)
                except:
                    pass

# ------------------------------------------------------------------------------
# 'Private' class to manage AWS using boto3 - public interface at end of file
# ------------------------------------------------------------------------------

class __aws:

    def __init__(self):
        self.s3 = boto3.resource('s3')
        self.client = boto3.client('s3')

    def _copy(self, aSrc, aDst):
        if 's3://' in aSrc and 's3://' in aDst:
            bucketSrc = aSrc.split('/')[2]
            keySrc = '/'.join(aSrc.split('/')[3:])
            bucketDst = aDst.split('/')[2]
            keyDst = '/'.join(aDst.split('/')[3:])
            self.client.copy_object(Bucket=bucketDst, Key=keyDst, CopySource="%s/%s" % (bucketSrc, keySrc))
        elif 's3://' in aSrc:
            bucket = self.s3.Bucket(aSrc.split('/')[2] )
            obj = bucket.Object('/'.join( aSrc.split('/')[3:]))
            try:
                outDir = os.path.dirname(aDst)
                if not os.path.exists( outDir ):
                    os.makedirs( outDir )
            except:
                pass
            with open(aDst, 'wb') as data:
                obj.download_fileobj(data)
        elif 's3://' in aDst:
            bucket = self.s3.Bucket(aDst.split('/')[2])
            with open(aSrc, 'rb') as data:
                ext = aSrc.split(".")[-1]
                if ext in ["txt", "json", "xml"]:
                    bucket.upload_fileobj(data, '/'.join(aDst.split('/')[3:]), ExtraArgs={'ContentType': 'text/plain'})
                elif ext in ["htm", "html"]:
                    bucket.upload_fileobj(data, '/'.join(aDst.split('/')[3:]), ExtraArgs={'ContentType': 'text/html'})
                else:
                    bucket.upload_fileobj(data, '/'.join(aDst.split('/')[3:]))
        else:
            shutil.copyfile(aSrc, aDst)

    def _delete(self, aItem):
        if 's3://' in aItem:
            bucket = aItem.split('/')[2]
            key = '/'.join(aItem.split('/')[3:])
            if key is not None and len(key) > 0:
                s3bucket = self.s3.Bucket(bucket)
                # this allows a single file to be deleted or an entire directory, so be careful!
                s3bucket.objects.filter(Prefix=key).delete()
        else:
            os.unlink( aItem )

    def _download(self, aKey, aDestinationFile, aBucket=kAwsBucketPrivate):
        print('Download from AWS s3://%s/%s to %s' % (aBucket, aKey.strip("/"), os.path.abspath(aDestinationFile)))
        bucket = self.s3.Bucket(aBucket)
        with open(aDestinationFile, 'wb') as data:
            bucket.download_fileobj(aKey.strip("/"), data)

    def _exists(self, aUri):
        exists = False
        bucket = aUri.split('/')[2]
        key = '/'.join(aUri.split('/')[3:])
        try:
            self.s3.Object(bucket, key).load()
            exists = True
        except:
            pass
        return exists

    def _listItems(self, aUri, aSort=None):
        """Return (non-recursive) directory listing of specified URI"""
        entries = []
        objects = self.__listObjs(aUri)
        if 'CommonPrefixes' in objects:
            for item in objects['CommonPrefixes']:
                entries.append(item['Prefix'])
        if 'Contents' in objects:
            for item in objects['Contents']:
                entries.append(item['Key'])
        if aSort is not None:
            entries = self.__sort(entries, aSort)
        return entries

    def _listItemsRecursive(self, aUri):
        """Return (non-recursive) directory listing of specified URI"""
        aUri = aUri.strip("/")
        entries = []
        objects = self.__listObjs(aUri)
        if 'CommonPrefixes' in objects:
            for item in objects['CommonPrefixes']:
                entries.append(item['Prefix'])
                entries.extend(self._listItemsRecursive(aUri + '/' + item['Prefix'].split('/')[-2]))
        if 'Contents' in objects:
            for item in objects['Contents']:
                entries.append(item['Key'])
        return entries

    def _listDetails(self, aUri):
        """Return (non-recursive) directory listing of specified URI"""
        entries = []
        objects = self.__listObjs(aUri)
        if 'CommonPrefixes' in objects:
            for item in objects['CommonPrefixes']:
                entries.append({'key': item['Prefix']})
        if 'Contents' in objects:
            for item in objects['Contents']:
                try:
                    timestamp = int(item['LastModified'].timestamp())
                except:
                    # handle obsolete python versions (but rsync method below now unreliable)
                    timestamp = str(item['LastModified'])
                entries.append({'key': item['Key'], 'modified': timestamp, 'size': item['Size']})
        return entries

    def _listDetailsRecursive(self, aUri):
        """Return detailed recursive directory listing of specified URI (ls -lr)"""
        entries = []
        objects = self.__listObjs(aUri)
        if 'CommonPrefixes' in objects:
            for item in objects['CommonPrefixes']:
                entries.append({'key': item['Prefix']})
                entries.extend(self._listDetailsRecursive(aUri + '/' + item['Prefix'].split('/')[-2]))
        if 'Contents' in objects:
            for item in objects['Contents']:
                try:
                    timestamp = int(item['LastModified'].timestamp())
                except:
                    # handle obsolete python versions (but rsync method below now unreliable)
                    timestamp = str(item['LastModified'])
                entries.append({'key': item['Key'], 'modified': timestamp, 'size': item['Size']})
        return entries

    def _move(self, aSrc, aDst):
        self._copy(aSrc, aDst)
        self._delete(aSrc)

    def _rsync(self, aSrc, aDst):
        """Perform an rsync operation - mirror contents of aSrc to aDst, only
           transferring files which have changed (in terms of timestamp)"""
        if 's3://' in aSrc:
            srcFiles = self.__s3FileList( aSrc )
        else:
            srcFiles = self.__fsFileList( aSrc )

        if 's3://' in aDst:
            dstFiles = self.__s3FileList(aDst)
        else:
            dstFiles = self.__fsFileList( aDst )

        for src in srcFiles:    # copy in new or updated src files to dst
            if 'size' in src:
                doCopy = True
                for dst in dstFiles:
                    if dst['name'] == src['name']:
                        if src['modified'] < dst['modified']:
                            print('Skipping %s' % src['path'])
                            doCopy = False
                            break
                if doCopy:
                    dstPath = aDst + '/' + src['name']
                    print('Copying %s -> %s' % (src['path'], dstPath))
                    self._copy(src['path'], dstPath)

        for dst in dstFiles:    # remove dst files not present in src list
            doDel = True
            for src in srcFiles:
                if dst['name'] == src['name']:
                    doDel = False
                    break
            if doDel:
                print('Deleting %s' % dst['path'])
                os.unlink(dst['path'])

        if 's3://' not in aDst:
            for root, dirs, _files in os.walk(aDst):
                for dir in dirs:
                    path = os.path.join(root, dir)
                    if not os.listdir(path):
                        os.rmdir(path)

    # Helper methods ----------------------------------

    @staticmethod
    def __cmpKey(aStr):
        """Key to compare version numbers in format NN.NNN.NNNNN"""
        verStr = aStr.strip("/").split("/")[-1]
        version = 0
        try:
            fields = verStr.split('_')[0].split('.')
            version = int(fields[0]) * 1000000000 + int(fields[1]) * 100000 + int(fields[2])
            # this is good for up to 1000 minor and 10000 build versions
        except:
            pass
        return version

    def __listObjs(self, aUri):
        fields = aUri.split('/')
        bucket = fields[2]
        prefix = '/'.join(fields[3:])
        if prefix:
            if prefix[-1] != '/':
                prefix += '/'
        else:
            prefix = ''     # top 'level' of bucket
        return self.client.list_objects_v2(Bucket=bucket, Delimiter='/', Prefix=prefix)

    def __sort(self, aItems, aSort):
        # NOTE that this wont work in python3 - need to use a 'key' function
        #      see functools.cmp_to_key
        sortedItems = None
        if 'asc' in aSort.lower():
            sortedItems = sorted(aItems, key=aws.__cmpKey)
        elif 'desc' in aSort.lower():
            sortedItems = sorted(aItems, key=aws.__cmpKey, reverse=True)
        return sortedItems

    @staticmethod
    def __listDiskFileDetailsRecursive(aSrc):
        items = []
        for root, _dirs, files in os.walk(aSrc):
            for name in files:
                path = os.path.join(root, name)
                stat = os.stat(path)
                items.append({'dir': dir, 'key': path, 'modified': int( stat.st_mtime ), 'size': stat.st_size})
        return items

    def __s3FileList(self, aSrc):
        bucket = aSrc.strip('s3://').split('/')[0]
        srcFiles = self._listDetailsRecursive(aSrc)
        for src in srcFiles:
            src['path'] = 's3://' + bucket + '/' + src['key']
            src['name'] = '/'.join(src['key'].split('/')[1:])
        return srcFiles

    def __fsFileList(self, aSrc):
        srcFiles = self.__listDiskFileDetailsRecursive( aSrc )
        prefixLen = len(aSrc) + 1
        for src in srcFiles:
            src['path'] = src['key']
            src['name'] = src['key'][prefixLen:].replace('\\', '/')
        return srcFiles

# ------------------------------------------------------------------------------
# Public interface to AWS (commands and aliases)
# ------------------------------------------------------------------------------

# NOTE that exists() method will return False for directories as they do not
#     actually exist as such on AWS, but are merely a prefix on existing keys

aws = __aws()

cp   = aws._copy
dir  = aws._listItems
ls   = aws._listItems
lsl  = aws._listDetails
lsr  = aws._listItemsRecursive
lslr = aws._listDetailsRecursive
mv   = aws._move
rm   = aws._delete

copy                 = aws._copy
download             = aws._download
delete               = aws._delete
exists               = aws._exists
listDetails          = aws._listItems
listDetailsRecursive = aws._listDetailsRecursive
listItems            = aws._listItems
listItemsRecursive   = aws._listItemsRecursive
move                 = aws._move
rsync                = aws._rsync


if __name__ == "__main__":

    # Don't change this 'test harness' - something in Volkano2 build depends on it
    import sys
    args = sys.argv
    if args[1] == "cp":
        cp(args[2], args[3])
