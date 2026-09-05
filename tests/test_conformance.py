import json
from datetime import datetime
from pathlib import Path

from mnemox_control.canonical import canonical_json_bytes
from mnemox_control.contracts import OrderIntent, PolicyBundle
from mnemox_control.evaluator import evaluate
from mnemox_control.state import InstrumentCatalog, MarketSnapshot, TrustedAccountSnapshot

FIXTURE_ROOT = Path(__file__).parent / "conformance" / "v0.3"


def test_published_conformance_vectors_match_byte_for_byte() -> None:
    paths = sorted(FIXTURE_ROOT.glob("*.json"))
    assert [path.name for path in paths] == ["basic-allow.json", "multi-deny.json"]

    for path in paths:
        fixture = json.loads(path.read_text(encoding="utf-8"))
        inputs = fixture["inputs"]
        result = evaluate(
            policy=PolicyBundle.model_validate(inputs["policy"]),
            intent=OrderIntent.model_validate(inputs["intent"]),
            account=TrustedAccountSnapshot.model_validate(inputs["account"]),
            market=MarketSnapshot.model_validate(inputs["market"]),
            instruments=InstrumentCatalog.model_validate(inputs["instruments"]),
            evaluated_at=datetime.fromisoformat(inputs["evaluated_at"].replace("Z", "+00:00")),
        )

        assert result.model_dump(mode="json") == fixture["expected"]["result"]
        assert canonical_json_bytes(result).decode("utf-8") == fixture["expected"]["canonical_json"]
        assert result.content_hash == fixture["expected"]["content_hash"]
