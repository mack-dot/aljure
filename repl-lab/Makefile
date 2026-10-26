.PHONY: doctor test fixture-demo evolve evaluate cold-boot replay demo isolation-test
CLJ = python3 scripts/clj.py
doctor:
	$(CLJ) -m repl-lab.main doctor
test:
	$(CLJ) -m repl-lab.test-runner
fixture-demo:
	$(CLJ) -m repl-lab.main fixture-demo
evolve:
	@LIVE='$(LIVE)' MODEL='$(MODEL)' MAX_USD='$(MAX_USD)' $(CLJ) -m repl-lab.main evolve
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
