FROM nucypher/rust-python:3.8.9

WORKDIR /code
COPY . /code

RUN pip3 install .[ursula]
RUN export PATH="$HOME/.local/bin:$PATH"

CMD ["/bin/bash"]
