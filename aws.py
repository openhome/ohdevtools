""" Interface to AWS S3 storage"""
import os
import urllib2
try:
    import boto3
except:
    print('\nAWS fetch requires boto3 module')
    print("Please install this using 'pip install boto3'\n")
else:
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
            credsFile = urllib2.urlopen('http://core.linn.co.uk/~artifacts/artifacts/aws-credentials' )
            creds = credsFile.read()
            with open(awsCreds, 'wt') as f:
                f.write(creds)


def copy(aSrc, aDst):
    """Copy objects to/from AWS. AWS uri in form s3://<bucket>/<key>"""
    s3 = boto3.resource('s3')
    if 's3://' in aSrc:
        bucket = s3.Bucket(aSrc.split('/')[2])
        obj = bucket.Object('/'.join(aSrc.split('/')[3:]))
        with open(aDst, 'wb') as data:
            obj.download_fileobj(data)
    elif 's3://' in aDst:
        bucket = s3.Bucket(aDst.split('/')[2])
        with open( aSrc, 'rb' ) as data:
            bucket.upload_fileobj(data, '/'.join(aDst.split('/')[3:]))
