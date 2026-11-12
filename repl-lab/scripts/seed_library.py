"""Pilot 1 of research/UNBLOCK_ACQUISITION.md: build the seeded validated library. No model call.

The function is A1c arm 08's recorded `lab` (Sonnet 5.5, model-authored; Step 0's best transfer arm),
kept verbatim inside a controller adapter: its keywords become the task's label names, and its
:ent default becomes nil, as Step 0 counted it (undecided). The hardcoded record-index sets of
its step 8 are not taken: they name records of one context. The applicability predicate is
developer-written: the context header must declare the six trec_coarse labels. Both are checked
exactly as a model proposal is (acquisition seed-proposal), then promoted by the preregistered
rule on the controller-only development panel (acquisition promote), in fresh isolated workers.

    source var/worker.env && python3 scripts/seed_library.py A1C_ARM SUITE LIBRARY_DIR
"""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))
from benchmark.oolong import digest, encoded, read_suite, require  # noqa: E402
from benchmark.paired import EMPTY_LIBRARY, EMPTY_LIBRARY_SHA256, trajectory_spec  # noqa: E402
from benchmark.relay_fixture import REUSE_FUNCTION  # noqa: E402
from review_replay_ablation import form, sources  # noqa: E402

STEP, HEAD = 5, '(defn lab [t]'
LABELS = ('{:abb "abbreviation" :num "numeric value" :hum "human being" :loc "location" '
          ':desc "description and abstract concept"}')
ADAPTER = ('keyword-label-map-v1: the recorded lab form verbatim as a local fn; :abb :num :hum :loc :desc map to the '
           'label names; its :ent default maps to nil (undecided), as Step 0 counted it')
PREDICATE = ('(fn [input] (let [c (:context input) head (subs c 0 (min (count c) 2000))] '
             '(boolean (and (clojure.string/includes? head "6 categories") '
             '(every? (fn [l] (clojure.string/includes? head (str "\'" l "\'"))) '
             '["abbreviation" "description and abstract concept" "entity" "human being" "location" "numeric value"])))))')
DESCRIPTION = ('A1c arm 08 trec_coarse question rules (Sonnet 5.5): abbreviation, numeric value, human being, location or '
               'description; nil when no rule matches. Entity is never decided.')


def clj(command, request_path):
    done = subprocess.run(['python3', 'scripts/clj.py', '-m', 'repl-lab.acquisition', command, str(request_path)],
                          cwd=ROOT, capture_output=True, timeout=1500)
    reply = json.loads((done.stdout or b'{}').decode().strip().splitlines()[-1])
    require(done.returncode == 0 and 'error' not in reply, f'{command} failed: {reply.get("error")}')
    return reply


def main(arm, suite, library_dir):
    arm, library = Path(arm), ROOT / library_dir
    require(not library.exists(), 'Library exists; prior evidence must remain unchanged')
    source = sources(arm)[STEP]
    start = source.index(HEAD)
    defn = form(source, start)
    body = defn[len(HEAD):-1].strip()
    require(body.startswith('(let [s (clojure.string/lower-case t)]') and body.endswith(':else :ent))'),
            'The recorded lab form differs from the one Step 0 measured')
    function = f'(fn [text] (let [lab (fn [t] {body})] (get {LABELS} (lab text))))'
    manifest, _, _ = read_suite(suite)
    panel = Path(suite) / 'controller/panel.json'
    require(digest(panel.read_bytes()) == manifest['files']['controller/panel.json'], 'Panel changed after suite preparation')
    rule = trajectory_spec(json.loads((ROOT / 'config/acquisition-pilot-sonnet.json').read_text()))['promotion_rule']
    (library / 'libraries').mkdir(parents=True)
    (library / 'libraries' / f'{EMPTY_LIBRARY_SHA256}.edn').write_bytes(EMPTY_LIBRARY)
    seeds = library / 'seeds'
    seeds.mkdir()
    seed = {'function-provenance': 'controller-generated', 'applicability-provenance': 'human-edit',
            'source-run': str(arm), 'source-step': STEP, 'source-sha256': hashlib.sha256(source.encode()).hexdigest(),
            'source-form-sha256': hashlib.sha256(defn.encode()).hexdigest(), 'source-author': 'model (A1c, Sonnet 5.5)',
            'adapter': ADAPTER, 'applicability-author': 'developer'}
    request = {'path': str(seeds / f'{REUSE_FUNCTION}.proposal.edn'), 'pin': EMPTY_LIBRARY_SHA256, 'name': REUSE_FUNCTION,
               'description': DESCRIPTION, 'function_source': function, 'applicability_source': PREDICATE, 'seed': seed}
    (seeds / 'seed-request.json').write_bytes(encoded(request))
    proposal = clj('seed-proposal', seeds / 'seed-request.json')
    promote = {'arm': 'E', 'library': str(library), 'pin': EMPTY_LIBRARY_SHA256, 'proposal': request['path'],
               'proposal_sha256': proposal['proposal-sha256'], 'task_id': f'seed-{REUSE_FUNCTION}', 'position': 0,
               'rule': rule, 'panel': str(panel.resolve()), 'panel_sha256': manifest['files']['controller/panel.json'],
               'assisted': True, 'structured_labels': False, 'seconds': 900}
    (seeds / 'promotion-request.json').write_bytes(encoded(promote))
    reply = clj('promote', seeds / 'promotion-request.json')
    receipt = json.loads((library / 'receipts' / f"{reply['receipt-sha256']}.json").read_text())
    report = {'model_calls': 0, 'decision': receipt['decision'], 'reasons': receipt['reasons'],
              'pin': receipt['pin-after'], 'receipt_sha256': reply['receipt-sha256'], 'proposal_sha256': proposal['proposal-sha256'],
              'candidate_panel': receipt.get('candidate-panel'), 'library_panel': receipt.get('library'),
              'validation_ms': receipt.get('validation-ms'), 'seed': seed}
    (seeds / 'seed-report.json').write_bytes(encoded(report))
    print(json.dumps(report, indent=1))
    require(receipt['decision'] == 'approved', 'The seed did not pass the preregistered rule; no library pin')


if __name__ == '__main__':
    main(*sys.argv[1:4])
