"""Prepare/score offline benchmarks, or run an explicitly authorized paired API pilot."""
import argparse
import json
from pathlib import Path

from .oolong import PINS, compare, prepare
from .language import compare_languages, prime_doctor
from .artifacts import compare_artifacts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    task = commands.add_parser("prepare", help="Prepare a local JSONL export of OOLONG-synth test rows")
    task.add_argument("--raw-jsonl", required=True, type=Path)
    task.add_argument("--out", required=True, type=Path)
    task.add_argument("--dataset-revision", default=PINS["oolong_dataset"]["revision"])
    task.add_argument("--subset", required=True)
    task.add_argument("--context-len", required=True, type=int)
    task.add_argument("--count", default=10, type=int)
    task.add_argument("--seed", default=0, type=int)
    task.add_argument("--fixture", action="store_true")
    report = commands.add_parser("compare", help="Verify and independently score normalized result records")
    report.add_argument("--suite", required=True, type=Path)
    report.add_argument("--results", required=True, type=Path)
    report.add_argument("--out", required=True, type=Path)
    language = commands.add_parser("language-compare", help="Independently re-score a FIXTURE language pilot")
    language.add_argument("--run", required=True, type=Path)
    artifacts = commands.add_parser("artifact-compare", help="Independently re-score a FIXTURE artifact/reset test")
    artifacts.add_argument("--run", required=True, type=Path)
    commands.add_parser("prime-doctor", help="Inspect the pinned native Prime prerequisites without inference")
    official = commands.add_parser("prepare-official", help="Import pinned official public data; no inference")
    official.add_argument("--suite", choices=("oolong-synth", "oolong-pairs", "obliq-math", "longbench-pro"), required=True)
    official.add_argument("--role", choices=("dev", "heldout"), help="Exploratory suites: the pinned seeded split to prepare")
    official.add_argument("--cache", type=Path, required=True)
    official.add_argument("--out", type=Path, required=True)
    official.add_argument("--count", choices=(1, 10), type=int, default=1)
    official.add_argument("--context-len", type=int, default=32768)
    official.add_argument("--offline", action="store_true")
    official.add_argument("--label-counts", action="store_true",
                          help="Every whole-window label-count question of the pinned dev windows (count development)")
    official.add_argument("--coverage-dev", action="store_true", help="Fresh-window label-judgement suite with negative controls (evidence-coverage ablation)")
    official.add_argument("--verification-dev", action="store_true", help="Seeded comparison/count questions from the dev windows (verification ablation)")
    official.add_argument("--independent", choices=("dev", "heldout"),
                          help="Seeded sample over the pinned independent 32K synth windows")
    planning = commands.add_parser("paired-plan", help="Freeze one-case or ten-case inputs/caps; no inference")
    planning.add_argument("--suite", type=Path, required=True)
    planning.add_argument("--config", type=Path, required=True)
    planning.add_argument("--out", type=Path, required=True)
    checking = commands.add_parser("paired-preflight", help="Read-only readiness checks; no inference")
    live = commands.add_parser("paired-run", help="Exact transport-specific plan approval and strict gates required")
    for command in (checking, live):
        command.add_argument("--suite", type=Path, required=True)
        command.add_argument("--plan", type=Path, required=True)
    live.add_argument("--out", type=Path, required=True)
    live.add_argument("--authorize-api-plan")
    live.add_argument("--authorize-subscription-plan")
    fixture = commands.add_parser("paired-relay-fixture", help="Actual isolated native/SCI transport control; scripted responses only")
    fixture.add_argument("--out", type=Path, required=True)
    fixture.add_argument("--provider", choices=("anthropic-api", "claude-oauth-subscription"), default="anthropic-api")
    fixture.add_argument("--config", type=Path, help="Explicit model/rate/budget control; defaults to the original Sonnet fixture")
    contract = commands.add_parser("paired-contract-fixture",
                                   help="Aljure execution-contract switches through the real gateway and SCI; scripted responses only")
    contract.add_argument("--out", type=Path, required=True)
    contract.add_argument("--provider", choices=("anthropic-api", "claude-oauth-subscription"), default="claude-oauth-subscription")
    contract.add_argument("--config", type=Path, required=True)
    review = commands.add_parser("paired-review-fixture",
                                 help="Aljure review switches through the real gateway and SCI; scripted responses only")
    review.add_argument("--out", type=Path, required=True)
    review.add_argument("--provider", choices=("anthropic-api", "claude-oauth-subscription"), default="claude-oauth-subscription")
    review.add_argument("--config", type=Path, required=True)
    pilot = commands.add_parser("thesis-pilot-prepare", help="Thesis-pilot suite and development panel from pinned data; no inference")
    pilot.add_argument("--cache", type=Path, required=True)
    pilot.add_argument("--out", type=Path, required=True)
    pilot.add_argument("--offline", action="store_true")
    pilot.add_argument("--profile", choices=("thesis-pilot", "reuse-pilot"), default="thesis-pilot")
    tplan = commands.add_parser("trajectory-plan", help="Freeze the A/C/E trajectory plan; no inference")
    tplan.add_argument("--suite", type=Path, required=True)
    tplan.add_argument("--config", type=Path, required=True)
    tplan.add_argument("--out", type=Path, required=True)
    tcheck = commands.add_parser("trajectory-preflight", help="Read-only trajectory readiness checks; no inference")
    trun = commands.add_parser("trajectory-run", help="One phase of one trajectory; exact plan approval required")
    for command in (tcheck, trun):
        command.add_argument("--suite", type=Path, required=True)
        command.add_argument("--plan", type=Path, required=True)
    trun.add_argument("--out", type=Path, required=True)
    trun.add_argument("--trajectory", required=True, help="For example E-s101; run again after the cold restart to resume")
    trun.add_argument("--authorize-api-plan")
    trun.add_argument("--authorize-subscription-plan")
    troll = commands.add_parser("trajectory-rollback", help="Put an earlier committed library pin back in force; recorded")
    troll.add_argument("--out", type=Path, required=True)
    troll.add_argument("--trajectory", required=True)
    troll.add_argument("--to", required=True)
    troll.add_argument("--reason", required=True)
    tfixture = commands.add_parser("trajectory-acquisition-fixture",
                                   help="Proposal turn and promotion through the real gateway, SCI and promotion JVM; scripted responses only")
    tfixture.add_argument("--out", type=Path, required=True)
    tfixture.add_argument("--provider", choices=("anthropic-api", "claude-oauth-subscription"), default="claude-oauth-subscription")
    tfixture.add_argument("--config", type=Path, required=True)
    tnew = commands.add_parser("trajectory-new-records",
                               help="Score each arm-E pin on records no panel or earlier task held; isolated SCI, no inference")
    tnew.add_argument("--suite", type=Path, required=True)
    tnew.add_argument("--plan", type=Path, required=True)
    tnew.add_argument("--out", type=Path, required=True)
    rfixture = commands.add_parser("reuse-fixture",
                                   help="Pilot 1 arms S, D and P through the real gateway and SCI; scripted responses only")
    rfixture.add_argument("--out", type=Path, required=True)
    rfixture.add_argument("--provider", choices=("anthropic-api", "claude-oauth-subscription"), default="claude-oauth-subscription")
    rfixture.add_argument("--config", type=Path, required=True, help="The P (positive control) plan config")
    treport = commands.add_parser("trajectory-report", help="Thesis endpoints from recorded trajectories; no inference")
    treport.add_argument("--suite", type=Path, required=True)
    treport.add_argument("--out", type=Path, required=True)
    auditing = commands.add_parser("audit", help="Offline audit of suites, scorer, proofs and recorded runs; no inference")
    auditing.add_argument("--out", type=Path, help="Write the full JSON audit here (refuses to overwrite)")
    args = parser.parse_args()
    if args.command == "audit":
        from .audit import full_audit
        value = full_audit()
        if args.out:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            with args.out.open("x", encoding="utf-8") as stream:
                json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False, default=list)
                stream.write("\n")
        print(json.dumps({"suites": len(value["suites"]), "runs_audited": sum(r.get("status") == "audited" for r in value["runs"]),
                          "runs_reproduced": sum(bool(r.get("reproduced")) for r in value["runs"]),
                          "violations": value["violations"], "model_calls": 0}, indent=2))
        return 1 if value["violations"] else 0
    if args.command in ("prepare-official", "paired-plan", "paired-preflight", "paired-run", "paired-relay-fixture",
                        "paired-contract-fixture", "paired-review-fixture", "thesis-pilot-prepare", "trajectory-plan",
                        "trajectory-preflight", "trajectory-run", "trajectory-rollback", "trajectory-report",
                        "trajectory-new-records",
                        "trajectory-acquisition-fixture", "reuse-fixture"):
        from . import paired
        try:
            if args.command == "thesis-pilot-prepare":
                from .official import prepare_thesis_pilot, scan_exposed
                value = prepare_thesis_pilot(args.out, cache=args.cache, download=not args.offline, exposed=scan_exposed(),
                                             name=args.profile)
                value = {"suite_sha256": value["suite_sha256"], "output": str(args.out), "model_calls": 0}
            elif args.command == "trajectory-plan":
                value = paired.plan_trajectory(args.suite, args.config, args.out)
                value = {"plan_sha256": value["plan_sha256"], "authorized": False, "output": str(args.out), "model_calls": 0}
            elif args.command == "trajectory-preflight":
                value = paired.trajectory_preflight(args.plan, args.suite)
            elif args.command == "trajectory-run":
                value = paired.run_trajectory(args.plan, args.suite, args.out, args.trajectory,
                                              authorize_api_plan=args.authorize_api_plan,
                                              authorize_subscription_plan=args.authorize_subscription_plan)
            elif args.command == "trajectory-rollback":
                value = paired.rollback_trajectory(args.out, args.trajectory, args.to, args.reason)
            elif args.command == "trajectory-new-records":
                value = paired.trajectory_new_records(args.plan, args.suite, args.out)
                value = {"pooled": value["pooled"], "complete_trajectories": value["complete_trajectories"], "model_calls": 0}
            elif args.command == "trajectory-report":
                value = paired.trajectory_report(args.out, args.suite)
            elif args.command == "reuse-fixture":
                from .relay_fixture import run_reuse
                value = run_reuse(args.out, provider=args.provider, config_path=args.config)
            elif args.command == "trajectory-acquisition-fixture":
                from .relay_fixture import run_acquisition
                value = run_acquisition(args.out, provider=args.provider, config_path=args.config)
            elif args.command == "prepare-official":
                from .official import prepare_independent, prepare_label_counts, prepare_official
                if args.suite in ("obliq-math", "longbench-pro"):
                    from .exploratory import prepare_obliq, prepare_longbench
                    if not args.role:
                        raise ValueError("Exploratory suites need --role dev|heldout")
                    value = (prepare_obliq if args.suite == "obliq-math" else prepare_longbench)(
                        args.out, role=args.role, cache=args.cache, download=not args.offline)
                elif args.coverage_dev:
                    from .official import prepare_coverage_dev, scan_exposed_contexts
                    value = prepare_coverage_dev(args.out, cache=args.cache, download=not args.offline, exposed_contexts=scan_exposed_contexts())
                elif args.verification_dev:
                    from .official import prepare_verification_dev
                    value = prepare_verification_dev(args.out, cache=args.cache, context_len=args.context_len, download=not args.offline)
                elif args.label_counts:
                    value = prepare_label_counts(args.out, cache=args.cache, download=not args.offline)
                elif args.independent:
                    if args.suite != "oolong-synth":
                        raise ValueError("Independent window suites are OOLONG-synth only")
                    value = prepare_independent(args.out, role=args.independent, cache=args.cache,
                                                context_len=args.context_len, download=not args.offline)
                else:
                    value = prepare_official(args.out, suite=args.suite, cache=args.cache, count=args.count,
                                             context_len=args.context_len, download=not args.offline)
                value = {"suite_sha256": value["suite_sha256"], "output": str(args.out), "model_calls": 0}
            elif args.command == "paired-plan":
                value = paired.plan(args.suite, args.config, args.out)
                value = {"plan_sha256": value["plan_sha256"], "authorized": False, "output": str(args.out), "model_calls": 0}
            elif args.command == "paired-preflight":
                value = paired.preflight(args.plan, args.suite)
            elif args.command == "paired-relay-fixture":
                from .relay_fixture import run
                value = run(args.out, provider=args.provider, config_path=args.config)
            elif args.command == "paired-contract-fixture":
                from .relay_fixture import run_contract
                value = run_contract(args.out, provider=args.provider, config_path=args.config)
            elif args.command == "paired-review-fixture":
                from .relay_fixture import run_review
                value = run_review(args.out, provider=args.provider, config_path=args.config)
            else:
                value = paired.run(args.plan, args.suite, args.out, authorize_api_plan=args.authorize_api_plan,
                                   authorize_subscription_plan=args.authorize_subscription_plan)
            print(json.dumps(value, indent=2, allow_nan=False))
            return 2 if value.get("ready") is False or value.get("status") == "FAILED" else 0
        except (ValueError, OSError, KeyError, RuntimeError) as error:
            print(json.dumps({"error": str(error), "command": args.command}))
            return 2
    if args.command in ("language-compare", "artifact-compare", "prime-doctor"):
        try:
            value = ({"language-compare": compare_languages, "artifact-compare": compare_artifacts}[args.command](args.run)
                     if args.command != "prime-doctor" else prime_doctor())
            print(json.dumps(value, indent=2, allow_nan=False))
            return 0 if args.command != "prime-doctor" or value["ready"] else 2
        except (ValueError, OSError, KeyError) as error:
            print(json.dumps({"error": str(error), "model_calls": 0}))
            return 2
    if args.command == "prepare":
        value = prepare(args.raw_jsonl, args.out, dataset_revision=args.dataset_revision,
                        subset=args.subset, context_len=args.context_len, count=args.count,
                        seed=args.seed, fixture=args.fixture)
    else:
        value = compare(args.suite, args.results)
        # Refuse to overwrite existing evidence.
        with args.out.open("x", encoding="utf-8") as stream:
            json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
            stream.write("\n")
    print(json.dumps({"command": args.command, "output": str(args.out), "model_calls": 0,
                      "learning_claim": False, "suite_sha256": value["suite_sha256"]}))


if __name__ == "__main__":
    raise SystemExit(main())
