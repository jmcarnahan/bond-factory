"""``/.well-known/apple-app-site-association`` and ``/.well-known/assetlinks.json`` for universal / app links.

The phone app's sign-in return address is ``https://<api>/app/return/<provider>``. iOS and Android check these two
files to hand that link to the app. Values come from the app's environment, never from the repo. Both answer
``application/json`` with a short cache, never redirect, and 404 when their list is empty.
"""

from collections.abc import Sequence

from fastapi import APIRouter
from fastapi.responses import JSONResponse

CACHE = {"Cache-Control": "public, max-age=300"}
_NOT_FOUND = {"detail": {"code": "not_found", "message": "Not found"}}


def well_known_router(*, apple_app_ids: Sequence[str], android_apps: Sequence[tuple[str, Sequence[str]]],
                      return_path_prefix: str = "/app/return/") -> APIRouter:
    """``apple_app_ids``: ``<TEAMID>.<bundle id>`` strings. ``android_apps``: ``(package, sha256 fingerprints)``."""
    router = APIRouter(include_in_schema=False)
    apple = [a for a in apple_app_ids if a]
    android = [(pkg, fps) for pkg, fps in ((p, [f for f in fp if f]) for p, fp in android_apps if p) if fps]

    @router.get("/.well-known/apple-app-site-association")
    def apple_app_site_association() -> JSONResponse:
        if not apple:
            return JSONResponse(_NOT_FOUND, status_code=404)
        body = {
            "applinks": {"details": [{"appIDs": apple, "components": [{"/": f"{return_path_prefix}*"}]}]},
            "webcredentials": {"apps": apple},
        }
        return JSONResponse(body, media_type="application/json", headers=CACHE)

    @router.get("/.well-known/assetlinks.json")
    def assetlinks() -> JSONResponse:
        if not android:
            return JSONResponse(_NOT_FOUND, status_code=404)
        body = [{"relation": ["delegate_permission/common.handle_all_urls"],
                 "target": {"namespace": "android_app", "package_name": pkg,
                            "sha256_cert_fingerprints": list(fingerprints)}} for pkg, fingerprints in android]
        return JSONResponse(body, media_type="application/json", headers=CACHE)

    return router
