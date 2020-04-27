.PHONY: clean-pyc clean-build docs

docs:
	sphinx-apidoc -fo docs/source/api . setup.py "*conftest*" "tests" "nucypher/utilities/*" "scripts"
	# sphinx-apidoc [OPTIONS] -o <OUTPUT_PATH> <MODULE_PATH> [EXCLUDE_PATTERN …]
	$(MAKE) -C docs clean
	$(MAKE) -C docs html
