FROM nucypher/rust-python:3.13.7

# set default user
USER $USER

# update os
RUN sudo apt-get update -y
RUN sudo apt-get full-upgrade -y

# install git (for potential git dependencies - development convenience)
RUN sudo apt-get install -y git

# set default in-container workdir
WORKDIR /code

# Layer 1: Install dependencies
COPY requirements.txt /code
RUN pip3 install --upgrade pip
RUN pip3 install --no-cache-dir -r requirements.txt

# Layer 2: Install nucypher entrypoint
COPY . /code
RUN pip3 install . --no-deps

# Layer 3: Set environment variables
RUN export PATH="$HOME/.local/bin:$PATH"
CMD ["/bin/bash"]

# Layer 4: Build metadata
ARG GIT_COMMIT="unknown-commit"
ARG GIT_REF_NAME="unknown-ref-name"

ENV NUCYPHER_GIT_COMMIT=$GIT_COMMIT
ENV NUCYPHER_GIT_REF_NAME=$GIT_REF_NAME

LABEL org.opencontainers.image.revision=$GIT_COMMIT
LABEL org.opencontainers.image.version=$GIT_REF_NAME
