import json
from typing import Optional

from schemas.prediction import ChartAnalysisReport, ChartStructureFeatures


class ChartAnalysisInterpreter:
    """
    Optional Gemini narrative over deterministic chart features only.
    Never invents prices/patterns; failures return the input report unchanged.
    """

    def __init__(self, api_key: str):
        self._api_key = api_key.strip()

    def enrich(self, features: ChartStructureFeatures) -> ChartStructureFeatures:
        if features.report is None or not features.data_ok:
            return features
        if not self._api_key:
            return features
        narrative = self._generate(features)
        if narrative is None:
            return features
        report = features.report.model_copy(update={"narrative": narrative})
        return features.model_copy(update={"report": report})

    def _generate(self, features: ChartStructureFeatures) -> Optional[str]:
        try:
            import google.generativeai as genai

            genai.configure(api_key=self._api_key)
            model = genai.GenerativeModel("gemini-1.5-flash")
            payload = {
                "structure_5m": features.structure_5m.value,
                "structure_15m": features.structure_15m.value,
                "setup": features.setup.value,
                "bias": features.bias.value,
                "action_hint": features.action_hint,
                "evidence": features.evidence,
                "patterns": [p.model_dump(mode="json") for p in features.patterns],
                "key_levels": [l.model_dump(mode="json") for l in features.key_levels],
                "trigger": features.trigger,
                "invalidation_price": features.invalidation_price,
                "invalidation_rule": features.invalidation_rule,
                "report": features.report.model_dump(mode="json") if features.report else None,
            }
            prompt = (
                "You explain NIFTY chart structure for a trading bot. "
                "Use ONLY the JSON facts provided. Do not invent patterns, prices, "
                "timestamps, or indicators. Return strict JSON: "
                '{"narrative":"..."}. Keep narrative under 120 words.\n\n'
                f"{json.dumps(payload, default=str)}"
            )
            response = model.generate_content(
                prompt,
                request_options={"timeout": 8},
            )
            text = (response.text or "").strip()
            return self._parse_narrative(text)
        except Exception:
            return None

    @staticmethod
    def _parse_narrative(text: str) -> Optional[str]:
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`")
            if cleaned.startswith("json"):
                cleaned = cleaned[4:].strip()
        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            return None
        if not isinstance(data, dict):
            return None
        narrative = data.get("narrative")
        if not isinstance(narrative, str) or not narrative.strip():
            return None
        return narrative.strip()
