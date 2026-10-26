"""Offline commands only. This entry point never calls a model provider."""
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
    args = parser.parse_args()
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
