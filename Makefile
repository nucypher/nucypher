.PHONY: clean-pyc clean-build docs

docs:
	$(MAKE) -C docs clean
	$(MAKE) -C docs html
