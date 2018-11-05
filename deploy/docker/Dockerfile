FROM python:3.7.0-slim-stretch

# Update
RUN apt update -y && apt upgrade -y
RUN apt install gcc libffi-dev wget -y

# Install pipenv
RUN pip3 install pipenv

# Set the working directory to /app
WORKDIR /app

# Copy the current directory contents into the container at /app
COPY . /app

# Run pipenv
RUN pipenv install --dev --python python3.7 --skip-lock --verbose
RUN pipenv run ./scripts/install_solc.sh

CMD ["/bin/bash"]
