.PHONY: setup run test data

setup:
	bash scripts/setup.sh

run:
	bash scripts/run.sh

test:
	bash scripts/test.sh

data:
	bash scripts/get_data.sh
