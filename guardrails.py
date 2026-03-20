from presidio_analyzer import AnalyzerEngine
from presidio_analyzer.nlp_engine import SpacyNlpEngine

_nlp_engine = SpacyNlpEngine(models=[{"lang_code": "en", "model_name": "en_core_web_lg"}])
_analyzer = AnalyzerEngine(nlp_engine=_nlp_engine, supported_languages=["en"])

_PII_ENTITIES = [
    "CREDIT_CARD",
    "US_SSN",
    "PHONE_NUMBER",
    "EMAIL_ADDRESS",
    "US_BANK_NUMBER",
    "US_DRIVER_LICENSE",
    "US_PASSPORT",
    "IP_ADDRESS",
    "IBAN_CODE",
]


def redact_pii(text: str) -> str:
    """Replace detected PII with <ENTITY_TYPE> placeholders."""
    results = _analyzer.analyze(
        text=text,
        entities=_PII_ENTITIES,
        language="en",
    )
    for result in sorted(results, key=lambda r: r.start, reverse=True):
        text = text[: result.start] + f"<{result.entity_type}>" + text[result.end :]
    return text

