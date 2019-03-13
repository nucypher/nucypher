FROM python:3.7.0
ENV PYTHONUNBUFFERED 1

# Update
RUN apt update -y && apt upgrade -y && apt install gcc libffi-dev wget git -y

EXPOSE 11500

RUN mkdir /code
WORKDIR /code
ADD . /code

# install reqs and solc
RUN pip install --upgrade pip \
    && pip install pipenv \
    && pip3 install -r dev-requirements.txt --src /usr/local/src \
    && ./scripts/installation/install_solc.sh

# finish install with some local volume ops
CMD ["./dev/docker/scripts/install/entrypoint.sh"]