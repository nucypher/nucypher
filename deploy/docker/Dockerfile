FROM nucypher/rust-python:3.12.0

# set default user
USER $USER

# set default in-container workdir
WORKDIR /code

# Layer 1: Install dependencies
COPY requirements.txt /code
RUN pip3 install --no-cache-dir -r requirements.txt

# Layer 2: Install nucypher entrypoint
COPY . /code
RUN pip3 install . --no-deps

# Layer 3: Set environment variables
RUN export PATH="$HOME/.local/bin:$PATH"
CMD ["/bin/bash"]
