"""Every string printed on the stamp caption and the signature certificate, English by default."""

from dataclasses import dataclass
from datetime import date, datetime

_EN_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
_ES_MONTHS = ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic")

_EN_EVENTS = (
    ("created", "Request created"),
    ("token_issued", "Signing link issued"),
    ("viewed", "Document viewed"),
    ("code_sent", "Verification code sent"),
    ("code_verified", "Verification code accepted"),
    ("code_failed", "Verification code rejected"),
    ("consent_given", "Consent given"),
    ("signed", "Signed"),
    ("declined", "Declined"),
    ("voided", "Voided"),
    ("expired", "Expired"),
    ("document_built", "Signed document built"),
    ("completed", "Completed"),
    ("copy_delivered", "Signed copy delivered"),
    ("downloaded", "Signed copy downloaded"),
    ("downloaded:original", "Original document downloaded"),
    ("link_sent", "Signing link sent"),
    ("reminder_sent", "Reminder sent"),
)
_ES_EVENTS = (
    ("created", "Solicitud creada"),
    ("token_issued", "Enlace de firma emitido"),
    ("viewed", "Documento visto"),
    ("code_sent", "Codigo de verificacion enviado"),
    ("code_verified", "Codigo de verificacion aceptado"),
    ("code_failed", "Codigo de verificacion rechazado"),
    ("consent_given", "Consentimiento otorgado"),
    ("signed", "Firmado"),
    ("declined", "Rechazado"),
    ("voided", "Anulado"),
    ("expired", "Vencido"),
    ("document_built", "Documento firmado generado"),
    ("completed", "Completado"),
    ("copy_delivered", "Copia firmada entregada"),
    ("downloaded", "Copia firmada descargada"),
    ("downloaded:original", "Documento original descargado"),
    ("link_sent", "Enlace de firma enviado"),
    ("reminder_sent", "Recordatorio enviado"),
)
_EN_METHODS = (
    ("link", "Private signing link"),
    ("app_link", "Private link issued by the sender"),
    ("email_code", "Emailed one-time code"),
    ("in_person", "In person"),
)
_ES_METHODS = (
    ("link", "Enlace de firma privado"),
    ("app_link", "Enlace privado emitido por el remitente"),
    ("email_code", "Codigo de un solo uso por correo"),
    ("in_person", "En persona"),
)
_EN_STATUS = (("pending", "Pending"), ("signed", "Signed"), ("declined", "Declined"))
_ES_STATUS = (("pending", "Pendiente"), ("signed", "Firmado"), ("declined", "Rechazado"))


@dataclass(frozen=True)
class CertificateLabels:
    # stamp
    stamp_caption: str = "Signed electronically by {name}, {date}, ref {ref}"
    months: tuple[str, ...] = _EN_MONTHS
    date_pattern: str = "{month} {day}, {year}"
    # certificate: headings and field names
    title: str = "Signature certificate"
    document: str = "Document"
    request_id: str = "Request ID"
    document_sha256: str = "Original document SHA-256"
    pages: str = "Pages"
    signers_heading: str = "Signers"
    name: str = "Name"
    email: str = "Email"
    role: str = "Role"
    status: str = "Status"
    method: str = "Signed via"
    witness: str = "Witnessed by"
    signed_at: str = "Signed at"
    ip: str = "IP address"
    user_agent: str = "Device"
    consent: str = "Consent"
    consent_sha256: str = "Consent SHA-256"
    signature: str = "Signature"
    typed_signature: str = "Typed signature"
    drawn_signature: str = "Drawn signature"
    signature_sha256: str = "Signature SHA-256"
    timeline_heading: str = "Event timeline"
    col_seq: str = "#"
    col_time: str = "Time (UTC)"
    col_event: str = "Event"
    col_signer: str = "Signer"
    consent_heading: str = "Consent text shown to the signer"
    verify_heading: str = "How to verify"
    verify_text: str = (
        "The SHA-256 of the final file is recorded by the issuing system. The event record is a hash chain; "
        "the head hash after the last signature is {head}."
    )
    page_of: str = "Certificate page {n} of {m}"
    zone_label: str = "UTC"
    continued: str = "(continued)"
    event_kinds: tuple[tuple[str, str], ...] = _EN_EVENTS
    methods: tuple[tuple[str, str], ...] = _EN_METHODS
    statuses: tuple[tuple[str, str], ...] = _EN_STATUS

    def format_date(self, day: date) -> str:
        return self.date_pattern.format(month=self.months[day.month - 1], day=day.day, year=day.year)

    def format_datetime(self, moment: datetime, zone_label: str | None = None) -> str:
        """``YYYY-MM-DD HH:MM:SS <zone label>`` for a datetime that is already in the wanted zone."""
        return f"{moment:%Y-%m-%d %H:%M:%S} {zone_label or self.zone_label}"

    def event_label(self, kind: str, detail: str | None = None) -> str:
        """The label of an event kind; ``kind:detail`` is tried first (e.g. ``downloaded:original``)."""
        known = dict(self.event_kinds)
        return known.get(f"{kind}:{detail}", known.get(kind, kind)) if detail else known.get(kind, kind)

    def method_label(self, method: str | None) -> str:
        return "" if method is None else dict(self.methods).get(method, method)

    def status_label(self, status: str) -> str:
        return dict(self.statuses).get(status, status)

    @classmethod
    def spanish(cls) -> "CertificateLabels":
        return cls(
            stamp_caption="Firmado electronicamente por {name}, {date}, ref {ref}",
            months=_ES_MONTHS,
            date_pattern="{day} {month} {year}",
            title="Certificado de firma",
            document="Documento",
            request_id="ID de solicitud",
            document_sha256="SHA-256 del documento original",
            pages="Paginas",
            signers_heading="Firmantes",
            name="Nombre",
            email="Correo",
            role="Funcion",
            status="Estado",
            method="Firmado mediante",
            witness="Presenciado por",
            signed_at="Firmado el",
            ip="Direccion IP",
            user_agent="Dispositivo",
            consent="Consentimiento",
            consent_sha256="SHA-256 del consentimiento",
            signature="Firma",
            typed_signature="Firma escrita",
            drawn_signature="Firma dibujada",
            signature_sha256="SHA-256 de la firma",
            timeline_heading="Cronologia de eventos",
            col_time="Hora (UTC)",
            col_event="Evento",
            col_signer="Firmante",
            consent_heading="Texto de consentimiento mostrado al firmante",
            verify_heading="Como verificar",
            verify_text=(
                "El SHA-256 del archivo final lo registra el sistema emisor. El registro de eventos es una "
                "cadena de hashes; el hash de cabecera tras la ultima firma es {head}."
            ),
            page_of="Página del certificado {n} de {m}",
            continued="(continuacion)",
            event_kinds=_ES_EVENTS,
            methods=_ES_METHODS,
            statuses=_ES_STATUS,
        )
