import base64
import os

from odoo import http
from odoo.http import request
from odoo.modules.module import get_module_path

from ..models.brand_config import (
    ATTACHMENT_BRAND_ICON,
    ATTACHMENT_BRAND_WORDMARK,
)

CACHE_HEADERS = [('Cache-Control', 'public, max-age=3600')]
DEFAULT_ICON_RELPATH = 'static/description/icon.png'


class VincBrandingController(http.Controller):

    @http.route('/qr_code_odoo/brand/icon', type='http', auth='public', csrf=False)
    def brand_icon(self, **kw):
        return self._serve(ATTACHMENT_BRAND_ICON, fallback_static=DEFAULT_ICON_RELPATH)

    @http.route('/qr_code_odoo/brand/wordmark', type='http', auth='public', csrf=False)
    def brand_wordmark(self, **kw):
        # Wordmark falls back to icon attachment, then to bundled default icon.
        return self._serve(
            ATTACHMENT_BRAND_WORDMARK,
            fallback_attachment=ATTACHMENT_BRAND_ICON,
            fallback_static=DEFAULT_ICON_RELPATH,
        )

    def _serve(self, attachment_name, fallback_attachment=None, fallback_static=None):
        IrAttachment = request.env['ir.attachment'].sudo()
        att = IrAttachment.search([('name', '=', attachment_name)], limit=1)
        if not att and fallback_attachment:
            att = IrAttachment.search([('name', '=', fallback_attachment)], limit=1)
        if att:
            return request.make_response(
                base64.b64decode(att.datas),
                headers=[('Content-Type', att.mimetype or 'image/png')] + CACHE_HEADERS,
            )
        if fallback_static:
            module_path = get_module_path('qr_code_odoo')
            path = os.path.join(module_path, fallback_static)
            if os.path.exists(path):
                with open(path, 'rb') as f:
                    return request.make_response(
                        f.read(),
                        headers=[('Content-Type', 'image/png')] + CACHE_HEADERS,
                    )
        return request.not_found()
