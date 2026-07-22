from odoo.tests import TransactionCase, tagged

from ..models.brand_config import DEFAULT_BRAND_NAME


@tagged('post_install', '-at_install')
class TestBrandAppChrome(TransactionCase):
    """Saving a brand name in Settings must rebrand the Vinc app menu."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.menu = cls.env['qr_code_odoo.brand']._find_root_menu()
        cls.module = cls.env['ir.module.module'].search(
            [('name', '=', 'qr_code_odoo')], limit=1
        )

    def _save_brand_name(self, name):
        """Save `name` through Settings the way an admin does."""
        self.env['res.config.settings'].create({'vinc_brand_name': name}).execute()

    def test_root_menu_found(self):
        """The helper resolves the app's root menu (guards the xmlid drifting)."""
        self.assertTrue(self.menu, "Vinc root menu not found")
        self.assertFalse(self.menu.parent_id)

    def test_saving_brand_name_renames_app_menu(self):
        """Regression: the menu label used to stay 'Vinc' after saving Settings."""
        self._save_brand_name('Branded')

        self.assertEqual(self.menu.name, 'Branded')
        self.assertEqual(self.module.shortdesc, 'Branded')

    def test_clearing_brand_name_restores_default(self):
        """Emptying the field puts the shipped name back."""
        self._save_brand_name('Branded')

        self._save_brand_name(False)

        self.assertEqual(self.menu.name, DEFAULT_BRAND_NAME)
        self.assertEqual(self.module.shortdesc, DEFAULT_BRAND_NAME)
