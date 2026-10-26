.PHONY: doctor test fixture-demo smoke smoke-subscription evolve resume evaluate cold-boot replay demo worker-setup isolation-test isolation-recover
CLJ = python3 scripts/clj.py
doctor:
	$(CLJ) -m repl-lab.main doctor
test:
	$(CLJ) -m repl-lab.test-runner
fixture-demo:
	$(CLJ) -m repl-lab.main fixture-demo
smoke:
	@LIVE='$(LIVE)' MODEL='$(MODEL)' MAX_USD='$(MAX_USD)' $(CLJ) -m repl-lab.main smoke
smoke-subscription:
	@SMOKE_PROVIDER=claude-subscription LIVE='$(LIVE)' MODEL='$(MODEL)' MAX_USD='$(MAX_USD)' INPUT_USD_PER_M=2 OUTPUT_USD_PER_M=10 $(CLJ) -m repl-lab.main smoke
evolve:
	@LIVE='$(LIVE)' MODEL='$(MODEL)' MAX_USD='$(MAX_USD)' $(CLJ) -m repl-lab.main evolve
resume:
	@LIVE='$(LIVE)' MODEL='$(MODEL)' MAX_USD='$(MAX_USD)' $(CLJ) -m repl-lab.main resume '$(RUN_ID)'
evaluate:
	@LIVE='$(LIVE)' MODEL='$(MODEL)' MAX_USD='$(MAX_USD)' $(CLJ) -m repl-lab.main evaluate '$(EXPORT)' '$(PROFILE)'
cold-boot:
	@LIVE='$(LIVE)' MODEL='$(MODEL)' MAX_USD='$(MAX_USD)' $(CLJ) -m repl-lab.main cold-boot '$(EXPORT)'
replay:
	$(CLJ) -m repl-lab.main replay '$(RUN_ID)'
demo:
	$(CLJ) -m repl-lab.main demo '$(RUN_ID)'
isolation-test:
	python3 scripts/isolation.py test
worker-setup:
	python3 scripts/setup_worker.py
isolation-recover:
	python3 scripts/isolation.py recover

.PHONY: python-worker-setup python-isolation-test language-parity artifact-parity artifact-compare benchmark-fixtures benchmark-pilot benchmark-compare benchmark-report prime-doctor prime-worker-setup prime-isolation-test prime-fixture benchmark-live benchmark-learn benchmark-coldboot benchmark-prime
python-worker-setup:
	python3 scripts/setup_python_worker.py
python-isolation-test:
	python3 scripts/python_isolation.py test
language-parity:
	$(CLJ) -m repl-lab.language-benchmark parity '$(OUT)'
artifact-parity:
	$(CLJ) -m repl-lab.artifact-fixture run '$(OUT)'
artifact-compare:
	python3 -m benchmark artifact-compare --run '$(RUN)'
benchmark-fixtures:
	$(CLJ) -m repl-lab.language-benchmark fixtures '$(OUT)'
benchmark-pilot:
	$(CLJ) -m repl-lab.language-benchmark pilot '$(OUT)'
benchmark-compare:
	python3 -m benchmark language-compare --run '$(RUN)'
benchmark-report:
	python3 -m benchmark language-compare --run '$(RUN)'
prime-doctor:
	python3 -m benchmark prime-doctor
prime-worker-setup:
	python3 scripts/setup_prime.py
prime-isolation-test:
	python3 -m benchmark.prime.isolation
prime-fixture:
	python3 -m benchmark.prime.fixture --out '$(OUT)' --aljure-run '$(RUN)'
.PHONY: prime-recursive-fixture
prime-recursive-fixture:
	python3 -m benchmark.prime.fixture --recursive --out '$(OUT)' --aljure-run '$(RUN)'
.PHONY: gateway-fixtures
gateway-fixtures:
	$(CLJ) -m repl-lab.gateway-fixture '$(OUT)'
.PHONY: gateway-native-replay prime-http-fixture
gateway-native-replay:
	$(CLJ) -m repl-lab.gateway-fixture '$(OUT)' '$(RUN)'
prime-http-fixture:
	python3 -m benchmark.prime.fixture --recursive --http-provider --out '$(OUT)' --aljure-run '$(RUN)'
benchmark-live benchmark-learn benchmark-coldboot benchmark-prime:
	@echo '$@: NOT IMPLEMENTED. Live adapters, verified parity, and new explicit spending authorization are required.' >&2
	@exit 2
