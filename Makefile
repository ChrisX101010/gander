GOOSE ?= goose

.PHONY: all build verify adversarial differential benchmark clean

all: build

build:
	mkdir -p build
	$(GOOSE) check src/main.goose
	$(GOOSE) check src/windowed.goose
	$(GOOSE) check src/windowed_bench.goose
	$(GOOSE) build -o build/gander-global src/main.goose
	$(GOOSE) build -o build/gander-windowed src/windowed.goose
	$(GOOSE) build -o build/gander-windowed-bench src/windowed_bench.goose
	cargo build --release

adversarial: build
	python3 tools/adversarial_gate.py

differential: build
	python3 tools/differential_fuzz.py

verify: adversarial differential
	@echo "GANDER_VERIFY=GREEN"

benchmark: build
	python3 tools/gen_workload.py
	python3 tools/bench_compare.py

clean:
	rm -rf build
	cargo clean
