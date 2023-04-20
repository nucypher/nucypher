FROM nucypher/rust-python:3.8.16

# set default user
USER $USER

WORKDIR /code
COPY . /code

RUN pip3 install .[ursula]
RUN pip3 install --force-reinstall nucypher-core@git+https://github.com/KPrasch/nucypher-core.git@b2a56784f41e89b702e74c14a56f461c9b8a233f#subdirectory=nucypher-core-python
RUN pip3 install --force-reinstall ferveo@git+https://github.com/nucypher/ferveo.git@2a69e64965c9825765c305c0e6ae7f168af26900#subdirectory=ferveo-python
RUN export PATH="$HOME/.local/bin:$PATH"

CMD ["/bin/bash"]
