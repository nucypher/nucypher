# Rust-Python CircleCI Container

### Setup
```bash
# the default username in the container
# circle ci expects the user "circleci"
export DOCKER_USER=<USERNAME>

# the version of python to build
export PYTHON_VERSION=<VERSION>
```

### Build
```bash
# pass local env vars as build args USER and VERSION
docker build -t nucypher/rust-python:$PYTHON_VERSION . \
--build-arg VERSION=${PYTHON_VERSION} \
--build-arg USER=${DOCKER_USER}
```

### Push
```bash
# docker login or authentication required
docker push nucypher/rust-python:$PYTHON_VERSION
```
