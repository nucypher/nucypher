FROM python:3.7.0-slim-stretch

# Update
RUN apt update -y && apt upgrade -y
RUN apt install gcc libffi-dev wget -y git

# Install pipenv
RUN apt install python3-pip -y
RUN pip3 install pipenv

# Set the working directory to /app
WORKDIR /app

# Copy the current directory contents into the container at /app
COPY . /app

# Fetch NuCypher
RUN git clone https://github.com/nucypher/nucypher
RUN cd nucypher

# Run pipenv
RUN pipenv install --dev --python python3.7 --skip-lock --verbose
RUN pipenv run ./nucypher/scripts/install_solc.sh

CMD ["/bin/bash"]
