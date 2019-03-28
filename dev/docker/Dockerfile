FROM python:3.7.0
ENV PYTHONUNBUFFERED 1

# Update
RUN apt-get update -y && apt-get upgrade -y && apt-get install gcc libffi-dev wget git -y

EXPOSE 11500

# add local files needed for install
RUN mkdir /code
WORKDIR /code
ADD dev-requirements.txt /code/dev-requirements.txt
ADD ./scripts/installation/install_solc.sh /code/install_solc.sh

# install reqs and solc
RUN pip install --upgrade pip \
    && pip3 install -r dev-requirements.txt --src /usr/local/src \
    && ./install_solc.sh

# finish install with some local volume ops
CMD ["./dev/docker/scripts/install/entrypoint.sh"]
