FROM nucypher/rust-python:3.12.0

# Build args
USER $USER
WORKDIR /app

# Install dependencies
COPY requirements.txt /app
RUN pip3 install --upgrade pip
RUN pip3 install --no-cache-dir -r requirements.txt

# Install from source
COPY . /app
RUN pip3 install . --no-deps
RUN rm -rf /app

# Setup the decicated user
RUN groupadd -g 10001 ursula
RUN useradd -u 10000 -g 10001 -m -s /bin/bash ursula
ENV PATH="/home/ursula/.local/bin:${PATH}"

# Switch to the dedicated user
WORKDIR /home/ursula
USER ursula

CMD ["/bin/bash"]
