"""The example's e-signing tables (the mixins of bond_esign own the columns, keys and constraints).

The plain request mixin is used: the example has no company notion. An app with tenants builds the request from
`TenantEsignRequestMixin` instead.
"""

from bond_esign import EsignEventMixin, EsignRequestMixin, EsignSignerMixin

from ..db import Base


class EsignRequest(EsignRequestMixin, Base):
    pass


class EsignSigner(EsignSignerMixin, Base):
    pass


class EsignEvent(EsignEventMixin, Base):
    pass
