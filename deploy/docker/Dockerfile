FROM python:3.7.0-slim-stretch

# Update
RUN apt update -y && apt upgrade -y
RUN apt install gcc libffi-dev wget -y

WORKDIR /code
COPY . /code

RUN pip3 install .[ursula]

CMD ["/bin/bash"]
