FROM nucypher/rust-python:3.12.0

# set default user
USER $USER

WORKDIR /code
COPY . /code

RUN pip3 install .[ursula]
RUN export PATH="$HOME/.local/bin:$PATH"

CMD ["/bin/bash"]
