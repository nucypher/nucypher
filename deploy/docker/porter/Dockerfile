FROM python:3.8.7-slim

# Update
RUN apt update -y && apt upgrade -y
RUN apt install patch gcc libffi-dev wget -y

WORKDIR /code
COPY . /code

# Porter requirements
RUN pip3 install .[porter]

CMD ["/bin/bash"]
