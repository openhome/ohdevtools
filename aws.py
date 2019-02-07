""" Interface to AWS S3 storage"""
import json
import os
import requests

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
                    creds = requests.get(kAwsLinnCredsUri).text
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
        """Copy objects to/from AWS. AWS uri in form s3://<bucket>/<key>"""
        if 's3://' in aSrc:
            bucket = self.s3.Bucket(aSrc.split('/')[2] )
            obj = bucket.Object('/'.join( aSrc.split('/')[3:]))
            with open(aDst, 'wb') as data:
                obj.download_fileobj(data)
        elif 's3://' in aDst:
            bucket = self.s3.Bucket(aDst.split('/')[2])
            with open(aSrc, 'rb') as data:
                ext = aSrc.split(".")[-1]
                if ext in ["txt", "json", "xml"]:
                    bucket.upload_fileobj(data, '/'.join(aDst.split('/')[3:]), ExtraArgs={'ContentType': 'text/plain'})
                else:
                    bucket.upload_fileobj(data, '/'.join(aDst.split('/')[3:]))

    def _delete(self, aBucket, aKey):
        if aKey is not None and len(aKey) > 0:
            bucket = self.s3.Bucket(aBucket)
            # this allows a single file to be deleted or an entire directory, so be careful!
            bucket.objects.filter(Prefix=aKey).delete()

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
                timestamp = str(item['LastModified'])
                entries.append({'key': item['Key'], 'modified': timestamp, 'size': item['Size']})
        return entries

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
        if prefix[-1] != '/':
            prefix += '/'
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
rm   = aws._delete

copy                 = aws._copy
download             = aws._download
delete               = aws._delete
exists               = aws._exists
listDetails          = aws._listItems
listDetailsRecursive = aws._listDetailsRecursive
listItems            = aws._listItems
listItemsRecursive   = aws._listItemsRecursive
