# Stage 1: Build Image
FROM rust:alpine as builder

# Install dependencies
RUN apk update && apk add --no-cache expat libffi musl-dev libgcc libstdc++ openssl

WORKDIR /nucypher

# Install python + dependencies
COPY --from=python:3.12.2-alpine3.18 /usr/local /usr/local
COPY requirements.txt .
RUN pip3 install --no-cache-dir --upgrade pip && \
    pip3 install --no-cache-dir -r requirements.txt

# Install source code + cleanup
COPY . .
RUN pip3 install --no-cache-dir --no-deps /nucypher && rm -rf /nucypher

# Stage 2: User Image
FROM python:3.12.2-alpine3.18 as user
COPY --from=builder /usr/local/lib/ /usr/local/lib/
COPY --from=builder /usr/lib /usr/lib
COPY --from=builder /usr/local/bin/ /usr/local/bin/
COPY --from=builder /usr/bin /usr/bin

# Install dependencies
RUN apk update && apk add --no-cache bash expat libffi openssl

# Dedicate a user to run the service
ARG USER=ursula
RUN addgroup -g 10001 $USER && \
    adduser --disabled-password -u 10000 -G $USER $USER
ENV PATH="/home/$USER/.local/bin:${PATH}"
ENV HOME="/home/$USER"

# ship it
WORKDIR $HOME
USER $USER
ENTRYPOINT ["nucypher"]
CMD ["--version"]
