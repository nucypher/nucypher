FROM nucypher:latest

# Update
RUN apt update -y && apt upgrade -y

WORKDIR /code
COPY . /code

# Porter requirements
RUN pip3 install .[porter]

CMD ["/bin/bash"]
