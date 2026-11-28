"""The default consent text. A starting point only: the adopting app owns the wording (not legal advice)."""

from bond_esign.types import Consent

CONSENT_VERSION = "bond-esign-consent/1"

_EN = (
    "I agree to receive and sign this document electronically. I understand that typing or drawing my "
    "signature here has the same effect as signing on paper. I can ask {company_name} for a paper copy at no "
    "charge by contacting {paper_contact}. I can decline by not signing. To open and save the signed document "
    "I need a device that can open and save a PDF file. {company_name} will provide me with a signed copy."
)
_ES = (
    "Acepto recibir y firmar este documento por medios electrónicos. Entiendo que escribir o dibujar mi firma "
    "aquí tiene el mismo efecto que firmar en papel. Puedo pedir a {company_name} una copia en papel sin "
    "ningún costo comunicándome con {paper_contact}. Puedo rechazar el documento si no lo firmo. Para abrir y "
    "guardar el documento firmado necesito un dispositivo que pueda abrir y guardar un archivo PDF. "
    "{company_name} me entregará una copia firmada."
)
_TEXTS = {"en": _EN, "es": _ES}


def default_consent(*, company_name: str, paper_contact: str, language: str = "en") -> Consent:
    if language not in _TEXTS:
        raise ValueError(f"no default consent text for language {language!r}; use one of {sorted(_TEXTS)}")
    text = _TEXTS[language].format(company_name=company_name, paper_contact=paper_contact)
    return Consent(version=CONSENT_VERSION, language=language, text=text)
