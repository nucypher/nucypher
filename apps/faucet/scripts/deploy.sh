yarn run build
echo "pushing to S3"
aws s3 sync dist s3://nucypher-faucet-dev --cache-control max-age=172800 --acl public-read --delete