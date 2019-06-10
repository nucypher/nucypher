FROM python:3.7.3
ENV PYTHONUNBUFFERED 1
ENV PYTHONPATH /code

# Update
RUN apt-get update -y && apt-get upgrade -y && apt-get install gcc libffi-dev wget git -y

# make an install directory
RUN mkdir /install
WORKDIR /install

# copy only the exact files needed for install into the container
COPY ./nucypher/__about__.py /install/nucypher/
COPY README.md /install
COPY setup.py /install
COPY scripts/installation/install_solc.sh /install
COPY dev-requirements.txt /install
COPY requirements.txt /install
COPY dev/docker/scripts/install/entrypoint.sh /install

# install reqs and solc
RUN pip install --upgrade pip
RUN pip3 install -r /install/dev-requirements.txt --src /usr/local/src
RUN /install/install_solc.sh

# puts the nucypher executable in bin path
RUN python /install/setup.py develop

# this gets called after volumes are mounted and so can modify the local disk
CMD ["/install/entrypoint.sh"]
