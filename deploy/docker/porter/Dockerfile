FROM python:3.8.12-slim

# Update
RUN apt-get update -y && apt upgrade -y
RUN apt-get install patch gcc libffi-dev wget git -y

WORKDIR /code
COPY . /code

# Porter requirements
RUN pip3 install .[porter]

CMD ["/bin/bash"]
