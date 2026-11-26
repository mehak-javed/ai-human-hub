"""GitHub calls this when one of our issues is closed or reopened (G4).

Anyone can reach this URL, so a delivery is trusted only if its signature
matches our secret. No user is signed in: GitHub itself is the caller.
"""

import json
import logging

from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .progress import apply_issue_event, valid_signature

logger = logging.getLogger(__name__)

HANDLED_ACTIONS = {"closed", "reopened"}


@csrf_exempt
@require_POST
def github_webhook(request):
    secret = settings.GITHUB_WEBHOOK_SECRET
    if not secret:
        return JsonResponse({"detail": "The GitHub webhook isn't set up."}, status=503)
    if not valid_signature(secret, request.body, request.headers.get("X-Hub-Signature-256", "")):
        logger.warning("Rejected a GitHub webhook with a bad signature.")
        return JsonResponse({"detail": "Bad signature."}, status=401)

    event = request.headers.get("X-GitHub-Event", "")
    if event == "ping":
        return JsonResponse({"ok": True})
    try:
        payload = json.loads(request.body)
    except ValueError:
        return JsonResponse({"detail": "The body isn't JSON."}, status=400)
    if event != "issues" or payload.get("action") not in HANDLED_ACTIONS:
        # Signed, but nothing we act on.
        return HttpResponse(status=204)
    return JsonResponse({"updated": apply_issue_event(payload)})
