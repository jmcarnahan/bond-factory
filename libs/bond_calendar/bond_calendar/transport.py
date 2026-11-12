"""One HTTP call with the shared failure mapping (both providers use it)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx

from .errors import CalendarError, EtagMismatch, NotFound, ReconnectRequired, Unavailable


def error_detail(response: httpx.Response) -> tuple[str, str]:
    """(code, message) from a Graph or Google error body; never raises on odd bodies."""
    try:
        err = response.json().get("error")
    except (ValueError, AttributeError):
        err = None
    if isinstance(err, str):
        return err[:64], ""
    if not isinstance(err, dict):
        return f"http_{response.status_code}", ""
    reasons = [e.get("reason") for e in err.get("errors") or [] if isinstance(e, dict) and e.get("reason")]
    code = err.get("code") if isinstance(err.get("code"), str) else None
    return str(reasons[0] if reasons else code or err.get("status") or f"http_{response.status_code}")[:64], \
        str(err.get("message") or "")[:300]


def raise_for(response: httpx.Response) -> None:
    """Map a non-2xx answer to a typed error. Nothing here ever includes a token or a request body."""
    status = response.status_code
    if status < 400:
        return
    code, message = error_detail(response)
    if status == 401:
        raise ReconnectRequired(message or "The calendar provider refused the token.")
    if status in (404, 410):
        raise NotFound(message or "The event does not exist.", status=status)
    if status == 412:
        raise EtagMismatch(message or "The event changed since it was read.")
    if status == 429 or status >= 500:
        raise Unavailable(message or f"The calendar service answered {status}.", status=status)
    raise CalendarError(status, code, message)


def _send(http: httpx.Client, bearer: str, method: str, url: str, params: dict[str, Any] | None, json: Any,
          headers: dict[str, str] | None) -> httpx.Response:
    merged = {"Authorization": f"Bearer {bearer}", "Accept": "application/json", **(headers or {})}
    try:
        return http.request(method, url, params=params, json=json, headers=merged)
    except httpx.TimeoutException as exc:
        raise Unavailable("The calendar service timed out.", code="timeout", status=0) from exc
    except httpx.HTTPError as exc:
        raise Unavailable(f"The calendar service did not answer ({type(exc).__name__}).", status=0) from exc


def call(http: httpx.Client, token: Callable[[], str], method: str, url: str, *,
         params: dict[str, Any] | None = None, json: Any = None,
         headers: dict[str, str] | None = None, refresh: Callable[[], str] | None = None) -> httpx.Response:
    """Send with a bearer token; return the (2xx) response or raise a typed error.

    On a 401, when ``refresh`` is given, it is called once and the request is sent once more with the token it
    returns. A second 401 raises ``ReconnectRequired``. Nothing but a 401 is ever retried here."""
    response = _send(http, token(), method, url, params, json, headers)
    if response.status_code == 401 and refresh is not None:
        try:
            fresh = refresh()
        except CalendarError:
            raise
        except Exception as exc:
            raise ReconnectRequired("The calendar token could not be refreshed.") from exc
        response = _send(http, fresh, method, url, params, json, headers)
    raise_for(response)
    return response


def json_body(response: httpx.Response) -> dict[str, Any]:
    """The JSON object of a response; an empty or non-object body is ``{}``."""
    if not response.content:
        return {}
    try:
        data = response.json()
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}
