# -*- coding: utf-8 -*-
"""
Vinculum - Digital Business Cards Module
Copyright (C) 2024 Faris Delija. All Rights Reserved.
Licensed under OPL-1 (Odoo Proprietary License v1.0)

Unauthorized copying, modification, or distribution prohibited.
"""
import base64

from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('post_install', '-at_install')
class TestVcardAttachmentOwnership(TransactionCase):
    """Generating one card's website must never touch another card's image.

    The image a published card serves is the bytes of the ir.attachment row
    its attachment_id points at. Two cards pointing at one row therefore serve
    one image, and regenerating either card rewrites the picture on both.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # install_mode short-circuits the Vinc license guard on create/write,
        # which would otherwise refuse every write in an unlicensed test DB.
        cls.env = cls.env(context=dict(cls.env.context, install_mode=True))
        cls.image_a = base64.b64encode(b'image-for-card-a')
        cls.image_b = base64.b64encode(b'image-for-card-b')
        cls.banner_a = base64.b64encode(b'banner-for-card-a')

    def _make_card(self, name, slug, image, banner=None):
        return self.env['partner.vcard'].create({
            'name': name,
            'website_slug': slug,
            'image_url': image,
            'banner_image': banner,
        })

    def test_generate_does_not_rewrite_another_cards_attachment(self):
        """A card sharing another card's attachment row must not write it.

        Fails without the ownership guard: card B's generate rewrites the row
        card A also points at, so A starts serving B's picture.
        """
        card_a = self._make_card('Card A', 'card-a', self.image_a)
        card_b = self._make_card('Card B', 'card-b', self.image_b)

        card_a.action_generate_website_page()
        shared = card_a.attachment_id
        self.assertTrue(shared, 'card A should own an attachment after generating')

        # Put card B on card A's attachment row - the state duplication used to
        # produce, and that a data edit can still produce.
        card_b.write({'attachment_id': shared.id})
        self.assertEqual(card_b.attachment_id, shared)

        card_b.action_generate_website_page()

        self.assertEqual(
            shared.datas, self.image_a,
            "generating card B rewrote card A's attachment - A now serves B's image",
        )
        self.assertNotEqual(
            card_b.attachment_id, shared,
            'card B should have been repointed at its own attachment row',
        )
        self.assertEqual(card_b.attachment_id.datas, self.image_b)
        self.assertEqual(card_b.attachment_id.res_id, card_b.id)
        self.assertEqual(card_a.attachment_id, shared)

        # The template resolves the picture from the record it embeds, so card
        # A's page must still be bound to card A.
        view_a = self.env['ir.ui.view'].search([('key', '=', 'website.card-a')], limit=1)
        self.assertTrue(view_a, 'card A should have a generated view')
        self.assertIn('browse(%s)' % card_a.id, view_a.arch_db)
        self.assertNotIn('browse(%s)' % card_b.id, view_a.arch_db)

    def test_duplicate_does_not_share_attachment_rows(self):
        """A duplicated card must not inherit the original's attachment rows.

        Fails without copy=False / the explicit clears in copy(): a Many2one is
        copied by reference, so the copy points at the original's rows.
        """
        card = self._make_card('Original', 'original', self.image_a, banner=self.banner_a)
        card.action_generate_website_page()
        self.assertTrue(card.attachment_id)
        self.assertTrue(card.banner_attachment_id)

        copy = card.copy()

        self.assertNotEqual(
            copy.attachment_id, card.attachment_id,
            'the copy shares the original image attachment row',
        )
        self.assertNotEqual(
            copy.banner_attachment_id, card.banner_attachment_id,
            'the copy shares the original banner attachment row',
        )
        self.assertFalse(copy.attachment_id)
        self.assertFalse(copy.banner_attachment_id)

    def test_removing_a_shared_banner_keeps_the_other_cards_row(self):
        """Clearing a banner must not unlink a row another card still uses."""
        card_a = self._make_card('Banner A', 'banner-a', self.image_a, banner=self.banner_a)
        card_b = self._make_card('Banner B', 'banner-b', self.image_b, banner=self.banner_a)

        card_a.action_generate_website_page()
        shared = card_a.banner_attachment_id
        self.assertTrue(shared)
        card_b.write({'banner_attachment_id': shared.id})

        card_b.write({'banner_image': False})
        card_b._update_banner_attachment_if_image_changed()

        self.assertFalse(card_b.banner_attachment_id)
        self.assertTrue(shared.exists(), "card B's clear deleted card A's banner row")
        self.assertEqual(card_a.banner_attachment_id, shared)

    def test_generate_without_slug_reports_an_error(self):
        """A slugless card must be refused, not reported as a success.

        Fails without the guard: the method returns "Success!" while the
        ir.ui.view INSERT it queued is invalid (name is False), which then
        aborts the transaction at flush.
        """
        card = self._make_card('No Slug', False, self.image_a)

        result = card.action_generate_website_page()

        self.assertEqual(result['params']['type'], 'danger')
        self.assertIn('No Slug', result['params']['message'])
        self.assertFalse(card.website_page_id)
        # Nothing invalid was queued, so the cursor is still usable.
        self.env.flush_all()
        self.assertFalse(
            self.env['ir.ui.view'].search([('key', '=', 'website.False')]),
            'a view was created for a slugless card',
        )
