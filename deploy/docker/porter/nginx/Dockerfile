FROM nginxproxy/nginx-proxy:alpine

# Copy porter.local virtual host location configuration file
COPY ./deploy/docker/porter/nginx/porter.local_location /etc/nginx/vhost.d/
