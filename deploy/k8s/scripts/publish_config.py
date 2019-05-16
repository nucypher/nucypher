import os
import boto3

tar_filename = '{}@{}.tar.gz'.format(
    os.getenv('ACCOUNT_ADDRESS'),
    os.getenv('MY_IP')
)
tarfile = os.path.join('/mnt/data/', tar_filename)

s3_client = boto3.client('s3')
s3_client.upload_file(tarfile, os.getenv('NUCYPHER_CONFIG_UPLOAD_BUCKET'), tar_filename)
