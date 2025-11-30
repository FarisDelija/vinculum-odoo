# -*- coding: utf-8 -*-
"""
Vinculum - Digital Business Cards Module
Copyright (C) 2024 Faris Delija. All Rights Reserved.
Licensed under OPL-1 (Odoo Proprietary License v1.0)

Unauthorized copying, modification, or distribution prohibited.
"""
from odoo import models, fields, api
import logging
import re

_logger = logging.getLogger(__name__)


class ResUsers(models.Model):
    _inherit = 'res.users'
    
    @api.model
    def create(self, vals):
        """Override create to auto-assign necessary groups and sync email"""
        # Automatically assign necessary groups to all new users
        if 'groups_id' not in vals:
            vals['groups_id'] = []
        
        # Always ensure base user group is included
        base_user_group = self.env.ref('base.group_user')
        if base_user_group and base_user_group.id not in [g[1] if len(g) > 1 and g[0] == 4 else g for g in vals['groups_id']]:
            vals['groups_id'].append((4, base_user_group.id))
        
        # Get the Sales/User group
        sales_user_group = self.env['res.groups'].search([
            ('name', '=', 'User: Own Documents Only'),
            ('category_id.name', '=', 'Sales')
        ], limit=1)
        
        # Get the Website/Editor group
        website_editor_group = self.env['res.groups'].search([
            ('name', '=', 'Editor and Designer'),
            ('category_id.name', '=', 'Website')
        ], limit=1)
        
        # Get the Website/Restricted Editor group
        website_restricted_group = self.env['res.groups'].search([
            ('name', '=', 'Restricted Editor'),
            ('category_id.name', '=', 'Website')
        ], limit=1)
        
        # Get the Email Marketing User group
        email_marketing_group = self.env.ref('mass_mailing.group_mass_mailing_user', raise_if_not_found=False)
        
        # Check existing group IDs
        existing_group_ids = []
        for group_tuple in vals['groups_id']:
            if len(group_tuple) > 1 and group_tuple[0] in [4, 6]:  # (4, id) or (6, 0, [ids])
                if group_tuple[0] == 4:
                    existing_group_ids.append(group_tuple[1])
                elif group_tuple[0] == 6:
                    existing_group_ids.extend(group_tuple[2])
        
        # Add Sales group if not already present
        if sales_user_group and sales_user_group.id not in existing_group_ids:
            vals['groups_id'].append((4, sales_user_group.id))
        
        # Add Website groups if not already present
        if website_editor_group and website_editor_group.id not in existing_group_ids:
            vals['groups_id'].append((4, website_editor_group.id))
        
        if website_restricted_group and website_restricted_group.id not in existing_group_ids:
            vals['groups_id'].append((4, website_restricted_group.id))
        
        # Add Email Marketing group if not already present
        if email_marketing_group and email_marketing_group.id not in existing_group_ids:
            vals['groups_id'].append((4, email_marketing_group.id))
        
        user = super(ResUsers, self).create(vals)
        
        # Ensure partner email is set from login if login is an email address and partner email is blank
        # NOTE: In Odoo, res.users.email is a related field from res.partner.email, NOT from login!
        # So we must explicitly set partner.email if we want user.email to work.
        if user.partner_id and user.login and not user.partner_id.email:
            # Check if login looks like an email address
            import re
            if re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', user.login):
                user.partner_id.email = user.login
                _logger.info(f"Set partner email from login for user {user.id} (login: {user.login})")
        
        return user
    
    def write(self, vals):
        """Override write to ensure partner email is synced from login if login changes"""
        result = super(ResUsers, self).write(vals)
        
        # If login was updated and it's an email address, sync to partner email if partner email is blank
        if 'login' in vals and vals['login']:
            import re
            for user in self:
                if (user.partner_id and 
                    re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', user.login) and
                    not user.partner_id.email):
                    user.partner_id.email = user.login
                    _logger.info(f"Synced partner email from login for user {user.id} (login: {user.login})")
        
        return result
    
    def fix_missing_emails(self):
        """Fix users where email is blank but login is an email address"""
        import re
        fixed_count = 0
        for user in self:
            if (user.partner_id and 
                user.login and 
                not user.partner_id.email and
                re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', user.login)):
                user.partner_id.email = user.login
                fixed_count += 1
                _logger.info(f"Fixed email for user {user.id} (login: {user.login})")
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Email Fix Complete',
                'message': f'Fixed {fixed_count} user(s) by setting partner email from login.',
                'type': 'success',
            }
        }
    
    @api.model
    def fix_all_users_sales_permissions(self):
        """Fix Sales permissions for all existing users"""
        # Get the Sales/User group
        sales_user_group = self.env['res.groups'].search([
            ('name', '=', 'User: Own Documents Only'),
            ('category_id.name', '=', 'Sales')
        ], limit=1)
        
        if not sales_user_group:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Error',
                    'message': 'Sales/User group not found!',
                    'type': 'danger',
                }
            }
        
        # Get all users who don't have the Sales group
        users_without_sales = self.search([
            ('id', '!=', 1),  # Exclude admin user
            ('groups_id', 'not in', [sales_user_group.id])
        ])
        
        fixed_count = 0
        for user in users_without_sales:
            user.groups_id = [(4, sales_user_group.id)]
            fixed_count += 1
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Fixed User Permissions',
                'message': f'Added Sales/User permissions to {fixed_count} users.',
                'type': 'success',
            }
        }
    
    @api.model
    def fix_all_users_website_permissions(self):
        """Fix Website permissions for all existing users"""
        # Get the Website groups
        website_editor_group = self.env['res.groups'].search([
            ('name', '=', 'Editor and Designer'),
            ('category_id.name', '=', 'Website')
        ], limit=1)
        
        website_restricted_group = self.env['res.groups'].search([
            ('name', '=', 'Restricted Editor'),
            ('category_id.name', '=', 'Website')
        ], limit=1)
        
        if not website_editor_group or not website_restricted_group:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Error',
                    'message': 'Website groups not found!',
                    'type': 'danger',
                }
            }
        
        # Get all users who don't have the Website groups
        users_without_website = self.search([
            ('id', '!=', 1),  # Exclude admin user
            ('groups_id', 'not in', [website_editor_group.id, website_restricted_group.id])
        ])
        
        fixed_count = 0
        for user in users_without_website:
            user.groups_id = [(4, website_editor_group.id), (4, website_restricted_group.id)]
            fixed_count += 1
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Fixed Website Permissions',
                'message': f'Added Website permissions to {fixed_count} users.',
                'type': 'success',
            }
        }
    
    @api.model
    def fix_email_marketing_permissions(self):
        """Add Email Marketing User permissions to all existing users"""
        # Get the Email Marketing User group
        email_marketing_group = self.env.ref('mass_mailing.group_mass_mailing_user', raise_if_not_found=False)
        
        if not email_marketing_group:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Error',
                    'message': 'Email Marketing User group not found!',
                    'type': 'danger',
                }
            }
        
        # Get all internal users who don't have the Email Marketing group
        users_without_email = self.search([
            ('id', '!=', 1),  # Exclude admin user
            ('share', '=', False),  # Only internal users
            ('groups_id', 'not in', [email_marketing_group.id])
        ])
        
        fixed_count = 0
        for user in users_without_email:
            user.groups_id = [(4, email_marketing_group.id)]
            fixed_count += 1
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Fixed Email Marketing Permissions',
                'message': f'Added Email Marketing permissions to {fixed_count} users.',
                'type': 'success',
            }
        }
    
    @api.model
    def name_search(self, name='', args=None, operator='ilike', limit=100):
        """Override name_search - tenant filtering removed"""
        return super().name_search(name=name, args=args, operator=operator, limit=limit)
