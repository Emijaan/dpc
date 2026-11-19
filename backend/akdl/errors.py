import logging

from rest_framework.response import Response
from rest_framework.views import exception_handler

log = logging.getLogger(__name__)


def safe_exception_handler(exc, context):
    """Return JSON errors without leaking internals."""
    response = exception_handler(exc, context)
    if response is None:
        log.exception("Unhandled API error", exc_info=exc)
        return Response({"error": "internal_error"}, status=500)
    return response

