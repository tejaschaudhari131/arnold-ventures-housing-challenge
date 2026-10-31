.PHONY: setup run test data lab-data

setup:
	bash scripts/setup.sh

run:
	bash scripts/run.sh

test:
	bash scripts/test.sh

data:
	bash scripts/get_data.sh

lab-data:
	bash scripts/get_lab_data.sh
