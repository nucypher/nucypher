.PHONY: clean-pyc clean-build

help:
	@echo "clean-build - remove build artifacts"
	@echo "clean-pyc - remove Python file artifacts"
	@echo "release - package and push a new release"
	@echo "dist - build wheels and source distribution"
	@echo "smoke-test - build a source distribution and spawn an active virtual environment"
	@echo "lock - Regenerate dependency locks"
	@echo "env - Regenerate locks and create a new development pipenv"
	@echo "install - Development installation via pipenv"

clean: clean-build clean-pyc

clean-build:
	rm -fr build/
	rm -fr dist/
	rm -fr *.egg-info

clean-pyc:
	find . -name '*.pyc' -exec rm -f {} +
	find . -name '*.pyo' -exec rm -f {} +
	find . -name '*~' -exec rm -f {} +

release: clean
    # Enable GPG signing of release commits
	CURRENT_SIGN_SETTING=$(git config commit.gpgSign)
	git config commit.gpgSign true
	# Let UPCOMING_VERSION be the version that is used for the current bump
	$(eval UPCOMING_VERSION=$(shell bumpversion $(bump) --dry-run --list | grep new_version= | sed 's/new_version=//g'))
	# Now generate the release notes to have them included in the release commit
	towncrier --yes --version $(UPCOMING_VERSION)
	# We need --allow-dirty because of the generated release_notes file but it is safe because the
	# previous dry-run runs *without* --allow-dirty which ensures it's really just the release notes
	# file that we are allowing to sit here dirty, waiting to get included in the release commit.
	bumpversion --allow-dirty $(bump)
	git push upstream main && git push upstream v$(UPCOMING_VERSION)
	# Restore the original system setting for commit signing
	git config commit.gpgSign "$(CURRENT_SIGN_SETTING)"

dist: clean
    # Build a source distribution and wheel
	python setup.py sdist bdist_wheel
	ls -l dist

smoke-test: clean
    # Build a source distribution and wheel then build a smoke test virtual env from the wheel
	python setup.py sdist bdist_wheel
	python scripts/release/test_package.py

lock: clean
    # Relock dependencies
	scripts/dependencies/relock_dependencies.sh

env: lock
    # Relock dependencies and generate a pipenv virtualenv from the result
	pipenv run pip install -e .[dev]
	pipenv shell
	nucypher --version

install: clean
	pipenv --rm
    # Development installation
	pipenv run pip install -e .[dev]
	# Show installed version and verify entry point
	pipenv shell
	nucypher --version
