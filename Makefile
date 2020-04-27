.PHONY: clean-pyc clean-build docs

docs:
	sphinx-apidoc -fME -o docs/source/api -t docs/source/apidoc . setup.py "*conftest*" "tests" "nucypher/utilities/*" "scripts"
	# sphinx-apidoc [OPTIONS] -o <OUTPUT_PATH> <MODULE_PATH> [EXCLUDE_PATTERN …]
	$(MAKE) -C docs clean
	$(MAKE) -C docs html
