from odoo import api, fields, models

# ir.config_parameter keys used for runtime branding.
PARAM_BRAND_NAME = 'qr_code_odoo.brand_name'
PARAM_BRAND_SHORT_NAME = 'qr_code_odoo.brand_short_name'
ATTACHMENT_BRAND_ICON = 'qr_code_odoo.brand_icon'
ATTACHMENT_BRAND_WORDMARK = 'qr_code_odoo.brand_wordmark'

DEFAULT_BRAND_NAME = 'Vinc'
DEFAULT_BRAND_SHORT_NAME = 'Vinc'


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    vinc_brand_name = fields.Char(
        string='Brand Name',
        config_parameter=PARAM_BRAND_NAME,
        default=DEFAULT_BRAND_NAME,
        help="Full product name shown to end users (emails, headers, prose).",
    )
    vinc_brand_short_name = fields.Char(
        string='Short Name',
        config_parameter=PARAM_BRAND_SHORT_NAME,
        default=DEFAULT_BRAND_SHORT_NAME,
        help="Compact name for tight spaces (chips, wordmarks).",
    )
    vinc_brand_icon = fields.Binary(
        string='Brand Icon',
        help="Square logo (~512x512). Used for chips, favicons, default QR overlay.",
    )
    vinc_brand_wordmark = fields.Binary(
        string='Brand Wordmark',
        help="Horizontal logo for page headers and email banners. Falls back to icon if blank.",
    )

    @api.model
    def get_values(self):
        res = super().get_values()
        res['vinc_brand_icon'] = self.env['qr_code_odoo.brand']._get_attachment_data(ATTACHMENT_BRAND_ICON)
        res['vinc_brand_wordmark'] = self.env['qr_code_odoo.brand']._get_attachment_data(ATTACHMENT_BRAND_WORDMARK)
        return res

    def set_values(self):
        super().set_values()
        Brand = self.env['qr_code_odoo.brand']
        Brand._set_attachment_data(ATTACHMENT_BRAND_ICON, self.vinc_brand_icon)
        Brand._set_attachment_data(ATTACHMENT_BRAND_WORDMARK, self.vinc_brand_wordmark)
        # Safe here: one admin, one transaction. The concurrency problem was the
        # registry-load copy of this call (see _register_hook), not this one.
        Brand._sync_app_chrome()


class VincBrand(models.AbstractModel):
    """Single point of access for brand strings & assets.

    Templates, controllers, and python email composers all route through here so
    a future change to storage (e.g. moving to res.company-scoped branding) only
    touches this file.
    """
    _name = 'qr_code_odoo.brand'
    _description = 'Vinc Brand Configuration Helper'

    def _register_hook(self):
        """Deliberately does not re-apply brand chrome.

        `-u qr_code_odoo` reloads the module's data and resets the root menu name
        and web_icon to the XML defaults, so a custom brand has to be re-applied
        by saving Settings again. Syncing from here instead used to do that
        automatically, but this hook runs on every registry load: with several
        workers rebuilding at once the overlapping writes to the shared
        ir.ui.menu row raised a Postgres serialization error that poisoned the
        transaction and failed the upgrade. Re-applying on upgrade needs a
        collision-safe design, not this hook.
        """
        return super()._register_hook()

    @api.model
    def get_brand_name(self):
        return self.env['ir.config_parameter'].sudo().get_param(
            PARAM_BRAND_NAME, DEFAULT_BRAND_NAME
        ) or DEFAULT_BRAND_NAME

    @api.model
    def get_brand_short_name(self):
        return self.env['ir.config_parameter'].sudo().get_param(
            PARAM_BRAND_SHORT_NAME, DEFAULT_BRAND_SHORT_NAME
        ) or DEFAULT_BRAND_SHORT_NAME

    @api.model
    def get_brand_icon_url(self):
        return '/qr_code_odoo/brand/icon'

    @api.model
    def get_brand_wordmark_url(self):
        return '/qr_code_odoo/brand/wordmark'

    @api.model
    def get_brand_icon_binary(self):
        """Return raw bytes of the configured brand icon, or None to fall back to the static default."""
        import base64
        data = self._get_attachment_data(ATTACHMENT_BRAND_ICON)
        if not data:
            return None
        try:
            return base64.b64decode(data)
        except Exception:
            return None

    @api.model
    def _get_attachment_data(self, name):
        att = self.env['ir.attachment'].sudo().search(
            [('name', '=', name)], limit=1
        )
        return att.datas if att else False

    @api.model
    def _sync_app_chrome(self):
        """Push brand_name + brand_icon onto the Vinc app's root menu and
        ir.module.module record so the Apps grid tile and main menu rebrand.

        Note: a future `-u qr_code_odoo` upgrade re-runs the module's data files
        and may reset these to the defaults declared in XML. Re-save Settings to
        re-apply.
        """
        brand_name = self.get_brand_name()
        icon_bytes = self.get_brand_icon_binary()

        # Root menu — name + icon. ir.ui.menu.write() recomputes web_icon_data
        # from web_icon whenever 'web_icon' is in the vals dict, so we must
        # write web_icon_data in a separate write() that does NOT touch web_icon.
        import base64
        menu = self._find_root_menu()
        if menu:
            menu.sudo().write({'name': brand_name})
            if icon_bytes:
                menu.sudo().write({'web_icon_data': base64.b64encode(icon_bytes)})

        # Apps grid tile. Only shortdesc is writable — ir.module.module.icon_image
        # is a non-stored computed field read from the module folder on disk.
        module = self.env['ir.module.module'].sudo().search(
            [('name', '=', 'qr_code_odoo')], limit=1
        )
        if module:
            module.write({'shortdesc': brand_name})

    @api.model
    def _find_root_menu(self):
        """Locate the addon's root menu without depending on a specific xmlid."""
        IrModelData = self.env['ir.model.data'].sudo()
        menu_data = IrModelData.search(
            [('module', '=', 'qr_code_odoo'), ('model', '=', 'ir.ui.menu')]
        )
        Menu = self.env['ir.ui.menu'].sudo()
        roots = Menu.search([('id', 'in', menu_data.mapped('res_id')),
                             ('parent_id', '=', False)], limit=1)
        return roots

    @api.model
    def _set_attachment_data(self, name, data):
        IrAttachment = self.env['ir.attachment'].sudo()
        existing = IrAttachment.search([('name', '=', name)], limit=1)
        if data:
            vals = {
                'name': name,
                'datas': data,
                'type': 'binary',
                'mimetype': 'image/png',
                'public': True,
                'res_model': 'ir.config_parameter',
            }
            if existing:
                existing.write(vals)
            else:
                IrAttachment.create(vals)
        elif existing:
            existing.unlink()
