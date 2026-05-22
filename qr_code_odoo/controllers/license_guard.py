"""
License enforcement for Vinc website controllers.

Instead of fragile controller inheritance, this module patches a license
check into the original controller methods at import time using a simple
decorator wrapper.
"""

import functools
import logging
from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


def _license_ok():
    """Return True if the Vinc license allows operation."""
    try:
        lic = request.env["vinc.license"].sudo()._get_license_record()
        return lic._effective_status() in ("active", "warning")
    except Exception:
        # During module install the table may not exist yet.
        return True


def _block_page():
    """Return an HTTP response for blocked public pages."""
    return request.render("qr_code_odoo.license_required_page", {}, status=503)


def _block_json():
    """Return a JSON error for blocked AJAX/JSON endpoints."""
    return {"error": True, "message": "Service temporarily unavailable."}


def license_required_http(fn):
    """Decorator: block HTTP route when unlicensed."""
    @functools.wraps(fn)
    def wrapper(self, *args, **kwargs):
        if not _license_ok():
            return _block_page()
        return fn(self, *args, **kwargs)
    return wrapper


def license_required_json(fn):
    """Decorator: block JSON route when unlicensed."""
    @functools.wraps(fn)
    def wrapper(self, *args, **kwargs):
        if not _license_ok():
            return _block_json()
        return fn(self, *args, **kwargs)
    return wrapper


def _patch_controllers():
    """Wrap target controller methods with license checks."""
    from .main import (
        QRCodeController,
        VCardController,
        ReviewController,
        LeadController,
        VCardFormController,
    )
    from .bulk_onboarding import BulkOnboardingController

    # HTTP routes — blocked with a 503 page
    _http_targets = [
        (QRCodeController,          "redirect_to_dynamic_url"),
        (QRCodeController,          "download_qr_code"),
        (VCardController,           "track_vcard_page_view"),
        (VCardController,           "download_vcard"),
        (VCardFormController,       "get_started_form_page"),
        (VCardFormController,       "handle_form_submission"),
        (BulkOnboardingController,  "bulk_onboard_index"),
        (BulkOnboardingController,  "bulk_onboard_page"),
        (BulkOnboardingController,  "submit_bulk_onboard"),
        (BulkOnboardingController,  "upload_file"),
        (BulkOnboardingController,  "activate_account"),
        (BulkOnboardingController,  "activate_account_submit"),
        (BulkOnboardingController,  "complete_vcard"),
        (BulkOnboardingController,  "complete_vcard_submit"),
    ]

    # JSON routes — blocked with an error dict
    _json_targets = [
        (ReviewController,          "create_review"),
        (LeadController,            "create_lead"),
        (LeadController,            "create_service_request"),
        (LeadController,            "get_service_questions"),
        (VCardFormController,       "generate_preview"),
        (VCardFormController,       "check_slug_availability"),
    ]

    for cls, method_name in _http_targets:
        original = getattr(cls, method_name, None)
        if original:
            setattr(cls, method_name, license_required_http(original))

    for cls, method_name in _json_targets:
        original = getattr(cls, method_name, None)
        if original:
            setattr(cls, method_name, license_required_json(original))


_patch_controllers()
