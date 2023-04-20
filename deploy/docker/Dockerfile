FROM nucypher/rust-python:3.8.16

# set default user
USER $USER

WORKDIR /code
COPY . /code

RUN pip3 install .[ursula]
RUN pip3 install --force-reinstall nucypher-core@git+https://github.com/KPrasch/nucypher-core.git@b2a56784f41e89b702e74c14a56f461c9b8a233f#subdirectory=nucypher-core-python
RUN pip3 install --force-reinstall ferveo@git+https://github.com/KPrasch/ferveo.git@7a5c5fc8be49894c0affd0da32b80e29e6e1ee8e#subdirectory=ferveo-python
RUN export PATH="$HOME/.local/bin:$PATH"

CMD ["/bin/bash"]
