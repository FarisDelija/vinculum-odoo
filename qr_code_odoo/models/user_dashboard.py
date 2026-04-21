# -*- coding: utf-8 -*-
"""
Vinculum - Digital Business Cards Module
Copyright (C) 2024 Faris Delija. All Rights Reserved.
Licensed under OPL-1 (Odoo Proprietary License v1.0)

Unauthorized copying, modification, or distribution prohibited.
"""
from odoo import models, fields, api
from datetime import datetime, timedelta


class UserDashboard(models.TransientModel):
    """Transient model to display aggregated dashboard statistics for user's vCards"""
    _name = 'user.dashboard'
    _description = 'User Dashboard Statistics'
    _rec_name = 'name'
    
    # User info
    name = fields.Char(string='Dashboard', default='My Dashboard', readonly=True)
    current_user_name = fields.Char(compute='_compute_user_info')
    
    # Aggregate statistics
    total_vcards = fields.Integer(compute='_compute_stats', string='Total Cards')
    total_opportunities = fields.Integer(compute='_compute_stats', string='Total Leads')
    total_qr_scans = fields.Integer(compute='_compute_stats', string='Total QR Scans')
    total_page_views = fields.Integer(compute='_compute_stats', string='Total Card Views')
    total_vcard_downloads = fields.Integer(compute='_compute_stats', string='Total Downloads')
    recent_downloads_count = fields.Integer(compute='_compute_stats', string='Recent Downloads (7 Days)')
    
    # Recent activity stats
    recent_leads_count = fields.Integer(compute='_compute_recent_stats', string='Recent Leads (7 Days)')
    monthly_opportunities = fields.Integer(compute='_compute_recent_stats', string='Monthly Leads')
    leads_mom_delta = fields.Char(compute='_compute_recent_stats', string='MoM Delta')
    
    # Download tracking
    download_tracking_ids = fields.Many2many(
        'vcard.download.tracking',
        compute='_compute_download_tracking',
        string='Recent Downloads'
    )
    
    # Recent leads
    recent_leads_ids = fields.Many2many(
        'crm.lead',
        compute='_compute_recent_leads',
        string='Recent Leads'
    )
    
    # All vCards for the user
    vcard_ids = fields.Many2many(
        'partner.vcard',
        compute='_compute_vcards',
        string='vCards'
    )
    
    @api.depends()
    def _compute_user_info(self):
        """Get current user name"""
        for record in self:
            record.current_user_name = self.env.user.name
    
    @api.depends()
    def _compute_vcards(self):
        """Get all vCards for current user"""
        for record in self:
            # Find vCards created by this user
            vcards = self.env['partner.vcard'].search([
                ('create_uid', '=', self.env.user.id)
            ])
            # Also try to match by email if user has an email
            if self.env.user.partner_id and self.env.user.partner_id.email:
                email_vcards = self.env['partner.vcard'].search([
                    ('email', '=', self.env.user.partner_id.email),
                    ('create_uid', '!=', self.env.user.id)  # Don't double-count
                ])
                vcards |= email_vcards
            record.vcard_ids = vcards
    
    @api.depends('vcard_ids')
    def _compute_stats(self):
        """Compute aggregate statistics across all user's vCards"""
        for record in self:
            if not record.vcard_ids:
                record.total_vcards = 0
                record.total_opportunities = 0
                record.total_qr_scans = 0
                record.total_page_views = 0
                record.total_vcard_downloads = 0
                record.recent_downloads_count = 0
                continue
            
            # Count published vCards
            record.total_vcards = len(record.vcard_ids.filtered(lambda v: v.is_published))
            
            # Aggregate leads from all vCards
            all_leads = self.env['crm.lead'].search([
                ('partner_vcard_id', 'in', record.vcard_ids.ids),
                ('type', '=', 'opportunity')
            ])
            record.total_opportunities = len(all_leads)
            
            # Aggregate QR scans
            record.total_qr_scans = sum(record.vcard_ids.mapped('qr_code_scan_count'))
            
            # Aggregate page views
            record.total_page_views = sum(record.vcard_ids.mapped('page_view_count'))
            
            # Aggregate downloads
            record.total_vcard_downloads = sum(record.vcard_ids.mapped('vcard_download_count'))
            
            # Recent downloads (last 7 days)
            seven_days_ago = datetime.now() - timedelta(days=7)
            recent_downloads = self.env['vcard.download.tracking'].search_count([
                ('partner_vcard_id', 'in', record.vcard_ids.ids),
                ('download_date', '>=', seven_days_ago)
            ])
            record.recent_downloads_count = recent_downloads
    
    @api.depends('vcard_ids')
    def _compute_recent_stats(self):
        """Compute recent activity statistics"""
        for record in self:
            if not record.vcard_ids:
                record.recent_leads_count = 0
                record.monthly_opportunities = 0
                record.leads_mom_delta = '0%'
                continue
            
            # Get all leads from user's vCards
            all_leads = self.env['crm.lead'].search([
                ('partner_vcard_id', 'in', record.vcard_ids.ids),
                ('type', '=', 'opportunity')
            ])
            
            # Recent leads (last 7 days)
            seven_days_ago = datetime.now() - timedelta(days=7)
            recent_leads = all_leads.filtered(
                lambda l: l.create_date and l.create_date >= seven_days_ago
            )
            record.recent_leads_count = len(recent_leads)
            
            # Monthly leads (last 30 days)
            thirty_days_ago = datetime.now() - timedelta(days=30)
            monthly_leads = all_leads.filtered(
                lambda l: l.create_date and l.create_date >= thirty_days_ago
            )
            record.monthly_opportunities = len(monthly_leads)
            
            # Month-over-month delta (simplified - compare this month vs last month)
            sixty_days_ago = datetime.now() - timedelta(days=60)
            last_month_leads = all_leads.filtered(
                lambda l: l.create_date and thirty_days_ago <= l.create_date < sixty_days_ago
            )
            
            if len(last_month_leads) > 0:
                delta = ((len(monthly_leads) - len(last_month_leads)) / len(last_month_leads)) * 100
                record.leads_mom_delta = f"{delta:+.0f}%"
            else:
                record.leads_mom_delta = f"+{len(monthly_leads) * 100}%" if len(monthly_leads) > 0 else "0%"
    
    @api.depends('vcard_ids')
    def _compute_download_tracking(self):
        """Get recent download tracking records"""
        for record in self:
            if not record.vcard_ids:
                record.download_tracking_ids = self.env['vcard.download.tracking']
                continue
            
            downloads = self.env['vcard.download.tracking'].search([
                ('partner_vcard_id', 'in', record.vcard_ids.ids)
            ], limit=20, order='download_date desc')
            record.download_tracking_ids = downloads
    
    @api.depends('vcard_ids')
    def _compute_recent_leads(self):
        """Get recent leads"""
        for record in self:
            if not record.vcard_ids:
                record.recent_leads_ids = self.env['crm.lead']
                continue
            
            seven_days_ago = datetime.now() - timedelta(days=7)
            recent_leads = self.env['crm.lead'].search([
                ('partner_vcard_id', 'in', record.vcard_ids.ids),
                ('type', '=', 'opportunity'),
                ('create_date', '>=', seven_days_ago)
            ], limit=10, order='create_date desc')
            record.recent_leads_ids = recent_leads
    
    def action_view_vcards(self):
        """Open vCards list view"""
        return {
            'type': 'ir.actions.act_window',
            'name': 'My vCards',
            'res_model': 'partner.vcard',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.vcard_ids.ids)],
            'target': 'current',
        }

    def action_create_new_card(self):
        """Open the public /get-started flow so the user is walked through the
        card creation steps the same way new users are."""
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        return {
            'type': 'ir.actions.act_url',
            'url': f"{base_url}/get-started",
            'target': 'new',
        }
    
    def action_view_opportunities(self):
        """Open Leads kanban view"""
        return {
            'type': 'ir.actions.act_window',
            'name': 'Leads',
            'res_model': 'crm.lead',
            'view_mode': 'kanban,list,form',
            'domain': [
                ('partner_vcard_id', 'in', self.vcard_ids.ids),
                ('type', '=', 'opportunity')
            ],
            'context': {'search_default_my_pipeline': 1, 'default_type': 'opportunity'},
            'target': 'current',
        }
    
    def action_open_nfc_setup(self):
        """Open the NFC card programming walkthrough.

        The NFC walkthrough at /nfc/setup/<partner_id> is scoped to a single
        vCard (it embeds the card's public URL). If the user has at least one
        card we deep-link to that; otherwise we fall back to the admin-track
        NFC topic in the Vinc Guide so the user still has instructions to
        read before they create a card.
        """
        if self.vcard_ids:
            target_url = f"/nfc/setup/{self.vcard_ids[0].id}"
        else:
            target_url = "/vinculum/guide/nfc"
        return {
            'type': 'ir.actions.act_url',
            'url': target_url,
            'target': 'new',
        }
    
    def action_open_vinculum_guide(self):
        """Open Vinc guide"""
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        return {
            'type': 'ir.actions.act_url',
            'url': f"{base_url}/vinculum/guide",
            'target': 'new',
        }
    
    def action_view_bulk_onboarding(self):
        """Open bulk onboarding website interface"""
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        return {
            'type': 'ir.actions.act_url',
            'url': f"{base_url}/bulk-onboard",
            'target': 'self',
        }
    
    @api.model
    def get_dashboard(self):
        """Create or get dashboard record for current user"""
        dashboard = self.create({'name': 'My Dashboard'})
        return dashboard

