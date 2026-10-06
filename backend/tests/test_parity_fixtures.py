"""The TS Worker's golden parity files must match what the reviewed Python path produces now.

If this fails after an intentional Python change, regenerate with tools/parity_fixtures.py and
review the diff; never regenerate golden files from the TypeScript implementation.
"""

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import parity_fixtures  # noqa: E402

PARITY = ROOT.parent / "worker" / "test" / "parity"


def load(name: str):
    return json.loads((PARITY / name).read_text(encoding="utf-8"))


def roundtrip(data):
    return json.loads(json.dumps(data, ensure_ascii=False))


def test_adversarial_golden_file_is_current():
    assert load("adversarial.json") == roundtrip(parity_fixtures.adversarial_cases())


def test_offer_golden_file_is_current():
    assert load("offer.json") == roundtrip(parity_fixtures.offer_case())


def test_prompt_golden_file_is_current():
    prompt = load("prompt.json")
    assert prompt["systemPrompt"] == parity_fixtures.SYSTEM_PROMPT
    assert prompt["outputSchema"] == roundtrip(parity_fixtures.OUTPUT_SCHEMA)
    assert prompt["promptVersion"] == parity_fixtures.COMPACT_PROMPT_VERSION
