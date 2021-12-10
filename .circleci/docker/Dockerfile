FROM rust:slim-buster

# prepare container
RUN apt-get update -y
RUN apt-get install -y sudo

# setup user
ARG USER
RUN echo "Creating user $USER"
RUN adduser --disabled-password --gecos '' $USER
RUN adduser $USER sudo
RUN echo '%sudo ALL=(ALL) NOPASSWD:ALL' >> /etc/sudoers
RUN chown -R $USER /home/$USER

# install python build dependencies
RUN sudo apt-get install -y make build-essential libssl-dev zlib1g-dev libbz2-dev \
    libreadline-dev libsqlite3-dev wget curl llvm libncurses5-dev libncursesw5-dev \
    xz-utils tk-dev libffi-dev liblzma-dev git docker-compose

# get python
ARG VERSION
RUN echo "Building python version $VERSION"
RUN wget https://www.python.org/ftp/python/$VERSION/Python-$VERSION.tgz
RUN tar xzvf Python-$VERSION.tgz

# build python
WORKDIR Python-$VERSION
RUN ./configure --enable-optimizations
RUN make
RUN make install

# setup python
RUN cp python /bin
RUN apt-get install -y python3-openssl python3-dev

# setup rust
ENV CARGO_ROOT /usr/local/cargo
ENV PATH $CARGO_ROOT/bin:$PATH

# echo python and rust versions
RUN python3 --version && \
    cargo --version &&   \
    rustup --version &&  \
    rustc --version

# set default user
USER $USER
