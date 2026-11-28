"""The panel's visible strings (English defaults, Spanish on request); re-exported by ``webform``."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PanelLabels:
    """Every visible string of the panel. ``signing_as`` may contain ``{name}``."""

    heading: str = "Sign this document"
    signing_as: str = "Signing as {name}"
    name_label: str = "Your full name"
    consent_label: str = "I have read the above and I agree to sign this document electronically."
    mode_label: str = "How do you want to sign?"
    draw_tab: str = "Draw"
    type_tab: str = "Type"
    canvas_label: str = "Draw your signature in the box"
    clear: str = "Clear"
    submit: str = "Sign and accept"
    typed_preview_label: str = "Your signature will look like this"
    signed_message: str = "Thank you. This document is signed."
    not_available_expired: str = "This signing link has expired. Please ask for a new one."
    not_available_not_open: str = "This document can no longer be signed."
    not_available_generic: str = "This document cannot be signed right now."
    code_needed: str = "Please enter the code we sent you before signing."
    noscript_hint: str = "Without JavaScript you can sign by typing your full name."
    noscript_draw_only: str = "JavaScript is needed to draw your signature. Please turn it on and reload this page."
    decline_summary: str = "Decline to sign"
    decline_reason_label: str = "Reason (optional)"
    decline_submit: str = "Decline"
    declined_message: str = "You declined to sign this document. Nothing was signed."

    @classmethod
    def spanish(cls) -> PanelLabels:
        return cls(
            heading="Firme este documento",
            signing_as="Firmando como {name}",
            name_label="Su nombre completo",
            consent_label="He leído lo anterior y acepto firmar este documento electrónicamente.",
            mode_label="¿Cómo desea firmar?",
            draw_tab="Dibujar",
            type_tab="Escribir",
            canvas_label="Dibuje su firma en el recuadro",
            clear="Borrar",
            submit="Firmar y aceptar",
            typed_preview_label="Su firma se verá así",
            signed_message="Gracias. Este documento está firmado.",
            not_available_expired="Este enlace de firma ha vencido. Pida uno nuevo.",
            not_available_not_open="Este documento ya no se puede firmar.",
            not_available_generic="Este documento no se puede firmar en este momento.",
            code_needed="Ingrese el código que le enviamos antes de firmar.",
            noscript_hint="Sin JavaScript puede firmar escribiendo su nombre completo.",
            noscript_draw_only=(
                "Se necesita JavaScript para dibujar su firma. Actívelo y vuelva a cargar esta página."
            ),
            decline_summary="Rechazar la firma",
            decline_reason_label="Motivo (opcional)",
            decline_submit="Rechazar",
            declined_message="Usted rechazó firmar este documento. No se firmó nada.",
        )
