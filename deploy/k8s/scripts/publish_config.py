import os
import boto3

ROOT_DIR = os.getenv('ROOT_DIR')

tar_filename = '{}@{}.tar.gz'.format(
    os.getenv('ACCOUNT_ADDRESS'),
    os.getenv('MY_IP')
)
tarfile = os.path.join(ROOT_DIR, tar_filename)

s3_client = boto3.client('s3')
s3_client.upload_file(tarfile, os.getenv('NUCYPHER_CONFIG_UPLOAD_BUCKET'), tar_filename)
