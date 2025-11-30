# -*- coding: utf-8 -*-
"""
Vinculum - Digital Business Cards Module
Copyright (C) 2024 Faris Delija. All Rights Reserved.
Licensed under OPL-1 (Odoo Proprietary License v1.0)

Unauthorized copying, modification, or distribution prohibited.
"""
import qrcode
from PIL import Image, ImageDraw
import io
import base64
import re
from odoo import models, fields, api
from odoo.exceptions import ValidationError, UserError
from markupsafe import Markup
from qrcode.image.styles.colormasks import SolidFillColorMask
from qrcode.image.styledpil import StyledPilImage
from qrcode.image.styles.moduledrawers import CircleModuleDrawer, RoundedModuleDrawer, GappedSquareModuleDrawer, SquareModuleDrawer

class LeadTag(models.Model):
    _name = 'lead.tag'
    _description = 'Lead Tag'

    name = fields.Char(string="Tag Name", required=True, help="Name of the tag")

class FollowupReminder(models.Model):
    _name = 'followup.reminder'
    _description = 'Follow-up Reminder Template'
    _order = 'sequence, id'
    
    partner_vcard_id = fields.Many2one(
        'partner.vcard',
        string="Partner vCard",
        required=True,
        ondelete='cascade'
    )
    name = fields.Char(
        string="Reminder Name",
        required=True,
        help="Name for this reminder (e.g., 'First Follow-up', 'Check-in After 3 Days')"
    )
    sequence = fields.Integer(string="Sequence", default=10, help="Order in which reminders are scheduled")
    active = fields.Boolean(string="Active", default=True, help="Enable or disable this reminder")
    
    # Activity configuration
    activity_type_id = fields.Many2one(
        'mail.activity.type',
        string="Activity Type",
        required=True,
        help="Type of activity to create (Call, Email, Meeting, etc.)"
    )
    summary = fields.Char(
        string="Summary",
        help="Short description for the activity. Leave empty to use activity type name."
    )
    note = fields.Text(
        string="Note",
        help="Additional notes for the activity"
    )
    
    # Timing configuration
    schedule_type = fields.Selection(
        [('after_creation', 'After Lead Creation'), ('after_previous_activity', 'After Previous Activity Completed')],
        string="Schedule Type",
        required=True,
        default='after_creation',
        help="When to schedule this reminder: immediately after lead creation, or after the previous activity is completed"
    )
    delay_amount = fields.Integer(
        string="Delay Amount",
        required=True,
        default=1,
        help="How long to wait before scheduling this reminder"
    )
    delay_type = fields.Selection(
        [('minutes', 'Minutes'), ('hours', 'Hours'), ('days', 'Days')],
        string="Delay Type",
        required=True,
        default='days',
        help="Unit for the delay"
    )
    
    # User assignment
    user_id = fields.Many2one(
        'res.users',
        string="Assigned To",
        help="User to assign the activity to. Leave empty to assign to vCard owner."
    )

class FollowupScheduledReminder(models.Model):
    _name = 'followup.scheduled.reminder'
    _description = 'Scheduled Follow-up Reminder'
    _order = 'scheduled_datetime asc'
    
    opportunity_id = fields.Many2one(
        'crm.lead',
        string="Opportunity",
        required=True,
        ondelete='cascade',
        help="The lead/opportunity this reminder is for"
    )
    contact_name = fields.Char(
        string="Contact Name",
        required=True,
        help="Name of the contact for placeholder replacement"
    )
    reminder_template_id = fields.Many2one(
        'followup.reminder',
        string="Reminder Template",
        required=True,
        ondelete='cascade',
        help="The reminder template this scheduled reminder is based on"
    )
    scheduled_datetime = fields.Datetime(
        string="Scheduled DateTime",
        required=True,
        index=True,
        help="Exact datetime when this activity should be created"
    )
    date_deadline = fields.Date(
        string="Activity Deadline",
        required=True,
        help="The date_deadline to set on the activity when it's created"
    )
    activity_type_id = fields.Many2one(
        'mail.activity.type',
        string="Activity Type",
        required=True,
        help="Type of activity to create"
    )
    summary = fields.Char(
        string="Summary",
        help="Activity summary (with placeholders already processed)"
    )
    note = fields.Text(
        string="Note",
        help="Activity notes"
    )
    user_id = fields.Many2one(
        'res.users',
        string="Assigned To",
        required=True,
        help="User to assign the activity to"
    )
    previous_activity_id = fields.Many2one(
        'mail.activity',
        string="Previous Activity",
        help="For 'after_previous_activity' type: the activity that must be completed before this reminder is scheduled"
    )
    processed = fields.Boolean(
        string="Processed",
        default=False,
        index=True,
        help="Whether this reminder has been processed and activity created"
    )
    activity_id = fields.Many2one(
        'mail.activity',
        string="Created Activity",
        readonly=True,
        help="The activity that was created from this scheduled reminder"
    )
    created_at = fields.Datetime(
        string="Created At",
        default=fields.Datetime.now,
        readonly=True,
        help="When this scheduled reminder was created"
    )
    processed_at = fields.Datetime(
        string="Processed At",
        readonly=True,
        help="When this scheduled reminder was processed"
    )
    
    @api.model
    def _cron_process_scheduled_reminders(self):
        """
        Cron job to process scheduled follow-up reminders and create activities.
        This runs every minute to check for reminders that are due.
        
        :return: Number of activities created
        """
        import logging
        _logger = logging.getLogger(__name__)
        
        _logger.info("=" * 80)
        _logger.info("FOLLOW-UP REMINDER CRON - Starting")
        _logger.info(f"Current datetime: {fields.Datetime.now()}")
        _logger.info("=" * 80)
        
        now_str = fields.Datetime.now()
        now_dt = fields.Datetime.from_string(now_str)
        
        # Find all unprocessed reminders that are due (scheduled_datetime <= now)
        # Exclude reminders waiting for previous activities (they'll be handled separately)
        due_reminders = self.sudo().search([
            ('processed', '=', False),
            ('scheduled_datetime', '<=', now_str),
            ('previous_activity_id', '=', False)  # Not waiting for previous activity
        ], order='scheduled_datetime asc')
        
        _logger.info(f"Found {len(due_reminders)} scheduled reminder(s) due for processing (excluding those waiting for previous activities)")
        
        # Also check for reminders waiting for completed activities
        completed_activities = self.env['mail.activity'].sudo().search([
            ('state', '=', 'done'),
            ('date_done', '!=', False),
        ])
        
        if completed_activities:
            # Find reminders waiting for these completed activities
            waiting_reminders = self.sudo().search([
                ('processed', '=', False),
                ('previous_activity_id', 'in', completed_activities.ids),
            ])
            
            if waiting_reminders:
                _logger.info(f"Found {len(waiting_reminders)} reminder(s) waiting for completed activities")
                # Process these reminders - recalculate their scheduled_datetime based on activity completion + delay
                for waiting_reminder in waiting_reminders:
                    try:
                        prev_activity = waiting_reminder.previous_activity_id
                        if prev_activity.state == 'done' and prev_activity.date_done:
                            # Calculate new scheduled_datetime based on completion date + delay
                            completion_dt = fields.Datetime.from_string(prev_activity.date_done)
                            template = waiting_reminder.reminder_template_id
                            
                            from datetime import timedelta
                            if template.delay_type == 'minutes':
                                new_scheduled_dt = completion_dt + timedelta(minutes=template.delay_amount)
                            elif template.delay_type == 'hours':
                                new_scheduled_dt = completion_dt + timedelta(hours=template.delay_amount)
                            elif template.delay_type == 'days':
                                new_scheduled_dt = completion_dt + timedelta(days=template.delay_amount)
                            else:
                                new_scheduled_dt = completion_dt
                            
                            # Update scheduled_datetime and date_deadline
                            if template.delay_type == 'days':
                                new_date_deadline = new_scheduled_dt.date()
                            else:
                                # For minutes/hours, if still today, set to tomorrow
                                if new_scheduled_dt.date() <= fields.Date.today():
                                    new_date_deadline = fields.Date.today() + timedelta(days=1)
                                else:
                                    new_date_deadline = new_scheduled_dt.date()
                            
                            waiting_reminder.write({
                                'scheduled_datetime': fields.Datetime.to_string(new_scheduled_dt),
                                'date_deadline': new_date_deadline,
                                'previous_activity_id': False,  # Clear the reference
                            })
                            
                            _logger.info(
                                f"  Updated reminder ID {waiting_reminder.id}: "
                                f"Previous activity {prev_activity.id} completed at {prev_activity.date_done}, "
                                f"New scheduled datetime: {new_scheduled_dt}, New deadline: {new_date_deadline}"
                            )
                    except Exception as e:
                        _logger.exception(f"Error updating waiting reminder ID {waiting_reminder.id}: {e}")
                
                # Re-fetch due reminders including the updated ones
                due_reminders = self.sudo().search([
                    ('processed', '=', False),
                    ('scheduled_datetime', '<=', now_str),
                    ('previous_activity_id', '=', False)
                ], order='scheduled_datetime asc')
        
        if not due_reminders:
            _logger.info("No reminders to process. Exiting.")
            _logger.info("=" * 80)
            return 0
        
        activities_created = 0
        errors = 0
        
        for reminder in due_reminders:
            try:
                _logger.info("-" * 80)
                _logger.info(f"Processing scheduled reminder ID {reminder.id}")
                _logger.info(f"  Opportunity ID: {reminder.opportunity_id.id}")
                _logger.info(f"  Contact Name: {reminder.contact_name}")
                _logger.info(f"  Reminder Template: {reminder.reminder_template_id.name}")
                _logger.info(f"  Scheduled for: {reminder.scheduled_datetime}")
                _logger.info(f"  Date Deadline: {reminder.date_deadline}")
                _logger.info(f"  Activity Type: {reminder.activity_type_id.name}")
                _logger.info(f"  Assigned To: {reminder.user_id.name}")
                
                # Check if opportunity still exists
                if not reminder.opportunity_id.exists():
                    _logger.warning(f"  ✗ Opportunity {reminder.opportunity_id.id} no longer exists. Marking as processed.")
                    reminder.write({
                        'processed': True,
                        'processed_at': fields.Datetime.now(),
                    })
                    continue
                
                # Create the activity using the stored date_deadline
                activity = reminder.opportunity_id.sudo().activity_schedule(
                    activity_type_id=reminder.activity_type_id.id,
                    summary=reminder.summary or reminder.activity_type_id.name or 'Follow-up',
                    note=reminder.note or '',
                    date_deadline=reminder.date_deadline,  # Use stored date_deadline
                    user_id=reminder.user_id.id,
                )
                
                # Mark as processed
                reminder.write({
                    'processed': True,
                    'processed_at': fields.Datetime.now(),
                    'activity_id': activity.id,
                })
                
                activities_created += 1
                
                _logger.info(
                    f"  ✓ Activity created successfully: ID {activity.id}, "
                    f"Assigned to: {reminder.user_id.name}, "
                    f"Due date: {reminder.date_deadline}"
                )
                
                # If there are any reminders waiting for this activity (for "after_previous_activity" type),
                # they will be picked up in the next cron run when this activity is marked as done
                
            except Exception as e:
                errors += 1
                _logger.exception(
                    f"  ✗ ERROR processing scheduled reminder ID {reminder.id}: {e}"
                )
                # Continue with other reminders even if one fails
                continue
        
        _logger.info("=" * 80)
        _logger.info(f"FOLLOW-UP REMINDER CRON - Completed")
        _logger.info(f"  Activities created: {activities_created}")
        _logger.info(f"  Errors: {errors}")
        _logger.info(f"  Total processed: {activities_created + errors}")
        _logger.info("=" * 80)
        
        return activities_created

class VcardDownloadTracking(models.Model):
    _name = 'vcard.download.tracking'
    _description = 'vCard Download Tracking'
    _order = 'download_date desc'
    
    partner_vcard_id = fields.Many2one(
        'partner.vcard',
        string="Partner vCard",
        required=True,
        ondelete='cascade',
        index=True,
        help="The vCard that was downloaded"
    )
    download_date = fields.Datetime(
        string="Download Date",
        default=fields.Datetime.now,
        required=True,
        index=True,
        help="When the vCard was downloaded"
    )
    
    # Tracking data (same as lead tracking)
    download_ip = fields.Char(
        string='Download IP',
        help='IP address captured when the vCard was downloaded'
    )
    download_user_agent = fields.Char(
        string='Download User Agent',
        help='Browser user agent string captured during download'
    )
    download_fingerprint_hash = fields.Char(
        string='Download Fingerprint',
        help='SHA-256 hash of browser fingerprint captured during download'
    )
    download_country = fields.Char(
        string='Download Country',
        help='Country detected from IP address geolocation'
    )
    download_city = fields.Char(
        string='Download City',
        help='City detected from IP address geolocation'
    )
    download_timezone = fields.Char(
        string='Download Timezone',
        help='Timezone detected from IP address or browser'
    )
    download_language = fields.Char(
        string='Download Language',
        help='Browser language preference (Accept-Language header)'
    )
    download_source_url = fields.Char(
        string='Source URL',
        help='The URL/referrer where the user came from before downloading'
    )
    download_utm_source = fields.Char(
        string='UTM Source',
        help='UTM source parameter from the URL (if present)'
    )
    download_utm_medium = fields.Char(
        string='UTM Medium',
        help='UTM medium parameter from the URL (if present)'
    )
    download_utm_campaign = fields.Char(
        string='UTM Campaign',
        help='UTM campaign parameter from the URL (if present)'
    )
    download_referral_code = fields.Char(
        string='Referral Code',
        help='Referral code (ref parameter) from the URL if the download came from a referral link'
    )
    download_device_type = fields.Char(
        string='Device Type',
        help='Detected device type (mobile, desktop, tablet) from user agent'
    )
    download_browser = fields.Char(
        string='Browser',
        help='Detected browser name from user agent'
    )
    download_os = fields.Char(
        string='Operating System',
        help='Detected operating system from user agent'
    )

class LeadbackMessagingChannel(models.Model):
    _name = 'leadback.messaging.channel'
    _description = 'Lead-Back Messaging Channel'
    _order = 'sequence, name'

    name = fields.Char(string="Channel Name", required=True)
    code = fields.Char(string="Channel Code", required=True, help="Internal code: whatsapp, viber, or telegram")
    sequence = fields.Integer(string="Sequence", default=10, help="Display order")
    active = fields.Boolean(string="Active", default=True)


class LeadbackScheduledEmail(models.Model):
    _name = 'leadback.scheduled.email'
    _description = 'Scheduled Lead-Back Email'
    _order = 'scheduled_time asc'
    
    partner_vcard_id = fields.Many2one(
        'partner.vcard',
        string="Partner vCard",
        required=True,
        ondelete='cascade'
    )
    contact_name = fields.Char(string="Contact Name", required=True)
    contact_email = fields.Char(string="Contact Email", required=True)
    opportunity_id = fields.Many2one(
        'crm.lead',
        string="Opportunity/Lead",
        ondelete='set null'
    )
    email_subject = fields.Char(string="Email Subject", required=True)
    email_body_html = fields.Html(string="Email Body (HTML)", required=True)
    scheduled_time = fields.Datetime(string="Scheduled Time", required=True, index=True)
    state = fields.Selection(
        [('pending', 'Pending'), ('sent', 'Sent'), ('failed', 'Failed')],
        string="State",
        default='pending',
        required=True
    )
    sent_time = fields.Datetime(string="Sent Time", readonly=True)
    error_message = fields.Text(string="Error Message", readonly=True)
    
    def action_send_now(self):
        """Manually send the scheduled email"""
        self.ensure_one()
        if self.state != 'pending':
            raise UserError("Only pending emails can be sent")
        
        self._send_email()
        return True
    
    def _send_email(self):
        """Send the scheduled email"""
        self.ensure_one()
        try:
            from datetime import datetime
            
            # Prepare mail values
            mail_values = {
                'subject': self.email_subject,
                'body_html': self.email_body_html,
                'email_to': self.contact_email,
                'email_from': self.partner_vcard_id.email or self.env.user.email or self.env['ir.config_parameter'].sudo().get_param('mail.catchall.alias', 'noreply@example.com'),
                'auto_delete': False,
            }
            
            # Create and send mail
            mail = self.env['mail.mail'].sudo().create(mail_values)
            mail.send()
            
            # Update state
            self.write({
                'state': 'sent',
                'sent_time': datetime.now()
            })
            
            # Log to opportunity if exists
            if self.opportunity_id:
                from markupsafe import Markup
                self.opportunity_id.message_post(
                    body=Markup(f"<p><strong>✓ Scheduled Email Sent</strong><br/>To: {self.contact_email}</p>"),
                    subject="Scheduled Lead-Back Email Sent"
                )
            
            import logging
            _logger = logging.getLogger(__name__)
            _logger.info(f"Scheduled email sent to {self.contact_email} for lead {self.opportunity_id.id if self.opportunity_id else 'N/A'}")
            
            return True
            
        except Exception as e:
            import logging
            _logger = logging.getLogger(__name__)
            _logger.exception(f"Error sending scheduled email {self.id}: {e}")
            
            self.write({
                'state': 'failed',
                'error_message': str(e)
            })
            
            # Log error to opportunity if exists
            if self.opportunity_id:
                from markupsafe import Markup
                self.opportunity_id.message_post(
                    body=Markup(f"<p><strong>✗ Scheduled Email Failed</strong><br/>To: {self.contact_email}<br/>Error: {str(e)}</p>"),
                    subject="Scheduled Lead-Back Email Failed"
                )
            
            return False
    
    @api.model
    def _cron_send_scheduled_emails(self):
        """Cron job to send scheduled emails that are due"""
        from datetime import datetime
        
        now = datetime.now()
        pending_emails = self.search([
            ('state', '=', 'pending'),
            ('scheduled_time', '<=', now)
        ])
        
        import logging
        _logger = logging.getLogger(__name__)
        _logger.info(f"Processing {len(pending_emails)} scheduled emails")
        
        for email in pending_emails:
            email._send_email()
        
        return True

class CrmLead(models.Model):
    _inherit = 'crm.lead'
    partner_vcard_id = fields.Many2one('partner.vcard', string='Partner vCard')
    service_request_answers = fields.Text(
        string='Service Request Answers',
        help='Structured summary of custom answers provided in the service request form.',
    )
    
    # Lead submission tracking (similar to referral tracking)
    submission_ip = fields.Char(
        string='Submission IP',
        help='IP address captured when the lead form was submitted'
    )
    submission_user_agent = fields.Char(
        string='Submission User Agent',
        help='Browser user agent string captured during form submission'
    )
    submission_fingerprint_hash = fields.Char(
        string='Submission Fingerprint',
        help='SHA-256 hash of browser fingerprint (IP, User-Agent, Accept headers, Language) captured during form submission'
    )
    submission_country = fields.Char(
        string='Submission Country',
        help='Country detected from IP address geolocation'
    )
    submission_city = fields.Char(
        string='Submission City',
        help='City detected from IP address geolocation'
    )
    submission_timezone = fields.Char(
        string='Submission Timezone',
        help='Timezone detected from IP address or browser'
    )
    submission_language = fields.Char(
        string='Submission Language',
        help='Browser language preference (Accept-Language header)'
    )
    submission_source_url = fields.Char(
        string='Source URL',
        help='The URL/referrer where the user came from before submitting the form'
    )
    submission_utm_source = fields.Char(
        string='UTM Source',
        help='UTM source parameter from the URL (if present)'
    )
    submission_utm_medium = fields.Char(
        string='UTM Medium',
        help='UTM medium parameter from the URL (if present)'
    )
    submission_utm_campaign = fields.Char(
        string='UTM Campaign',
        help='UTM campaign parameter from the URL (if present)'
    )
    submission_referral_code = fields.Char(
        string='Referral Code',
        help='Referral code (ref parameter) from the URL if the lead came from a referral link'
    )
    submission_device_type = fields.Char(
        string='Device Type',
        help='Detected device type (mobile, desktop, tablet) from user agent'
    )
    submission_browser = fields.Char(
        string='Browser',
        help='Detected browser name from user agent'
    )
    submission_os = fields.Char(
        string='Operating System',
        help='Detected operating system from user agent'
    )
    
    @api.model
    def default_get(self, fields_list):
        """Set default type to opportunity"""
        defaults = super().default_get(fields_list)
        if 'type' not in defaults:
            defaults['type'] = 'opportunity'
        return defaults
    
    @api.model
    def create(self, vals):
        """Override create - ensure it's an opportunity by default"""
        # Ensure it's an opportunity by default
        if 'type' not in vals:
            vals['type'] = 'opportunity'
        
        return super().create(vals)
    
    def write(self, vals):
        """Override write - integrations removed"""
        return super(CrmLead, self).write(vals)

class PartnerVCardSpeciality(models.Model):
    _name = 'partner.vcard.speciality'
    _description = 'Partner vCard Speciality'
    _order = 'name'
    
    name = fields.Char(string='Speciality', required=True)
    partner_id = fields.Many2one('partner.vcard', string='Partner vCard', required=True, ondelete='cascade')

class PartnerVCardService(models.Model):
    _name = 'partner.vcard.service'
    _description = 'Partner vCard Service'
    _order = 'sequence, name'
    
    name = fields.Char(string='Service Title', required=True)
    description = fields.Text(string='Description', required=True)
    price = fields.Char(string='Pricing', help='Enter pricing information (e.g., "$100/hour", "Starting at $500", "Free consultation")')
    show_pricing = fields.Boolean(string='Show Pricing', default=True, help='Display pricing on the vCard')
    thank_you_message = fields.Char(
        string='Thank You Message',
        default="Thank you! Your service request has been sent. We'll be in touch shortly.",
        help='Custom message shown after service request submission. If empty, a default message will be used.'
    )
    partner_id = fields.Many2one('partner.vcard', string='Partner vCard', required=True, ondelete='cascade')
    sequence = fields.Integer(string='Sequence', default=10, help='Display order')
    active = fields.Boolean(string='Active', default=True, help='Archive this service to hide it from the vCard without deleting it')
    question_ids = fields.One2many(
        'partner.vcard.service.question',
        'service_id',
        string='Custom Questions',
        help='Additional questions to ask when someone requests this service.',
    )
    
    @api.model
    def create(self, vals):
        """Create service - no limits"""
        return super(PartnerVCardService, self).create(vals)
    
    def write(self, vals):
        """Write service - no limits"""
        return super(PartnerVCardService, self).write(vals)


class PartnerVCardServiceQuestion(models.Model):
    _name = 'partner.vcard.service.question'
    _description = 'Service Request Question'
    _order = 'sequence, id'

    service_id = fields.Many2one(
        'partner.vcard.service',
        string='Service',
        required=True,
        ondelete='cascade',
    )
    name = fields.Char(string='Question', required=True)
    field_type = fields.Selection(
        [
            ('short_text', 'Short text'),
            ('long_text', 'Long text'),
            ('number', 'Number'),
            ('checkbox', 'Yes / No'),
            ('select', 'Dropdown'),
        ],
        string='Answer Type',
        default='short_text',
        required=True,
    )
    is_required = fields.Boolean(string='Required', default=False)
    sequence = fields.Integer(string='Sequence', default=10)
    options = fields.Char(
        string='Options',
        help='Comma-separated options for dropdown questions (e.g. "Option A, Option B, Option C").',
    )

class PartnerVCard(models.Model):
    _name = 'partner.vcard'
    _description = 'Partner vCard'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    
    name = fields.Char(string='Name')
    company_name = fields.Char(string='Company Name')
    street = fields.Char(string='Street')
    street2 = fields.Char(string='Street2')
    city = fields.Char(string='City')
    state_id = fields.Many2one('res.country.state', string='State')
    zip = fields.Char(string='ZIP')
    country_id = fields.Many2one('res.country', string='Country')
    function = fields.Char(string='Job Position')
    phone = fields.Char(string='Phone')
    mobile = fields.Char(string='Mobile')
    email = fields.Char(string='Email')
    website = fields.Char(string='Website')
    image_url = fields.Binary(string='Image')
    banner_image = fields.Binary(string='Banner Image', help='Upload a banner image that appears behind your profile picture (similar to LinkedIn)')
    title_id = fields.Many2one('res.partner.title', string='Title')
    website_ids = fields.One2many('partner.vcard.website', 'partner_id', string="Websites")
    video_ids = fields.One2many('partner.vcard.videos', 'partner_id', string="Videos")
    review_ids = fields.One2many('partner.vcard.reviews', 'partner_id', string="Reviews")
    speciality_ids = fields.One2many('partner.vcard.speciality', 'partner_id', string="Specialities")
    service_ids = fields.One2many('partner.vcard.service', 'partner_id', string="Services")
    show_services = fields.Boolean(string="Show Services Section", default=False, 
                                  help="Display the services section on the website")
    calendly_url = fields.Char(string="Calendar URL", help="Enter your Calendly URL (e.g., https://calendly.com/username). This will be displayed in the Calendar tab of the Minimal template.")
    
    # Reviews section settings
    reviews_section_title = fields.Char(string="Reviews Section Title", default="Reviews", 
                                      help="Title for the reviews section on the website")
    show_reviews = fields.Boolean(string="Show Reviews Section", default=True, 
                                help="Display the reviews section on the website")
    max_reviews_display = fields.Integer(string="Max Reviews to Display", default=5, 
                                       help="Maximum number of reviews to show on the website")
    carousel_autoscroll_speed = fields.Integer(string="Carousel Autoscroll Speed (seconds)", default=5, 
                                             help="Time in seconds between automatic carousel transitions (0 to disable autoscroll)")
    review_thank_you_message = fields.Char(
        string="Review Thank You Message",
        default="Thank you for your review! We appreciate your feedback.",
        help="Message displayed after review submission"
    )
    
    # Website Template
    website_template = fields.Selection([
        ('modern', 'Modern'),
        ('classic', 'Classic'),
        ('minimal', 'Minimal'),
        ('corporate', 'Corporate'),
        ('creative', 'Creative'),
    ], string='Website Template', default='modern', required=True,
       help='Choose the design template for your vCard website')
    
    # QR Code fields
    qr_pattern = fields.Selection(
        [
            ('square', 'Square'),
            ('dots', 'Dots'),
            ('classy', 'Classy'),
            ('classy-rounded', 'Classy Rounded'),
            ('rounded', 'Rounded')
        ],
        string="QR Code Pattern",
        default='square',
        help="Select the QR code pattern."
    )
    qr_logo = fields.Binary(
        string="QR Logo",
        help="Upload a logo to display in the center of the QR code."
    )
    qr_code = fields.Binary(string="QR Code")
    qr_code_data = fields.Char(
        string="QR Code Data",
        readonly=True,
        help="The data encoded in the QR code, generated once upon creation."
    )
    qr_code_scan_count = fields.Integer(string='QR Code Scan Count', default=0)
    page_view_count = fields.Integer(string='Page View Count', default=0, help='Total number of times the vCard page has been viewed')
    vcard_download_count = fields.Integer(string='vCard Download Count', default=0, help='Total number of times the vCard has been downloaded')
    download_tracking_ids = fields.One2many(
        'vcard.download.tracking',
        'partner_vcard_id',
        string='Download History',
        help='Detailed tracking records of all vCard downloads'
    )

    website_slug = fields.Char(string='Website Slug', help='Editable part of the website URL', required=False)
    website_full_url = fields.Char(string='Website URL', compute='_compute_website_full_url', store=True)
    website_page_id = fields.Many2one('website.page', string="Website Page", readonly=True)
    is_published = fields.Boolean(string='Published', compute='_compute_is_published', inverse='_inverse_is_published', store=False, help='Whether this vCard is published and accessible publicly')
    attachment_id = fields.Many2one('ir.attachment', string='Image Attachment', readonly=True)
    banner_attachment_id = fields.Many2one('ir.attachment', string='Banner Image Attachment', readonly=True)
    primary_color = fields.Char(string="Primary Color", help="This color is used as the background color for all vCard templates.", default="#ffffff")
    secondary_color = fields.Char(string="Secondary Color", help="This color is used for all accent elements (buttons, sections, highlights) across all templates.", default="#4C75A3")
    about = fields.Html(string="About", help="HTML content to describe the partner.")
    
    # Social media URLs
    whatsapp_url = fields.Char(string="WhatsApp URL", help="Enter the WhatsApp click-to-chat URL, e.g., https://wa.me/1XXXXXXXXXX")
    linkedin_url = fields.Char(string="LinkedIn URL", help="Enter the LinkedIn profile URL, e.g., https://www.linkedin.com/in/username")
    linkedin_url_company = fields.Char(string="LinkedIn URL (Company)", help="Enter the LinkedIn profile URL, e.g., https://www.linkedin.com/in/username")
    youtube_url = fields.Char(string="YouTube URL", help="Enter the YouTube channel or video URL, e.g., https://www.youtube.com/channel/CHANNEL_ID")
    facebook_url = fields.Char(string="Facebook URL", help="Enter the Facebook profile URL, e.g., https://www.facebook.com/username")
    facebook_url_company = fields.Char(string="Facebook URL (Company)", help="Enter the Facebook profile URL, e.g., https://www.facebook.com/username")
    telegram_url = fields.Char(string="Telegram URL", help="Enter the Telegram URL, e.g., https://t.me/username")
    instagram_url = fields.Char(string="Instagram URL", help="Enter the Instagram profile URL, e.g., https://www.instagram.com/username")
    instagram_url_company = fields.Char(string="Instagram URL (Company)", help="Enter the Instagram profile URL, e.g., https://www.instagram.com/username")
    tumblr_url = fields.Char(string="Tumblr URL", help="Enter the Tumblr profile URL, e.g., https://username.tumblr.com")
    xing_url = fields.Char(string="Xing URL", help="Enter the Xing profile URL, e.g., https://www.xing.com/profile/username")
    github_url = fields.Char(string="GitHub URL", help="Enter the GitHub profile URL, e.g., https://github.com/username")
    vimeo_url = fields.Char(string="Vimeo URL", help="Enter the Vimeo profile URL, e.g., https://vimeo.com/username")
    messenger_url = fields.Char(string="Facebook Messenger URL", help="Enter the Messenger URL, e.g., https://m.me/username")
    dribbble_url = fields.Char(string="Dribbble URL", help="Enter the Dribbble profile URL, e.g., https://dribbble.com/username")
    skype_url = fields.Char(string="Skype URL", help="Enter the Skype username, e.g., skype:username?call")
    doordash_url = fields.Char(string="DoorDash URL", help="Enter the DoorDash store URL, e.g., https://www.doordash.com/store/restaurant")
    tripadvisor_url = fields.Char(string="TripAdvisor URL", help="Enter the TripAdvisor profile URL, e.g., https://www.tripadvisor.com/Profile/username")
    yelp_url = fields.Char(string="Yelp URL", help="Enter the Yelp business URL, e.g., https://www.yelp.com/biz/username")
    twitter_url = fields.Char(string="Twitter URL", help="Enter the Twitter profile URL, e.g., https://www.twitter.com/username")
    twitter_url_company = fields.Char(string="Twitter URL (Company)", help="Enter the Twitter profile URL, e.g., https://www.twitter.com/username")
    google_reviews_url = fields.Char(string="Google Reviews URL", help="Enter the Google Reviews URL, e.g., https://g.page/username/review")
    ubereats_url = fields.Char(string="Uber Eats URL", help="Enter the Uber Eats store URL, e.g., https://www.ubereats.com/store/restaurant")
    line_url = fields.Char(string="Line URL", help="Enter the Line URL, e.g., https://line.me/R/ti/p/username")
    vkontakte_url = fields.Char(string="Vkontakte URL", help="Enter the Vkontakte profile URL, e.g., https://vk.com/username")
    reddit_url = fields.Char(string="Reddit URL", help="Enter the Reddit profile URL, e.g., https://www.reddit.com/user/username")
    viber_url = fields.Char(string="Viber URL", help="Enter the Viber URL, e.g., viber://chat?number=number")
    pinterest_url = fields.Char(string="Pinterest URL", help="Enter the Pinterest profile URL, e.g., https://www.pinterest.com/username")
    tiktok_url = fields.Char(string="TikTok URL", help="Enter the TikTok profile URL, e.g., https://www.tiktok.com/@username")
    snapchat_url = fields.Char(string="Snapchat URL", help="Enter the Snapchat profile URL, e.g., https://www.snapchat.com/add/username")
    signal_url = fields.Char(string="Signal URL", help="Enter the Signal phone number URL, e.g., https://signal.me/#p/number")
    
    # CRM and Opportunity fields
    crm_opportunity_ids = fields.One2many('crm.lead', 'partner_vcard_id', string='Opportunities', domain=[('type', '=', 'opportunity')])
    show_form = fields.Boolean(string="Show the lead collection form")
    lead_tag_ids = fields.Many2many('crm.tag', string='Lead Tags')
    lead_button_label = fields.Char(string="Lead Button Label", default="Leave Your Info", help="Label for the lead form button")
    form_thank_you_message = fields.Char(
        string="Form Thank You Message",
        help="Message displayed after form submission. If empty, a default message will be used."
    )
    notify_on_new_lead = fields.Boolean(
        string="Notify on New Lead",
        default=True,
        help="Send an email notification when a new lead is submitted through the form"
    )
    mailing_list_id = fields.Many2one(
        'mailing.list',
        string="Email Marketing List",
        help="Leads from this vCard will be added to this mailing list. Required if lead form is enabled.",
    )
    
    # Introduction Email Configuration
    intro_email_enabled = fields.Boolean(
        string="Send intro email automatically",
        default=False,
        help="Automatically send an introduction email to new leads. The email will be sent from notifications@vinculumapp.com with you CC'd and as the Reply-To address."
    )
    intro_email_template = fields.Html(
        string="Intro email template",
        default="<p>Hi {contact_name},</p><p>Great meeting you today. I'm {owner_name} (cc'd), here's my info and how to reach me:</p><p><strong>Email:</strong> {owner_email}<br/><strong>Phone:</strong> {owner_phone}<br/><strong>My vCard:</strong> <a href='{vcard_url}'>{vcard_url}</a></p>{if booking_url}<p>If you'd like to schedule a time to connect, you can book a slot here:</p><p><a href='{booking_url}'>{booking_url}</a></p>{/if}<p>Looking forward to connecting!<br/>{owner_name}</p>",
        help="HTML email template for the introduction email. Use placeholders like {contact_name}, {first_name}, {vcard_url}, {booking_url}, {owner_name}, {owner_email}, {owner_phone}. Use {placeholder|fallback} for fallback values. Use {if field}...{/if} for conditional blocks."
    )
    
    # Follow-up Reminders Configuration
    followup_reminders_enabled = fields.Boolean(
        string="Enable follow-up reminders",
        default=False,
        help="Automatically schedule follow-up activities for new leads based on your reminder templates"
    )
    followup_reminder_ids = fields.One2many(
        'followup.reminder',
        'partner_vcard_id',
        string="Follow-up Reminders",
        help="Configure one or more reminder templates to automatically schedule activities for new leads"
    )
    
    # Instant Lead-Back Configuration
    enable_instant_leadback = fields.Boolean(
        string="Instant Lead-Back",
        default=False,
        help="Automatically send email and messaging links to new contacts within 10 seconds of form submission"
    )
    leadback_send_email = fields.Boolean(
        string="Enable Automated Email",
        default=True,
        help="Automatically send an email to new leads using your email marketing system",
        invisible="enable_instant_leadback != True"
    )
    leadback_enable_messaging = fields.Boolean(
        string="Enable Click to Chat",
        default=True,
        help="Generate click-to-chat links for messaging platforms (WhatsApp, Viber, Telegram)",
        invisible="enable_instant_leadback != True"
    )
    leadback_email_template_preset = fields.Selection(
        [
            ('friendly', 'Friendly & Simple'),
            ('professional', 'Professional & Polished'),
            ('event', 'Event Mode'),
            ('follow_up', 'Follow-Up'),
            ('appointment', 'Appointment Booking'),
            ('custom', 'Custom'),
        ],
        string="Email Template",
        default='friendly',
        help="Choose a pre-built email template or create your own",
        invisible="enable_instant_leadback != True or leadback_send_email != True"
    )
    leadback_email_subject = fields.Char(
        string="Subject",
        default="Great connecting with you",
        help="Subject line for the automated welcome email",
        invisible="enable_instant_leadback != True or leadback_send_email != True"
    )
    leadback_email_template = fields.Html(
        string="Email Body",
        default="<p>Hi {contact_name},</p><p>Thanks again for sharing your contact details. Just wanted to let you know I received your message.</p>{if booking_url}<p>If you'd like to continue our conversation or set up some time, you can book a slot here:</p><p><a href='{booking_url}'>{booking_url}</a></p>{/if}<p>Talk soon,<br/>{owner_name}</p>",
        help="HTML email template. Use placeholders like {contact_name}, {first_name}, {vcard_url}, {booking_url}, {owner_name}. Use {placeholder|fallback} for fallback values. Use {if field}...{/if} for conditional blocks.",
        invisible="enable_instant_leadback != True or leadback_send_email != True or leadback_email_template_preset != 'custom'"
    )
    leadback_email_delay_preset = fields.Selection(
        [
            ('immediate', 'Immediate (0 min)'),
            ('1_min', '1 minute'),
            ('5_min', '5 minutes'),
            ('15_min', '15 minutes'),
            ('1_hour', '1 hour'),
            ('custom', 'Custom'),
        ],
        string="Email Delay Preset",
        default='immediate',
        help="Quick preset for email delay, or choose Custom to set manually",
        invisible="enable_instant_leadback != True or leadback_send_email != True"
    )
    leadback_email_delay_type = fields.Selection(
        [('minutes', 'Minutes'), ('hours', 'Hours'), ('days', 'Days')],
        string="Email Send Delay Type",
        default='minutes',
        help="Delay type for sending automated email (only used when Custom preset is selected)",
        invisible="enable_instant_leadback != True or leadback_send_email != True or leadback_email_delay_preset != 'custom'"
    )
    leadback_email_delay = fields.Integer(
        string="Email Delay",
        default=0,
        help="How long to wait before sending the email (only used when Custom preset is selected)",
        invisible="enable_instant_leadback != True or leadback_send_email != True or leadback_email_delay_preset != 'custom'"
    )
    leadback_message_template_preset = fields.Selection(
        [
            ('friendly', 'Friendly & Short'),
            ('event', 'Event Mode'),
            ('professional', 'Professional'),
            ('follow_up', 'Follow-Up'),
            ('custom', 'Custom'),
        ],
        string="Message Template",
        default='friendly',
        help="Choose a pre-built message template or create your own",
        invisible="enable_instant_leadback != True or leadback_enable_messaging != True"
    )
    leadback_message_template = fields.Text(
        string="Message Body",
        default="Hi {contact_name}! Thanks for sharing your details — I got your message.\n\n{if booking_url}If you'd like to continue the conversation or set up a time, here's my booking link:\n{booking_url}{/if}",
        help="Template for messaging links (WhatsApp/Viber/Telegram). Use placeholders like {contact_name}, {first_name}, {vcard_url}, {booking_url}, {owner_name}. Use {placeholder|fallback} for fallback values. Use {if field}...{/if} for conditional blocks.",
        invisible="enable_instant_leadback != True or leadback_enable_messaging != True or leadback_message_template_preset != 'custom'"
    )
    leadback_message_delay_preset = fields.Selection(
        [
            ('immediate', 'Immediate (0 min)'),
            ('1_min', '1 minute'),
            ('5_min', '5 minutes'),
            ('15_min', '15 minutes'),
            ('1_hour', '1 hour'),
            ('custom', 'Custom'),
        ],
        string="Message Delay Preset",
        default='immediate',
        help="Quick preset for message delay, or choose Custom to set manually",
        invisible="enable_instant_leadback != True or leadback_enable_messaging != True"
    )
    leadback_message_delay_type = fields.Selection(
        [('minutes', 'Minutes'), ('hours', 'Hours'), ('days', 'Days')],
        string="Message Send Delay Type",
        default='minutes',
        help="Delay type for generating messaging links (only used when Custom preset is selected)",
        invisible="enable_instant_leadback != True or leadback_enable_messaging != True or leadback_message_delay_preset != 'custom'"
    )
    leadback_message_delay = fields.Integer(
        string="Message Delay",
        default=0,
        help="How long to wait before generating messaging links (only used when Custom preset is selected)",
        invisible="enable_instant_leadback != True or leadback_enable_messaging != True or leadback_message_delay_preset != 'custom'"
    )
    leadback_channels = fields.Many2many(
        'leadback.messaging.channel',
        'partner_vcard_leadback_channel_rel',
        'partner_vcard_id',
        'channel_id',
        string="Messaging Channels",
        help="Select one or more messaging channels to send instant lead-back messages",
        invisible="enable_instant_leadback != True or leadback_enable_messaging != True"
    )
    
    # Digest Email Settings
    digest_enabled = fields.Boolean(
        string="Enable Digest Emails",
        default=True,
        help="Receive weekly digest emails with your Vinculum Card statistics"
    )
    digest_frequency = fields.Selection(
        [
            ('weekly', 'Weekly'),
            ('monthly', 'Monthly'),
            ('daily', 'Daily (only if activity)'),
        ],
        string="Digest Frequency",
        default='weekly',
        help="How often to receive digest emails. Daily emails are only sent if there's new activity."
    )
    last_digest_sent = fields.Datetime(
        string="Last Digest Sent",
        readonly=True,
        help="Timestamp of when the last digest email was sent"
    )
    
    # Computed fields
    vcard_opportunity_count = fields.Integer(compute='_compute_vcard_opportunity_count')
    vcard_email_contact_count = fields.Integer(compute='_compute_vcard_email_contact_count')
    has_socials = fields.Boolean(
        string="Has Social Media",
        compute="_compute_has_socials",
        store=False
    )
    referral_signup_url = fields.Char(
        string="Referral Signup URL",
        compute="_compute_referral_signup_url",
        store=True,  # Store it so it's always available in templates
        help="Signup URL with referral code for this vCard owner"
    )
    
    # Plan-based access fields
    has_grow_features = fields.Boolean(
        string="Has Grow Features",
        compute='_compute_plan_features',
        help="Whether the tenant has access to Grow plan features"
    )
    has_scale_features = fields.Boolean(
        string="Has Scale Features",
        compute='_compute_plan_features',
        help="Whether the tenant has access to Scale plan features"
    )
    subscription_plan = fields.Char(
        string="Subscription Plan",
        compute='_compute_plan_features',
        help="Current subscription plan code"
    )
    is_launch_plan = fields.Boolean(
        string="Is Launch Plan",
        compute='_compute_plan_features',
        help="Whether the tenant is on Launch plan"
    )
    template_readonly = fields.Boolean(
        string="Template Readonly",
        compute='_compute_template_readonly',
        help="Whether template selection should be readonly (Launch plan users can only use Modern)"
    )
    
    @api.depends()
    def _compute_plan_features(self):
        """Compute plan-based feature access - all features enabled"""
        for record in self:
            record.has_grow_features = True
            record.has_scale_features = True
            record.subscription_plan = 'scale'
            record.is_launch_plan = False
    
    @api.depends('website_template')
    def _compute_template_readonly(self):
        """Compute if template should be readonly - always False (all templates available)"""
        for record in self:
            record.template_readonly = False
    
    @api.depends()
    def _compute_referral_signup_url(self):
        """Compute the referral signup URL - simplified to /get-started"""
        for vcard in self:
            vcard.referral_signup_url = '/get-started'

    @api.depends(
        'whatsapp_url', 'linkedin_url', 'linkedin_url_company', 'youtube_url',
        'facebook_url', 'facebook_url_company', 'telegram_url',
        'instagram_url', 'instagram_url_company', 'tumblr_url', 'xing_url',
        'github_url', 'vimeo_url', 'messenger_url', 'dribbble_url',
        'skype_url', 'doordash_url', 'tripadvisor_url', 'yelp_url',
        'twitter_url', 'twitter_url_company', 'google_reviews_url',
        'ubereats_url', 'line_url', 'vkontakte_url', 'reddit_url',
        'viber_url', 'pinterest_url', 'tiktok_url', 'snapchat_url', 'signal_url'
    )
    def _compute_has_socials(self):
        for rec in self:
            social_urls = [
                rec.whatsapp_url, rec.linkedin_url, rec.linkedin_url_company, rec.youtube_url,
                rec.facebook_url, rec.facebook_url_company, rec.telegram_url,
                rec.instagram_url, rec.instagram_url_company, rec.tumblr_url, rec.xing_url,
                rec.github_url, rec.vimeo_url, rec.messenger_url, rec.dribbble_url,
                rec.skype_url, rec.doordash_url, rec.tripadvisor_url, rec.yelp_url,
                rec.twitter_url, rec.twitter_url_company, rec.google_reviews_url,
                rec.ubereats_url, rec.line_url, rec.vkontakte_url, rec.reddit_url,
                rec.viber_url, rec.pinterest_url, rec.tiktok_url, rec.snapchat_url, rec.signal_url
            ]
            rec.has_socials = any(social_urls)
            

    def get_referral_signup_url(self):
        """Get the referral signup URL - simplified to /get-started"""
        self.ensure_one()
        return '/get-started'
    
    @api.model
    def default_get(self, fields_list):
        """Override default_get - no limits applied"""
        result = super().default_get(fields_list)
        return result
    
    @api.model
    def create(self, vals):
        """Override create - no limits or tenant requirements"""
        return super().create(vals)
    
    
    @api.constrains('show_form', 'mailing_list_id')
    def _check_mailing_list_required(self):
        """Ensure mailing list is set when form is enabled"""
        for record in self:
            if record.show_form and not record.mailing_list_id:
                raise ValidationError(
                    'Please select an Email Marketing List. '
                    'This is required when the lead collection form is enabled.'
                )
    
    _sql_constraints = [
        ('website_slug_unique', 'unique(website_slug)', 
         'Website slug must be unique. Please choose a different slug. '
         'Note: Multiple NULL slugs are allowed (for unpublished vCards).')
    ]
    
    def copy(self, default=None):
        """Override copy to set slug to null so user must provide a unique slug"""
        if default is None:
            default = {}
        
        # Set slug to null - user must provide a unique slug before publishing
        default['website_slug'] = False
        default['website_page_id'] = False  # Don't copy the website page reference
        default['name'] = default.get('name', f"{self.name} (Copy)" if self.name else "Copy")
        default['is_published'] = False  # Unpublish the copy
        
        return super().copy(default)
    
    @api.constrains('website_slug', 'is_published')
    def _check_website_slug(self):
        """Validate website slug format and uniqueness - required when published"""
        for record in self:
            # Slug is only required when published or when generating website
            if record.is_published or record.website_page_id:
                if not record.website_slug:
                    raise ValidationError(
                        'Website slug is required to publish a vCard. Please enter a unique URL slug.'
                    )
                
                # Check for valid slug format (alphanumeric, hyphens, underscores)
                import re
                if not re.match(r'^[a-zA-Z0-9_-]+$', record.website_slug):
                    raise ValidationError(
                        'Website slug can only contain letters, numbers, hyphens, and underscores.'
                    )
                
                # Check uniqueness (slug must be globally unique)
                existing = self.search([
                    ('website_slug', '=', record.website_slug),
                    ('id', '!=', record.id)
                ])
                if existing:
                    raise ValidationError(
                        f'Website slug "{record.website_slug}" is already taken. Please choose a different slug.'
                    )
    
    @api.constrains('enable_instant_leadback', 'leadback_channels', 'leadback_send_email', 'leadback_enable_messaging')
    def _check_leadback_config_required(self):
        """Ensure at least email or messaging is configured when instant lead-back is enabled"""
        for record in self:
            if record.enable_instant_leadback:
                has_email = record.leadback_send_email
                has_messaging = record.leadback_enable_messaging and record.leadback_channels
                
                if not has_email and not has_messaging:
                    raise ValidationError(
                        'Please configure either:\n'
                        '• Enable "Enable Automated Email" (recommended), OR\n'
                        '• Enable "Enable Click to Chat" AND select at least one Message Channel\n\n'
                        'At least one method must be configured when Instant Lead-Back is enabled.'
                    )
                
                # If messaging is enabled, validate messaging requirements
                if record.leadback_enable_messaging:
                    if not record.leadback_channels:
                        raise ValidationError(
                            'Please select at least one Message Channel. '
                            'This is required when "Enable Click to Chat" is enabled.'
                        )
    
    @api.depends('crm_opportunity_ids')
    def _compute_vcard_opportunity_count(self):
        import logging
        _logger = logging.getLogger(__name__)
        
        for partner in self:
            _logger.info(f"=== COMPUTING VCARD OPPORTUNITY COUNT ===")
            _logger.info(f"Partner ID: {partner.id}")
            _logger.info(f"Current user: {self.env.user.name} (ID: {self.env.user.id})")
            
            # Check with sudo (all leads)
            all_leads = self.env['crm.lead'].sudo().search([
                ('partner_vcard_id', '=', partner.id),
                ('type', '=', 'opportunity')
            ])
            _logger.info(f"Total leads (with sudo): {len(all_leads)}")
            
            # Check without sudo (what user can see)
            user_leads = partner.crm_opportunity_ids
            _logger.info(f"Leads visible to user (crm_opportunity_ids): {len(user_leads)}")
            for lead in user_leads:
                _logger.info(f"  Lead ID: {lead.id}")
            
            partner.vcard_opportunity_count = len(partner.crm_opportunity_ids)
    
    def _compute_vcard_email_contact_count(self):
        """Count email contacts that came from this vCard's leads"""
        for partner in self:
            # Count contacts where email matches any lead from this vCard
            if partner.crm_opportunity_ids:
                lead_emails = partner.crm_opportunity_ids.mapped('email_from')
                contact_count = self.env['mailing.contact'].search_count([
                    ('email', 'in', lead_emails)
                ])
                partner.vcard_email_contact_count = contact_count
            else:
                partner.vcard_email_contact_count = 0

    def action_view_vcard_opportunities(self):
        """Action to view vCard opportunities."""
        self.ensure_one()
        
        import logging
        _logger = logging.getLogger(__name__)
        
        _logger.info(f"=== ACTION VIEW VCARD OPPORTUNITIES ===")
        _logger.info(f"Current user: {self.env.user.name} (ID: {self.env.user.id})")
        _logger.info(f"vCard ID: {self.id}")
        
        # Check what leads exist for this vCard
        all_leads = self.env['crm.lead'].sudo().search([
            ('partner_vcard_id', '=', self.id),
            ('type', '=', 'opportunity')
        ])
        _logger.info(f"Total leads for vCard (with sudo): {len(all_leads)}")
        for lead in all_leads:
            _logger.info(f"  Lead ID: {lead.id}, name: {lead.name}")
        
        # Check what leads the user can see (without sudo)
        user_leads = self.env['crm.lead'].search([
            ('partner_vcard_id', '=', self.id),
            ('type', '=', 'opportunity')
        ])
        _logger.info(f"Leads visible to user (without sudo): {len(user_leads)}")
        for lead in user_leads:
            _logger.info(f"  Lead ID: {lead.id}, name: {lead.name}")
    
        return {
            'type': 'ir.actions.act_window',
            'name': 'Leads',
            'view_mode': 'list,form',
            'res_model': 'crm.lead',
            'domain': [('partner_vcard_id', '=', self.id), ('type', '=', 'opportunity')],
            'context': {
                'default_partner_vcard_id': self.id,
                'default_type': 'opportunity',
            },
        }
    
    def action_view_tenant_mailing_lists(self):
        """Action to view mailing lists"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'My Mailing Lists',
            'view_mode': 'kanban,list,form',
            'res_model': 'mailing.list',
            'help': """
                <p class="o_view_nocontent_smiling_face">
                    Create your first mailing list!
                </p>
                <p>
                    Mailing lists help you organize your email contacts.
                    Create lists for different audiences (e.g., "Hot Leads", "Newsletter Subscribers").
                </p>
            """,
        }
    
    def action_view_vcard_email_contacts(self):
        """Action to view email contacts from this vCard's leads"""
        self.ensure_one()
        
        # Get all email addresses from leads collected via this vCard
        lead_emails = self.crm_opportunity_ids.mapped('email_from')
        
        return {
            'type': 'ir.actions.act_window',
            'name': f'Email Contacts from {self.name}',
            'view_mode': 'kanban,list,form',
            'res_model': 'mailing.contact',
            'domain': [
                ('email', 'in', lead_emails)
            ],
            'context': {
                'default_company_id': self.env.company.id,
                'search_default_exclude_optout': 1,
            },
            'help': """
                <p class="o_view_nocontent_smiling_face">
                    No email contacts yet from this vCard!
                </p>
                <p>
                    Email contacts will appear here when people fill out the lead form on this vCard page.
                </p>
            """,
        }
    
    def action_open_website(self):
        """Open the vCard website in a new tab, generate if needed"""
        self.ensure_one()
        if not self.website_full_url:
            # Generate the website first
            self.action_generate_website_page()
        
        if self.website_full_url:
            return {
                'type': 'ir.actions.act_url',
                'url': self.website_full_url,
                'target': 'new',
            }
        else:
            raise ValidationError('Website URL is not available. Please generate the website first.')

    def action_open_nfc_guide(self):
        """Open the NFC card programming guide"""
        self.ensure_one()
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        nfc_guide_url = f"{base_url}/nfc/setup/{self.id}"
        
        return {
            'type': 'ir.actions.act_url',
            'url': nfc_guide_url,
            'target': 'new',
        }

    def action_open_vinculum_guide(self):
        """Open the How to Use Vinculum guide"""
        self.ensure_one()
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        guide_url = f"{base_url}/vinculum/guide"
        
        return {
            'type': 'ir.actions.act_url',
            'url': guide_url,
            'target': 'new',
        }
    
    @api.depends('website_page_id', 'website_page_id.is_published')
    def _compute_is_published(self):
        """Compute published status from website page"""
        for record in self:
            record.is_published = record.website_page_id.is_published if record.website_page_id else False
    
    def _inverse_is_published(self):
        """Publish/unpublish vCard by updating website page"""
        import logging
        _logger = logging.getLogger(__name__)
        for record in self:
            if record.website_page_id:
                record.website_page_id.sudo().write({'is_published': record.is_published})
                _logger.info(f"vCard {record.id} ({record.name}) publish status changed to: {record.is_published}")
            elif record.is_published and record.website_slug:
                # If trying to publish but page doesn't exist, generate it first
                record.action_generate_website_page()
                if record.website_page_id:
                    record.website_page_id.sudo().write({'is_published': True})
                    _logger.info(f"Generated and published vCard {record.id} ({record.name})")
    
    def _get_digest_stats(self, period_start=None, period_end=None):
        """Gather statistics for digest email"""
        self.ensure_one()
        from datetime import datetime, timedelta
        
        if not period_end:
            period_end = datetime.now()
        if not period_start:
            # Default to last 7 days for weekly, 30 for monthly, 1 for daily
            if self.digest_frequency == 'daily':
                period_start = period_end - timedelta(days=1)
            elif self.digest_frequency == 'monthly':
                period_start = period_end - timedelta(days=30)
            else:  # weekly
                period_start = period_end - timedelta(days=7)
        
        # Get all leads for this vCard
        all_leads = self.crm_opportunity_ids
        
        # Leads captured in the period
        new_leads = all_leads.filtered(
            lambda l: l.create_date and period_start <= l.create_date <= period_end
        )
        total_leads = len(all_leads)
        
        # Leads without follow-up (no activity scheduled at all - any type)
        leads_without_followup = all_leads.filtered(
            lambda l: not l.activity_ids.filtered(
                lambda a: a.date_deadline  # Any activity with a due date
            )
        )
        
        # Follow-up reminders (activities due or overdue - these ARE scheduled but need attention)
        today = datetime.now().date()
        due_followups = []
        for lead in all_leads:
            # Check for any activity with a due date (not just reminders)
            activities = lead.activity_ids.filtered(
                lambda a: a.date_deadline
            )
            for activity in activities:
                if activity.date_deadline and activity.date_deadline <= today:
                    due_followups.append({
                        'lead_name': lead.name,
                        'activity_summary': activity.summary or activity.activity_type_id.name or 'Follow-up',
                        'date_deadline': activity.date_deadline,
                        'overdue': activity.date_deadline < today
                    })
        
        # Leads per stage (CRM pipeline stages)
        leads_by_stage = {}
        for lead in all_leads:
            stage_name = lead.stage_id.name if lead.stage_id else 'New'
            if stage_name not in leads_by_stage:
                leads_by_stage[stage_name] = 0
            leads_by_stage[stage_name] += 1
        
        # Usage stats
        scans_count = self.qr_code_scan_count  # Total QR code scans (tracked via /qr/<partner_id> route)
        page_views = self.page_view_count  # Total page views (tracked when someone visits /{slug})
        
        return {
            'new_leads_count': len(new_leads),
            'total_leads_count': total_leads,
            'leads_without_followup_count': len(leads_without_followup),
            'due_followups': due_followups,
            'due_followups_count': len(due_followups),
            'leads_by_stage': leads_by_stage,
            'scans_count': scans_count,
            'page_views': page_views,
            'period_start': period_start,
            'period_end': period_end,
        }
    
    def _send_digest_email(self, force_send=False):
        """Send digest email to vCard owner
        
        Args:
            force_send: If True, bypass daily activity check (for testing)
        """
        self.ensure_one()
        
        if not self.digest_enabled or not self.email:
            return False
        
        # For daily frequency, check if there's activity (unless force_send is True)
        if self.digest_frequency == 'daily' and not force_send:
            stats = self._get_digest_stats()
            if stats['new_leads_count'] == 0 and stats['due_followups_count'] == 0:
                # No activity, skip sending
                return False
        
        # Gather stats
        stats = self._get_digest_stats()
        
        # Get email template
        template = self.env.ref('qr_code_odoo.email_template_digest', raise_if_not_found=False)
        if not template:
            import logging
            _logger = logging.getLogger(__name__)
            _logger.warning("Digest email template not found")
            return False
        
        # Prepare email context
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        vcard_url = self.website_full_url or f"{base_url}/web#id={self.id}&model=partner.vcard"
        
        # Format period for display
        period_display = ""
        if self.digest_frequency == 'daily':
            period_display = "Today"
        elif self.digest_frequency == 'weekly':
            period_display = "This Week"
        else:  # monthly
            period_display = "This Month"
        
        # Render the template with context
        email_ctx = {
            'vcard': self,
            'stats': stats,
            'vcard_url': vcard_url,
            'period_display': period_display,
            'base_url': base_url,
        }
        
        # Send email
        try:
            # Build the email body using Python string formatting for reliability
            from markupsafe import Markup
            
            # Format follow-ups list
            followups_html = ""
            if stats['due_followups']:
                followups_list = ""
                for followup in stats['due_followups'][:5]:
                    overdue_text = " <span style='color: #dc3545;'>(Overdue)</span>" if followup.get('overdue') else ""
                    followups_list += f"<li style='margin-bottom: 5px;'><strong>{followup.get('lead_name', 'Lead')}</strong> - {followup.get('activity_summary', 'Follow-up')}{overdue_text}</li>"
                
                if len(stats['due_followups']) > 5:
                    followups_list += f"<p style='margin: 10px 0 0 0; color: #666; font-size: 12px;'>... and {len(stats['due_followups']) - 5} more</p>"
                
                followups_html = f"""
                    <ul style="margin: 10px 0 0 0; padding-left: 20px; color: #666;">
                        {followups_list}
                    </ul>
                """
            else:
                followups_html = "<p style='margin: 10px 0 0 0; color: #28a745;'>✓ All caught up! No follow-ups due.</p>"
            
            # Format leads by stage
            leads_by_stage_html = ""
            if stats.get('leads_by_stage'):
                stage_items = []
                for stage_name, count in sorted(stats['leads_by_stage'].items()):
                    stage_items.append(f"<div style='display: flex; justify-content: space-between; margin-bottom: 8px;'><span style='color: #666;'>{stage_name}:</span><strong style='color: #333; font-size: 16px;'>{count}</strong></div>")
                leads_by_stage_html = "".join(stage_items)
            else:
                leads_by_stage_html = "<p style='color: #999; font-size: 12px; margin: 0;'>No leads yet</p>"
            
            # QR code status
            qr_status = "✓ <span style='color: #28a745; font-weight: bold;'>Yes</span>" if stats['qr_code_programmed'] else "✗ <span style='color: #dc3545; font-weight: bold;'>Not yet</span>"
            qr_link = "" if stats['qr_code_programmed'] else f"""
                <p style="margin: 5px 0 0 0; font-size: 12px; color: #666;">
                    <a href="{base_url}/web#id={self.id}&model=partner.vcard&view_type=form" 
                       style="color: #007bff; text-decoration: none;">Program your card →</a>
                </p>
            """
            
            # Build HTML body
            body_html = f"""
            <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; background-color: #ffffff;">
                <!-- Header -->
                <div style="text-align: center; padding: 20px 0; border-bottom: 2px solid #e0e0e0;">
                    <h1 style="margin: 0; color: #333; font-size: 24px;">📊 Your Vinculum Card Digest</h1>
                    <p style="margin: 10px 0 0 0; color: #666; font-size: 14px;">{period_display}</p>
                </div>

                <!-- Stats Overview -->
                <div style="padding: 30px 0;">
                    <h2 style="color: #333; font-size: 20px; margin: 0 0 20px 0;">📈 Quick Stats</h2>
                    
                    <!-- Leads Section -->
                    <div style="background: ' + (partner.primary_color or '#ffffff') + '; padding: 20px; border-radius: 8px; margin-bottom: 20px;">
                        <h3 style="color: #333; font-size: 18px; margin: 0 0 15px 0;">🎯 Leads Captured</h3>
                        <div style="display: flex; justify-content: space-between; margin-bottom: 10px;">
                            <span style="color: #666;">New Leads:</span>
                            <strong style="color: #007bff; font-size: 18px;">{stats['new_leads_count']}</strong>
                        </div>
                        <p style="margin: 0 0 10px 0; color: #999; font-size: 11px; font-style: italic;">Leads captured in the {period_display.lower()}</p>
                        <div style="display: flex; justify-content: space-between; margin-bottom: 10px;">
                            <span style="color: #666;">Total Leads:</span>
                            <strong style="color: #333; font-size: 18px;">{stats['total_leads_count']}</strong>
                        </div>
                        <p style="margin: 0 0 10px 0; color: #999; font-size: 11px; font-style: italic;">All-time total leads captured from this Vinculum Card</p>
                        <div style="display: flex; justify-content: space-between;">
                            <span style="color: #666;">Without Follow-up:</span>
                            <strong style="color: #dc3545; font-size: 18px;">{stats['leads_without_followup_count']}</strong>
                        </div>
                        <p style="margin: 0 0 15px 0; color: #999; font-size: 11px; font-style: italic;">Leads that have NO scheduled activity (any type) with a due date</p>
                        
                        <!-- Leads by Stage -->
                        <div style="border-top: 1px solid #dee2e6; padding-top: 15px; margin-top: 15px;">
                            <h4 style="color: #333; font-size: 16px; margin: 0 0 10px 0;">Leads by Stage</h4>
                            {leads_by_stage_html}
                            <p style="margin: 10px 0 0 0; color: #999; font-size: 11px; font-style: italic;">Breakdown of leads across your CRM pipeline stages</p>
                        </div>
                    </div>

                    <!-- Follow-ups Section -->
                    <div style="background: #fff3cd; padding: 20px; border-radius: 8px; margin-bottom: 20px; border-left: 4px solid #ffc107;">
                        <h3 style="color: #333; font-size: 18px; margin: 0 0 15px 0;">⏰ Follow-up Reminders</h3>
                        <p style="margin: 0 0 10px 0; color: #666;">
                            <strong style="color: #dc3545; font-size: 18px;">{stats['due_followups_count']}</strong> 
                            <span style="color: #666;">due or overdue</span>
                        </p>
                        <p style="margin: 0 0 10px 0; color: #999; font-size: 11px; font-style: italic;">Leads that HAVE scheduled activities (any type) with due dates on or before today (these need your attention now)</p>
                        {followups_html}
                    </div>

                    <!-- Onboarding Section -->
                    <div style="background: rgba(69, 126, 184, 0.1); padding: 20px; border-radius: 8px; margin-bottom: 20px; border-left: 4px solid #457eb8;">
                        <h3 style="color: #333; font-size: 18px; margin: 0 0 15px 0;">🚀 Onboarding Status</h3>
                        <div style="margin-bottom: 10px;">
                            <div style="display: flex; justify-content: space-between; margin-bottom: 5px;">
                                <span style="color: #666;">Profile Completeness:</span>
                                <strong style="color: #457eb8; font-size: 18px;">{stats['profile_completeness']}%</strong>
                            </div>
                            <div style="background: #e9ecef; height: 8px; border-radius: 4px; overflow: hidden; margin-top: 5px;">
                                <div style="background: #457eb8; height: 100%; width: {stats['profile_completeness']}%;"></div>
                            </div>
                            <p style="margin: 5px 0 0 0; color: #999; font-size: 11px; font-style: italic;">Based on core info (40%), contact details (20%), address (15%), content & branding (15%), and social links (10%)</p>
                        </div>
                        <div style="margin-top: 15px;">
                            <span style="color: #666;">QR Code Programmed:</span> {qr_status}
                            {qr_link}
                            <p style="margin: 5px 0 0 0; color: #999; font-size: 11px; font-style: italic;">Whether your QR code has been generated and is ready to use</p>
                        </div>
                    </div>

                    <!-- Usage Section -->
                    <div style="background: ' + (partner.primary_color or '#ffffff') + '; padding: 20px; border-radius: 8px; margin-bottom: 20px;">
                        <h3 style="color: #333; font-size: 18px; margin: 0 0 15px 0;">📱 Usage Stats</h3>
                        <div style="display: flex; justify-content: space-between; margin-bottom: 10px;">
                            <span style="color: #666;">Page Views:</span>
                            <strong style="color: #333; font-size: 18px;">{stats['page_views']}</strong>
                        </div>
                        <p style="margin: 0 0 10px 0; color: #999; font-size: 11px; font-style: italic;">Total number of times your Vinculum Card page has been viewed (via your unique URL)</p>
                        <div style="display: flex; justify-content: space-between;">
                            <span style="color: #666;">QR Code Scans:</span>
                            <strong style="color: #333; font-size: 18px;">{stats['scans_count']}</strong>
                        </div>
                        <p style="margin: 5px 0 0 0; color: #999; font-size: 11px; font-style: italic;">Total number of times your QR code has been scanned</p>
                    </div>

                    <!-- Referral Stats Section -->
                    {self._get_referral_stats_html(stats.get('referral_stats', {}))}
                </div>

                <!-- CTA Section -->
                <div style="text-align: center; padding: 30px 0; border-top: 2px solid #e0e0e0;">
                    <a href="{vcard_url}" 
                       style="display: inline-block; background-color: #457eb8; color: #ffffff; padding: 12px 30px; text-decoration: none; border-radius: 5px; font-weight: bold; font-size: 16px;">
                        View Your Vinculum Card →
                    </a>
                    <p style="margin: 20px 0 0 0; color: #666; font-size: 12px;">
                        <a href="{base_url}/web#id={self.id}&model=partner.vcard&view_type=form&active_id={self.id}" 
                           style="color: #007bff; text-decoration: none;">Manage Digest Settings</a>
                    </p>
                </div>

                <!-- Footer -->
                <div style="text-align: center; padding: 20px 0; border-top: 1px solid #e0e0e0; color: #999; font-size: 12px;">
                    <p style="margin: 0;">This is an automated digest email from Vinculum.</p>
                    <p style="margin: 5px 0 0 0;">You can change your digest preferences in your Vinculum Card settings.</p>
                </div>
            </div>
            """
            
            # Create mail values
            mail_values = {
                'subject': f"{period_display}'s Digest - {self.name or 'Your Vinculum Card'}",
                'body_html': Markup(body_html),
                'email_from': 'notifications@vinculumapp.com',
                'email_to': self.email,
                'auto_delete': True,
                'model': 'partner.vcard',
                'res_id': self.id,
            }
            
            # Send the email
            mail = self.env['mail.mail'].sudo().create(mail_values)
            mail.send()
            
            # Update last_digest_sent
            self.write({'last_digest_sent': fields.Datetime.now()})
            return True
        except Exception as e:
            import logging
            _logger = logging.getLogger(__name__)
            _logger.error(f"Error sending digest email to {self.email}: {str(e)}")
            return False
    
    @api.model
    def _cron_send_digest_emails(self):
        """Cron job to send digest emails to all eligible vCards"""
        from datetime import datetime, timedelta
        
        now = datetime.now()
        
        # Get all vCards with digest enabled
        vcards = self.search([
            ('digest_enabled', '=', True),
            ('email', '!=', False),
        ])
        
        for vcard in vcards:
            # Check if it's time to send based on frequency
            should_send = False
            
            if not vcard.last_digest_sent:
                # Never sent, send now
                should_send = True
            else:
                last_sent = fields.Datetime.from_string(vcard.last_digest_sent)
                time_since_last = now - last_sent
                
                if vcard.digest_frequency == 'daily':
                    # Daily: send if 24+ hours have passed
                    should_send = time_since_last >= timedelta(days=1)
                elif vcard.digest_frequency == 'weekly':
                    # Weekly: send if 7+ days have passed
                    should_send = time_since_last >= timedelta(days=7)
                elif vcard.digest_frequency == 'monthly':
                    # Monthly: send if 30+ days have passed
                    should_send = time_since_last >= timedelta(days=30)
            
            if should_send:
                vcard._send_digest_email()
    
    def action_send_test_digest(self):
        """Send a test digest email immediately (for testing purposes)"""
        self.ensure_one()
        
        if not self.email:
            raise UserError('Please set an email address on your Vinculum Card to receive digest emails.')
        
        if not self.digest_enabled:
            raise UserError('Please enable digest emails first.')
        
        result = self._send_digest_email(force_send=True)
        
        if result:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Success',
                    'message': f'Test digest email sent to {self.email}',
                    'type': 'success',
                    'sticky': False,
                }
            }
        else:
            raise UserError('Failed to send digest email. Please check the logs for details.')
    
    def action_test_intro_email(self):
        """Preview intro email template with sample data"""
        self.ensure_one()
        from odoo.exceptions import UserError
        
        if not self.intro_email_enabled:
            raise UserError("Please enable 'Send intro email automatically' first.")
        
        # Prepare template variables
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        vcard_url = self.website_full_url or f"{base_url}/{self.website_slug}" if self.website_slug else base_url
        booking_url = self.calendly_url or vcard_url
        
        template_vars = {
            'contact_name': 'John Smith',
            'first_name': 'John',
            'vcard_url': vcard_url,
            'booking_url': booking_url,
            'owner_name': self.name or 'Your Name',
            'owner_phone': self.phone or self.mobile or '+1234567890',
            'owner_email': self.email or 'you@example.com',
            'company_name': self.company_name or 'Your Company',
            'owner_title': self.function or 'Your Title',
        }
        
        # Get email template and process it
        email_template = self.intro_email_template or "<p>Hi {contact_name},</p><p>Great meeting you today. I'm {owner_name} (cc'd), here's my info and how to reach me:</p><p><strong>Email:</strong> {owner_email}<br/><strong>Phone:</strong> {owner_phone}<br/><strong>My vCard:</strong> <a href='{vcard_url}'>{vcard_url}</a></p><p>Looking forward to connecting!<br/>{owner_name}</p>"
        
        # Process template with fallbacks and conditionals
        body_html = self._process_template(email_template, template_vars)
        subject = f'Great meeting you today - {self.name or "Your Name"}'
        
        # Create preview record
        preview = self.env['leadback.preview'].create({
            'preview_type': 'email',
            'subject': subject,
            'body_html': body_html,
            'email_to': 'john.smith@example.com',
            'email_from': 'notifications@vinculumapp.com',
        })
        
        return {
            'type': 'ir.actions.act_window',
            'name': 'Intro Email Preview',
            'res_model': 'leadback.preview',
            'res_id': preview.id,
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_preview_type': 'email'},
        }
    
    def action_test_email(self):
        """Preview email template with sample data"""
        self.ensure_one()
        from odoo.exceptions import UserError
        
        if not self.leadback_send_email:
            raise UserError("Please enable 'Enable Automated Email' first.")
        
        # Prepare template variables
        vcard_url = self.website_full_url or f"{self.env['ir.config_parameter'].sudo().get_param('web.base.url')}/{self.website_slug}"
        booking_url = self.calendly_url or ''
        
        template_vars = {
            'contact_name': 'John Smith',
            'first_name': 'John',
            'vcard_url': vcard_url,
            'short_vcard_url': vcard_url,
            'booking_url': booking_url,
            'owner_name': self.name or 'Your Name',
            'owner_phone': self.phone or self.mobile or '+1234567890',
            'owner_email': self.email or 'you@example.com',
            'company_name': self.company_name or 'Your Company',
            'owner_title': self.function or 'Your Title',
            'lead_source': 'QR Code',
            'event_name': 'Sample Event',
            'profile_variant': 'Standard',
        }
        
        # Process templates
        subject = self._process_template(self.leadback_email_subject or 'Test Email', template_vars)
        body_html = self._process_template(self.leadback_email_template or '<p>Test email</p>', template_vars)
        
        # Create preview record
        preview = self.env['leadback.preview'].create({
            'preview_type': 'email',
            'subject': subject,
            'body_html': body_html,
            'email_to': 'john.smith@example.com',
            'email_from': self.email or self.env.user.email or 'you@example.com',
        })
        
        return {
            'type': 'ir.actions.act_window',
            'name': 'Email Preview',
            'res_model': 'leadback.preview',
            'res_id': preview.id,
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_preview_type': 'email'},
        }
    
    def action_test_message(self):
        """Generate test messaging links"""
        self.ensure_one()
        from odoo.exceptions import UserError
        
        if not self.leadback_enable_messaging:
            raise UserError("Please enable 'Enable Click to Chat' first.")
        
        if not self.leadback_channels:
            raise UserError("Please select at least one messaging channel.")
        
        # Prepare template variables
        vcard_url = self.website_full_url or f"{self.env['ir.config_parameter'].sudo().get_param('web.base.url')}/{self.website_slug}"
        booking_url = self.calendly_url or ''
        
        template_vars = {
            'contact_name': 'Test Contact',
            'first_name': 'Test',
            'vcard_url': vcard_url,
            'short_vcard_url': vcard_url,
            'booking_url': booking_url,
            'owner_name': self.name or 'me',
            'owner_phone': self.phone or self.mobile or '',
            'owner_email': self.email or '',
            'company_name': self.company_name or '',
            'owner_title': self.function or '',
            'lead_source': 'Test',
            'event_name': '',
            'profile_variant': '',
        }
        
        # Process message template
        message_text = self._process_template(self.leadback_message_template or 'Test message', template_vars)
        
        # Generate test links (using a test phone number)
        test_phone = '+1234567890'
        links = []
        channel_names = []
        
        for channel in self.leadback_channels:
            channel_names.append(channel.name)
            if channel.name == 'WhatsApp':
                result = self._send_whatsapp_message(test_phone, message_text)
                if result.get('status') == 'success' and result.get('url'):
                    links.append({
                        'name': 'WhatsApp',
                        'url': result['url'],
                        'icon': '💬'
                    })
            elif channel.name == 'Viber':
                result = self._send_viber_message(test_phone, message_text)
                if result.get('status') == 'success' and result.get('url'):
                    links.append({
                        'name': 'Viber',
                        'url': result['url'],
                        'icon': '💜'
                    })
            elif channel.name == 'Telegram':
                result = self._send_telegram_message(test_phone, message_text)
                if result.get('status') == 'success' and result.get('url'):
                    links.append({
                        'name': 'Telegram',
                        'url': result['url'],
                        'icon': '✈️'
                    })
        
        if not links:
            raise UserError("Failed to generate test links. Please check your channel configuration.")
        
        # Create links HTML
        links_html = '<br/>'.join([
            f'<div style="margin: 8px 0;"><strong>{link["icon"]} {link["name"]}:</strong> <a href="{link["url"]}" target="_blank" style="color: #0066cc; word-break: break-all;">{link["url"]}</a></div>'
            for link in links
        ])
        
        # Create preview record
        preview = self.env['leadback.preview'].create({
            'preview_type': 'message',
            'message_preview': message_text,
            'message_to': '+1234567890 (Test Phone)',
            'channels': ', '.join(channel_names),
            'links_html': links_html,
        })
        
        return {
            'type': 'ir.actions.act_window',
            'name': 'Message Preview',
            'res_model': 'leadback.preview',
            'res_id': preview.id,
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_preview_type': 'message'},
        }
    
    def _send_instant_leadback_message(self, contact_name, contact_phone, contact_email, opportunity):
        """
        Send instant lead-back message to a new contact via email (automated) and messaging links (click-to-chat).
        
        :param contact_name: Name of the contact
        :param contact_phone: Phone number of the contact
        :param contact_email: Email of the contact
        :param opportunity: CRM lead/opportunity record
        :return: dict with status and message
        """
        self.ensure_one()
        
        try:
            if not self.enable_instant_leadback:
                return {'status': 'disabled', 'message': 'Instant lead-back is disabled'}
            
            # Check if at least email or messaging is configured
            has_email = self.leadback_send_email and contact_email
            has_messaging = self.leadback_enable_messaging and contact_phone and self.leadback_channels
            
            if not has_email and not has_messaging:
                return {'status': 'error', 'message': 'Either email or phone messaging must be configured'}
            
            # Validate messaging requirements if messaging is enabled
            if self.leadback_enable_messaging and contact_phone:
                if not self.leadback_channels:
                    return {'status': 'error', 'message': 'No messaging channels selected'}
            
            # Prepare template variables
            base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
            vcard_url = self.website_full_url or f"{base_url}/{self.website_slug}" if self.website_slug else base_url
            booking_url = self.calendly_url or vcard_url
            
            # Extract first name from contact name
            first_name = contact_name.split()[0] if contact_name and ' ' in contact_name else (contact_name or 'there')
            
            template_vars = {
                'contact_name': contact_name or 'there',
                'first_name': first_name,
                'vcard_url': vcard_url,
                'short_vcard_url': vcard_url,
                'booking_url': booking_url,
                'owner_name': self.name or 'me',
                'owner_phone': self.phone or self.mobile or '',
                'owner_email': self.email or '',
                'company_name': self.company_name or '',
                'owner_title': self.function or '',
                'lead_source': 'QR Code',
                'event_name': '',
                'profile_variant': '',
            }
            
            # Process message template with fallbacks and conditionals
            message_template = (self.leadback_message_template or 
                              "Hi {first_name|there}! 👋\n\nGreat meeting you — here's my contact card:\n{vcard_url}")
            message = self._process_template(message_template, template_vars)
            
            # Schedule or send messages to all selected channels (only if messaging is enabled)
            results = []
            channel_names = []
            
            if self.leadback_enable_messaging and has_messaging:
                # Calculate message delay
                message_delay_amount = self.leadback_message_delay or 0
                message_delay_type = self.leadback_message_delay_type or 'minutes'
                
                try:
                    # If there's a delay, we'll generate links immediately but log them as scheduled
                    # (Since click-to-chat links can't be "scheduled", we generate them but note the delay)
                    for channel in self.leadback_channels:
                        try:
                            if channel.code == 'whatsapp':
                                result = self._send_whatsapp_message(contact_phone, message)
                            elif channel.code == 'viber':
                                result = self._send_viber_message(contact_phone, message)
                            elif channel.code == 'telegram':
                                result = self._send_telegram_message(contact_phone, message)
                            else:
                                result = {'status': 'error', 'message': f'Unknown channel code: {channel.code}'}
                            
                            results.append({
                                'channel': channel.name,
                                'code': channel.code,
                                'result': result
                            })
                            channel_names.append(channel.name)
                            
                        except Exception as e:
                            import logging
                            _logger = logging.getLogger(__name__)
                            _logger.exception(f"Error sending message via {channel.name}: {e}")
                            results.append({
                                'channel': channel.name,
                                'code': channel.code,
                                'result': {'status': 'error', 'message': str(e)}
                            })
                except Exception as e:
                    import logging
                    _logger = logging.getLogger(__name__)
                    _logger.exception(f"Error in messaging loop: {e}")
            
            # Schedule or send automated email if enabled
            email_scheduled = False
            if self.leadback_send_email and contact_email:
                try:
                    email_result = self._schedule_automated_email(contact_name, contact_email, opportunity, template_vars)
                    email_scheduled = email_result.get('status') in ['success', 'scheduled']
                except Exception as e:
                    import logging
                    _logger = logging.getLogger(__name__)
                    _logger.exception(f"Error scheduling automated email: {e}")
            
            # Log messages to lead timeline
            if opportunity:
                # Build status message
                status_parts = []
                if email_scheduled:
                    delay_info = self._get_delay_info(self.leadback_email_delay_type, self.leadback_email_delay)
                    if delay_info:
                        status_parts.append(f"Email: Scheduled ({delay_info})")
                    else:
                        status_parts.append("Email: Sent")
                if results:
                    success_count = sum(1 for r in results if r['result'].get('status') == 'success')
                    total_count = len(results)
                    delay_info = self._get_delay_info(self.leadback_message_delay_type, self.leadback_message_delay)
                    if delay_info:
                        status_parts.append(f"Messaging: Scheduled ({delay_info})")
                    else:
                        status_parts.append(f"Messaging: {success_count}/{total_count} links")
                
                status_str = " | ".join(status_parts) if status_parts else "No actions"
                
                # Build message content
                message_parts = []
                if email_scheduled:
                    delay_info = self._get_delay_info(self.leadback_email_delay_type, self.leadback_email_delay)
                    if delay_info:
                        message_parts.append(f"<p><strong>✓ Automated Email Scheduled</strong><br/>To: {contact_email}<br/>Will send in: {delay_info}</p>")
                    else:
                        message_parts.append(f"<p><strong>✓ Automated Email Sent</strong><br/>To: {contact_email}</p>")
                
                if results:
                    success_count = sum(1 for r in results if r['result'].get('status') == 'success')
                    if success_count > 0:
                        channels_str = ', '.join(channel_names)
                        task_links = []
                        for result_item in results:
                            if result_item['result'].get('status') == 'success' and result_item['result'].get('url'):
                                url = result_item['result'].get('url')
                                task_links.append(
                                    f"<li><a href='{url}' target='_blank'>{result_item['channel']}</a></li>"
                                )
                        
                        if task_links:
                            links_html = "".join(task_links)
                            message_parts.append(
                                f"<p><strong>Messaging Links Generated ({channels_str})</strong><br/>"
                                f"To: {contact_phone}<br/>"
                                f"Links: <ul style='margin: 5px 0;'>{links_html}</ul></p>"
                            )
                
                if message_parts:
                    body_message = Markup(
                        f"<p><strong>Instant Lead-Back Sent</strong></p>"
                        f"{''.join(message_parts)}"
                        f"<p><em>Status: {status_str}</em></p>"
                    )
                    opportunity.message_post(
                        body=body_message,
                        subject="Instant Lead-Back"
                    )
                    
                    # Log individual failures
                    for result_item in results:
                        if result_item['result'].get('status') != 'success':
                            opportunity.message_post(
                                body=f"<p><strong>Instant Lead-Back Message Failed</strong></p>"
                                     f"<p>Channel: {result_item['channel']}</p>"
                                     f"<p>To: {contact_phone}</p>"
                                     f"<p>Error: {result_item['result'].get('message', 'Unknown error')}</p>",
                                subject=f"Instant Lead-Back Failed - {result_item['channel']}"
                            )
                
                # Return summary
                success_count = sum(1 for r in results if r['result'].get('status') == 'success')
                if success_count == len(results):
                    return {'status': 'success', 'message': f'Messages sent via {", ".join(channel_names)}', 'results': results}
                elif success_count > 0:
                    return {'status': 'partial', 'message': f'{success_count}/{len(results)} messages sent', 'results': results}
                else:
                    return {'status': 'error', 'message': 'All message attempts failed', 'results': results}
                    
        except Exception as e:
            import logging
            _logger = logging.getLogger(__name__)
            _logger.exception(f"Error sending instant lead-back message: {e}")
            
            # Log error to lead timeline
            if opportunity:
                opportunity.message_post(
                    body=f"<p><strong>Instant Lead-Back Message Error</strong></p>"
                         f"<p>Error: {str(e)}</p>",
                    subject="Instant Lead-Back Message Error"
                )
            
            return {'status': 'error', 'message': str(e)}
    
    def _process_template(self, template, template_vars):
        """
        Process template with fallback syntax and conditional blocks.
        
        Supports:
        - Fallbacks: {placeholder|fallback} - uses fallback if placeholder is empty
        - Conditionals: {if field}...{/if} - shows content only if field exists and is not empty
        
        :param template: Template string with placeholders
        :param template_vars: Dictionary of variable values
        :return: Processed template string
        """
        import re
        
        # First, process conditional blocks {if field}...{/if}
        def process_conditionals(text):
            # Pattern to match {if field}...{/if}
            pattern = r'\{if\s+(\w+)\}(.*?)\{/if\}'
            
            def replace_conditional(match):
                field_name = match.group(1)
                content = match.group(2)
                # Check if field exists and is not empty
                field_value = template_vars.get(field_name, '')
                if field_value and str(field_value).strip():
                    return content
                return ''
            
            return re.sub(pattern, replace_conditional, text, flags=re.DOTALL)
        
        # Process conditionals first
        processed = process_conditionals(template)
        
        # Then process fallbacks {placeholder|fallback}
        def process_fallbacks(text):
            # Pattern to match {placeholder|fallback}
            pattern = r'\{(\w+)\|([^}]+)\}'
            
            def replace_fallback(match):
                placeholder = match.group(1)
                fallback = match.group(2)
                value = template_vars.get(placeholder, '')
                if value and str(value).strip():
                    return str(value)
                return fallback
            
            return re.sub(pattern, replace_fallback, text)
        
        processed = process_fallbacks(processed)
        
        # Finally, replace remaining placeholders
        try:
            return processed.format(**template_vars)
        except KeyError as e:
            # If placeholder doesn't exist, leave it as is
            import logging
            _logger = logging.getLogger(__name__)
            _logger.warning(f"Missing placeholder in template: {e}")
            # Replace missing placeholders with empty string
            pattern = r'\{(\w+)\}'
            return re.sub(pattern, '', processed)
    
    def _get_delay_info(self, delay_type, delay_amount):
        """Get human-readable delay information"""
        if not delay_amount or delay_amount == 0:
            return None
        if delay_type == 'minutes':
            return f"{delay_amount} minute{'s' if delay_amount != 1 else ''}"
        elif delay_type == 'hours':
            return f"{delay_amount} hour{'s' if delay_amount != 1 else ''}"
        elif delay_type == 'days':
            return f"{delay_amount} day{'s' if delay_amount != 1 else ''}"
        return None
    
    def _schedule_followup_reminders(self, opportunity, contact_name):
        """
        Schedule follow-up reminder activities for a new lead based on configured reminder templates.
        
        For day-based delays: Creates activities immediately with the correct date_deadline.
        For minute/hour delays: Stores reminders in a queue to be processed by a cron job.
        
        :param opportunity: CRM lead/opportunity record
        :param contact_name: Name of the contact
        :return: Tuple of (activities_created_immediately, reminders_queued)
        """
        self.ensure_one()
        
        import logging
        _logger = logging.getLogger(__name__)
        
        _logger.info("=" * 80)
        _logger.info(f"FOLLOW-UP REMINDER SCHEDULING - Starting")
        _logger.info(f"vCard ID: {self.id}, vCard Name: {self.name}")
        _logger.info(f"Opportunity ID: {opportunity.id}, Contact Name: {contact_name}")
        _logger.info(f"Follow-up reminders enabled: {self.followup_reminders_enabled}")
        _logger.info("=" * 80)
        
        if not self.followup_reminders_enabled:
            _logger.info("Follow-up reminders are disabled for this vCard. Skipping.")
            return (0, 0)
        
        # Get active reminders, ordered by sequence
        reminders = self.followup_reminder_ids.filtered(lambda r: r.active)
        _logger.info(f"Found {len(reminders)} active reminder template(s)")
        
        if not reminders:
            _logger.info("No active reminder templates found. Skipping.")
            return (0, 0)
        
        from datetime import datetime, timedelta, date
        
        activities_created = 0
        reminders_queued = 0
        
        # Use Odoo's timezone-aware datetime
        now_dt_str = fields.Datetime.now()
        now_dt = fields.Datetime.from_string(now_dt_str)
        now_date = fields.Date.today()
        
        _logger.info(f"Current datetime: {now_dt_str} (parsed: {now_dt})")
        _logger.info(f"Current date: {now_date}")
        
        # Track created activities for "after_previous_activity" scheduling
        previous_activity_id = None
        
        for reminder in reminders:
            try:
                _logger.info("-" * 80)
                _logger.info(f"Processing reminder template: '{reminder.name}' (ID: {reminder.id})")
                _logger.info(f"  Schedule Type: {reminder.schedule_type}")
                _logger.info(f"  Delay: {reminder.delay_amount} {reminder.delay_type}")
                _logger.info(f"  Activity Type: {reminder.activity_type_id.name if reminder.activity_type_id else 'N/A'}")
                
                # Determine the base datetime for calculation
                if reminder.schedule_type == 'after_previous_activity' and previous_activity_id:
                    # For "after_previous_activity", we need to wait for the previous activity to be completed
                    # We'll queue this reminder with a reference to the previous activity
                    # The cron will check when the previous activity is done
                    _logger.info(f"  Schedule type is 'after_previous_activity', will wait for previous activity ID {previous_activity_id}")
                    # Set scheduled_datetime to a far future date initially - will be updated when previous activity completes
                    due_datetime = now_dt + timedelta(days=365)  # Placeholder, will be recalculated
                    base_for_calculation = now_dt  # Will be updated when previous activity completes
                else:
                    # For "after_creation", use current datetime
                    base_for_calculation = now_dt
                    # Calculate the due datetime based on delay
                    if reminder.delay_type == 'minutes':
                        due_datetime = base_for_calculation + timedelta(minutes=reminder.delay_amount)
                    elif reminder.delay_type == 'hours':
                        due_datetime = base_for_calculation + timedelta(hours=reminder.delay_amount)
                    elif reminder.delay_type == 'days':
                        due_datetime = base_for_calculation + timedelta(days=reminder.delay_amount)
                    else:
                        _logger.warning(f"  Unknown delay_type '{reminder.delay_type}', defaulting to now")
                        due_datetime = base_for_calculation
                
                # Calculate the date_deadline (for the activity's deadline field)
                if reminder.delay_type == 'days':
                    date_deadline = due_datetime.date()
                elif reminder.delay_type == 'hours':
                    # For hour delays, if it's still today, set to tomorrow
                    if due_datetime.date() <= now_date:
                        date_deadline = now_date + timedelta(days=1)
                    else:
                        date_deadline = due_datetime.date()
                else:  # minutes
                    # For minute delays, if it's still today, set to tomorrow
                    if due_datetime.date() <= now_date:
                        date_deadline = now_date + timedelta(days=1)
                    else:
                        date_deadline = due_datetime.date()
                
                _logger.info(f"  Calculated due_datetime: {due_datetime}")
                _logger.info(f"  Calculated date_deadline: {date_deadline}")
                
                # Process summary with placeholders
                summary = reminder.summary or reminder.activity_type_id.name or 'Follow-up'
                original_summary = summary
                if '{contact_name}' in summary:
                    summary = summary.replace('{contact_name}', contact_name or 'Contact')
                    _logger.info(f"  Summary placeholder replaced: '{original_summary}' -> '{summary}'")
                else:
                    _logger.info(f"  Summary: '{summary}' (no placeholders to replace)")
                
                # Determine assigned user
                assigned_user = reminder.user_id
                if not assigned_user:
                    _logger.info("  No user specified in reminder template, trying to find from vCard owner email")
                    # Try to get user from vCard owner's email
                    if self.email:
                        user = self.env['res.users'].sudo().search([
                            ('login', '=', self.email)
                        ], limit=1)
                        if user:
                            assigned_user = user
                            _logger.info(f"  Found user from email '{self.email}': {assigned_user.name} (ID: {assigned_user.id})")
                        else:
                            _logger.info(f"  No user found with email '{self.email}'")
                    # Fallback to current user
                    if not assigned_user:
                        assigned_user = self.env.user
                        _logger.info(f"  Using current user as fallback: {assigned_user.name} (ID: {assigned_user.id})")
                else:
                    _logger.info(f"  Using user from reminder template: {assigned_user.name} (ID: {assigned_user.id})")
                
                # Handle scheduling based on schedule_type and delay_type
                if reminder.schedule_type == 'after_previous_activity':
                    if not previous_activity_id:
                        _logger.warning(f"  'After previous activity' type but no previous activity exists. This reminder will be skipped.")
                        continue
                    
                    # Queue for processing after previous activity completes
                    _logger.info(f"  'After previous activity' type: Queueing reminder to wait for activity ID {previous_activity_id}")
                    
                    scheduled_reminder = self.env['followup.scheduled.reminder'].sudo().create({
                        'opportunity_id': opportunity.id,
                        'contact_name': contact_name or 'Contact',
                        'reminder_template_id': reminder.id,
                        'scheduled_datetime': fields.Datetime.to_string(due_datetime),  # Placeholder, will be updated when previous activity completes
                        'date_deadline': date_deadline,  # Placeholder, will be recalculated
                        'activity_type_id': reminder.activity_type_id.id,
                        'summary': summary,
                        'note': reminder.note or '',
                        'user_id': assigned_user.id,
                        'previous_activity_id': previous_activity_id,
                    })
                    reminders_queued += 1
                    
                    _logger.info(
                        f"  ✓ Reminder queued (waiting for previous activity): Scheduled reminder ID {scheduled_reminder.id}, "
                        f"Previous activity ID: {previous_activity_id}, Assigned to: {assigned_user.name}"
                    )
                    # Don't update previous_activity_id - this reminder's activity will be created later
                    continue  # Skip to next reminder
                    
                elif reminder.delay_type == 'days':
                    # Day-based delay: create activity immediately
                    _logger.info(f"  Day-based delay: Creating activity immediately with date_deadline: {date_deadline}")
                    
                    # Create the activity using activity_schedule method
                    activity = opportunity.sudo().activity_schedule(
                        activity_type_id=reminder.activity_type_id.id,
                        summary=summary,
                        note=reminder.note or '',
                        date_deadline=date_deadline,
                        user_id=assigned_user.id,
                    )
                    activities_created += 1
                    previous_activity_id = activity.id  # Track for next reminder
                    
                    _logger.info(
                        f"  ✓ Activity created immediately: ID {activity.id}, "
                        f"Due date: {date_deadline}, Assigned to: {assigned_user.name}"
                    )
                    
                else:
                    # Minute or hour delay - queue for cron processing
                    _logger.info(f"  Minute/hour delay: Queueing reminder for scheduled processing at {due_datetime}")
                    
                    scheduled_reminder = self.env['followup.scheduled.reminder'].sudo().create({
                        'opportunity_id': opportunity.id,
                        'contact_name': contact_name or 'Contact',
                        'reminder_template_id': reminder.id,
                        'scheduled_datetime': fields.Datetime.to_string(due_datetime),
                        'date_deadline': date_deadline,
                        'activity_type_id': reminder.activity_type_id.id,
                        'summary': summary,
                        'note': reminder.note or '',
                        'user_id': assigned_user.id,
                    })
                    reminders_queued += 1
                    
                    # For "after_creation" type with minute/hour delays, we can't track the activity yet
                    # But we can update previous_activity_id when the activity is created by the cron
                    # For now, we'll track it via the scheduled_reminder's activity_id after creation
                    
                    _logger.info(
                        f"  ✓ Reminder queued: Scheduled reminder ID {scheduled_reminder.id}, "
                        f"Will be processed at {due_datetime}, Date deadline: {date_deadline}, Assigned to: {assigned_user.name}"
                    )
                
            except Exception as e:
                _logger.exception(
                    f"  ✗ ERROR scheduling follow-up reminder '{reminder.name}' (ID: {reminder.id}) "
                    f"for lead {opportunity.id}: {e}"
                )
                # Continue with other reminders even if one fails
                continue
        
        _logger.info("=" * 80)
        _logger.info(f"FOLLOW-UP REMINDER SCHEDULING - Completed")
        _logger.info(f"  Activities created immediately: {activities_created}")
        _logger.info(f"  Reminders queued for cron processing: {reminders_queued}")
        _logger.info(f"  Total reminders processed: {activities_created + reminders_queued}")
        _logger.info("=" * 80)
        
        return (activities_created, reminders_queued)
    
    def _schedule_automated_email(self, contact_name, contact_email, opportunity, template_vars):
        """
        Schedule or send automated email to new lead using Odoo's email system.
        
        :param contact_name: Name of the contact
        :param contact_email: Email address of the contact
        :param opportunity: CRM lead/opportunity record
        :param template_vars: Dictionary with template variables
        :return: dict with status and message
        """
        try:
            from datetime import datetime, timedelta
            
            # Get email template and process it with fallbacks and conditionals
            email_template = (self.leadback_email_template or 
                            "<p>Hi {contact_name|there}!</p><p>Great meeting you earlier! Here's my digital card: <a href='{vcard_url}'>{vcard_url}</a></p>")
            
            # Process template with fallbacks and conditionals
            email_body_html = self._process_template(email_template, template_vars)
            
            # Get email subject and process it
            email_subject = self.leadback_email_subject or "Great meeting you!"
            email_subject = self._process_template(email_subject, template_vars)
            
            # Calculate scheduled time
            delay_amount = self.leadback_email_delay or 0
            delay_type = self.leadback_email_delay_type or 'minutes'
            
            if delay_amount > 0:
                now = datetime.now()
                if delay_type == 'minutes':
                    scheduled_time = now + timedelta(minutes=delay_amount)
                elif delay_type == 'hours':
                    scheduled_time = now + timedelta(hours=delay_amount)
                elif delay_type == 'days':
                    scheduled_time = now + timedelta(days=delay_amount)
                else:
                    scheduled_time = now
            else:
                scheduled_time = None  # Send immediately
            
            # Prepare mail values
            mail_values = {
                'subject': email_subject,
                'body_html': email_body_html,
                'email_to': contact_email,
                'email_from': self.email or self.env.user.email or self.env['ir.config_parameter'].sudo().get_param('mail.catchall.alias', 'noreply@example.com'),
                'auto_delete': False,
            }
            
            # Schedule or send immediately
            if scheduled_time:
                # Store scheduled email for cron to process
                scheduled_email = self.env['leadback.scheduled.email'].sudo().create({
                    'partner_vcard_id': self.id,
                    'contact_name': contact_name,
                    'contact_email': contact_email,
                    'opportunity_id': opportunity.id if opportunity else False,
                    'email_subject': email_subject,
                    'email_body_html': email_body_html,
                    'scheduled_time': scheduled_time,
                    'state': 'pending'
                })
                
                import logging
                _logger = logging.getLogger(__name__)
                _logger.info(f"Email scheduled for {scheduled_time} to {contact_email} for lead {opportunity.id if opportunity else 'N/A'}")
                
                return {
                    'status': 'scheduled',
                    'message': f'Email scheduled to send in {self._get_delay_info(delay_type, delay_amount)}',
                    'scheduled_email_id': scheduled_email.id,
                    'scheduled_time': scheduled_time.isoformat() if scheduled_time else None
                }
            else:
                # Send immediately
                mail = self.env['mail.mail'].sudo().create(mail_values)
                mail.send()
                
                import logging
                _logger = logging.getLogger(__name__)
                _logger.info(f"Automated email sent immediately to {contact_email} for lead {opportunity.id if opportunity else 'N/A'}")
                
                return {
                    'status': 'success',
                    'message': f'Email sent to {contact_email}',
                    'email_id': mail.id
                }
            
        except Exception as e:
            import logging
            _logger = logging.getLogger(__name__)
            _logger.exception(f"Error scheduling automated email: {e}")
            return {'status': 'error', 'message': str(e)}
    
    def _send_whatsapp_message(self, contact_phone, message):
        """
        Send WhatsApp message using click-to-chat link or WhatsApp Business API.
        
        Note: Click-to-chat links only work if the phone number is registered on WhatsApp.
        For automated sending, integrate with WhatsApp Business API.
        """
        try:
            # Clean phone number (remove non-digits except +)
            # Also remove extension (ext, x, etc. and numbers after them)
            import re
            from urllib.parse import quote
            
            # Remove extension patterns (ext, x, etc. and following numbers/spaces)
            phone_without_ext = re.sub(r'\s*(ext|Ext|EXT|x|X|ext\.|Ext\.|EXT\.|x\.|X\.)\s*\d+.*$', '', contact_phone, flags=re.IGNORECASE)
            
            clean_phone = re.sub(r'[^\d+]', '', phone_without_ext)
            if not clean_phone.startswith('+'):
                # Assume it's a local number, add +1 for US (adjust as needed)
                clean_phone = '+1' + clean_phone
            
            # Remove + for WhatsApp URL
            phone_digits = clean_phone.replace('+', '')
            
            # Properly encode the message for URL
            encoded_message = quote(message)
            
            # Generate WhatsApp click-to-chat URL
            # WARNING: This only works if the phone number is registered on WhatsApp
            # If the number doesn't exist on WhatsApp, clicking the link will show an error
            whatsapp_url = f"https://wa.me/{phone_digits}?text={encoded_message}"
            
            # For now, we'll log the URL and return success
            # In production, integrate with WhatsApp Business API here for actual validation
            # Example with WhatsApp Business API:
            # import requests
            # api_url = "https://api.whatsapp.com/v1/messages"
            # headers = {"Authorization": f"Bearer {api_token}"}
            # payload = {"to": phone_digits, "text": message}
            # response = requests.post(api_url, json=payload, headers=headers)
            # The API will return an error if the number doesn't exist
            
            import logging
            _logger = logging.getLogger(__name__)
            _logger.info(f"WhatsApp message URL generated: {whatsapp_url}")
            _logger.warning("WhatsApp click-to-chat link may not work if phone number is not registered on WhatsApp")
            
            return {
                'status': 'success',
                'message': 'WhatsApp click-to-chat link generated (not automatically sent - requires Business API for automated sending)',
                'url': whatsapp_url,
                'warning': 'This is a click-to-chat link. It must be opened/clicked to send the message. Phone number must be registered on WhatsApp for this link to work. For automated sending, integrate with WhatsApp Business API.'
            }
            
        except Exception as e:
            import logging
            _logger = logging.getLogger(__name__)
            _logger.exception(f"Error sending WhatsApp message: {e}")
            return {'status': 'error', 'message': str(e)}
    
    def _send_viber_message(self, contact_phone, message):
        """
        Send Viber message using Viber click-to-chat link or Viber Business API.
        
        Note: Click-to-chat links only work if the phone number is registered on Viber.
        For automated sending, integrate with Viber Business API.
        """
        try:
            # Clean phone number (remove non-digits except +)
            # Also remove extension (ext, x, etc. and numbers after them)
            import re
            from urllib.parse import quote
            
            # Remove extension patterns (ext, x, etc. and following numbers/spaces)
            phone_without_ext = re.sub(r'\s*(ext|Ext|EXT|x|X|ext\.|Ext\.|EXT\.|x\.|X\.)\s*\d+.*$', '', contact_phone, flags=re.IGNORECASE)
            
            clean_phone = re.sub(r'[^\d+]', '', phone_without_ext)
            if not clean_phone.startswith('+'):
                # Assume it's a local number, add +1 for US (adjust as needed)
                clean_phone = '+1' + clean_phone
            
            # Remove + for Viber URL
            phone_digits = clean_phone.replace('+', '')
            
            # Properly encode the message for URL
            encoded_message = quote(message)
            
            # Generate Viber click-to-chat URL
            # WARNING: This only works if the phone number is registered on Viber
            # Format: viber://chat?number=PHONE&text=MESSAGE
            viber_url = f"viber://chat?number={phone_digits}&text={encoded_message}"
            
            # Alternative web-based URL (if available)
            # viber_url = f"https://chats.viber.com/{phone_digits}?text={encoded_message}"
            
            import logging
            _logger = logging.getLogger(__name__)
            _logger.info(f"Viber message URL generated: {viber_url}")
            _logger.warning("Viber click-to-chat link may not work if phone number is not registered on Viber")
            return {
                'status': 'success',
                'message': 'Viber click-to-chat link generated (not automatically sent - requires Business API for automated sending)',
                'url': viber_url,
                'warning': 'This is a click-to-chat link. It must be opened/clicked to send the message. Phone number must be registered on Viber for this link to work. For automated sending, integrate with Viber Business API.'
            }
            
        except Exception as e:
            import logging
            _logger = logging.getLogger(__name__)
            _logger.exception(f"Error sending Viber message: {e}")
            return {'status': 'error', 'message': str(e)}
    
    def _send_telegram_message(self, contact_phone, message):
        """
        Send Telegram message using Telegram click-to-chat link.
        
        Note: Phone number-based links only work if the number is registered on Telegram.
        """
        try:
            from urllib.parse import quote
            
            # Telegram uses phone number for click-to-chat links
            if not contact_phone:
                return {'status': 'error', 'message': 'Phone number is required for Telegram'}
            
            # Remove any non-digit characters except +
            clean_phone = ''.join(c for c in contact_phone if c.isdigit() or c == '+')
            if not clean_phone.startswith('+'):
                clean_phone = '+' + clean_phone
            
            encoded_message = quote(message)
            # Telegram phone link format
            telegram_url = f"https://t.me/{clean_phone}?text={encoded_message}"
            
            import logging
            _logger = logging.getLogger(__name__)
            _logger.info(f"Telegram message URL generated: {telegram_url}")
            
            return {
                'status': 'success',
                'message': 'Telegram click-to-chat link generated (not automatically sent - requires Bot API for automated sending)',
                'url': telegram_url,
                'method': 'phone',
                'warning': 'This is a click-to-chat link. It must be opened/clicked to send the message. For automated sending, integrate with Telegram Bot API.'
            }
            
        except Exception as e:
            import logging
            _logger = logging.getLogger(__name__)
            _logger.exception(f"Error sending Telegram message: {e}")
            return {'status': 'error', 'message': str(e)}

    @api.onchange('leadback_email_template_preset')
    def _onchange_email_template_preset(self):
        """Automatically populate email subject and template based on preset"""
        if self.leadback_email_template_preset == 'friendly':
            self.leadback_email_subject = "Great connecting with you"
            self.leadback_email_template = """<p>Hi {contact_name},</p>
<p>Thanks again for sharing your contact details. Just wanted to let you know I received your message.</p>
{if booking_url}<p>If you'd like to continue our conversation or set up some time, you can book a slot here:</p>
<p><a href='{booking_url}'>{booking_url}</a></p>{/if}
<p>Talk soon,<br/>{owner_name}</p>"""
        elif self.leadback_email_template_preset == 'professional':
            self.leadback_email_subject = "Good speaking with you"
            self.leadback_email_template = """<p>Hi {contact_name},</p>
<p>It was great connecting — I got your details.</p>
{if booking_url}<p>If you'd like to pick up the conversation, here's my booking link:</p>
<p><a href='{booking_url}'>{booking_url}</a></p>{/if}
<p>Best regards,<br/>{owner_name}{if owner_title}<br/>{owner_title}{/if}{if company_name}<br/>{company_name}{/if}</p>"""
        elif self.leadback_email_template_preset == 'event':
            self.leadback_email_subject = "Thanks for connecting"
            self.leadback_email_template = """<p>Hi {contact_name},</p>
<p>Thanks for sharing your details — I received your message.</p>
{if booking_url}<p>If you'd like to continue the conversation or set up a time, here's my booking link:</p>
<p><a href='{booking_url}'>{booking_url}</a></p>{/if}
<p>If you ever want to save my contact card again, here's the link:</p>
<p><a href='{vcard_url}'>{vcard_url}</a></p>
<p>Best,<br/>{owner_name}</p>"""
        elif self.leadback_email_template_preset == 'follow_up':
            self.leadback_email_subject = "Follow-up from earlier"
            self.leadback_email_template = """<p>Hi {contact_name},</p>
<p>Just following up — I received your contact information.</p>
{if booking_url}<p>If you'd like to book a call or ask anything, you can pick a time here:</p>
<p><a href='{booking_url}'>{booking_url}</a></p>{/if}
<p>Best,<br/>{owner_name}{if company_name}<br/>{company_name}{/if}</p>"""
        elif self.leadback_email_template_preset == 'appointment':
            self.leadback_email_subject = "Let's schedule a time to connect"
            self.leadback_email_template = """<p>Hi {contact_name},</p>
<p>Thanks for sharing your details — I got your message.</p>
{if booking_url}<p>I'd love to schedule some time to chat further. Please book a time that works for you:</p>
<p><a href='{booking_url}'>{booking_url}</a></p>{/if}
<p>Talk soon,<br/>{owner_name}</p>"""
        # For 'custom', leave the fields as they are so user can edit
    
    @api.onchange('leadback_message_template_preset')
    def _onchange_message_template_preset(self):
        """Automatically populate message template based on preset"""
        if self.leadback_message_template_preset == 'friendly':
            self.leadback_message_template = """Hi {contact_name}! Thanks for sharing your details — I got your message.

{if booking_url}If you'd like to continue the conversation or set up a time, here's my booking link:
{booking_url}{/if}"""
        elif self.leadback_message_template_preset == 'event':
            self.leadback_message_template = """Hi {contact_name}! Thanks for sharing your details — I got your message.

If you'd like to save my info again later, here's my card: {vcard_url}

{if booking_url}Booking link: {booking_url}{/if}"""
        elif self.leadback_message_template_preset == 'professional':
            self.leadback_message_template = """Hi {contact_name}! Just confirming I received your info.

{if booking_url}Here's my booking link if you want to chat:
{booking_url}{/if}"""
        elif self.leadback_message_template_preset == 'follow_up':
            self.leadback_message_template = """Hi {contact_name}, got your info — thank you!

{if booking_url}Book a time here: {booking_url}{/if}"""
        # For 'custom', leave the field as it is so user can edit
    
    @api.onchange('leadback_email_delay_preset')
    def _onchange_email_delay_preset(self):
        """Automatically set email delay amount and type based on preset"""
        if self.leadback_email_delay_preset == 'immediate':
            self.leadback_email_delay = 0
            self.leadback_email_delay_type = 'minutes'
        elif self.leadback_email_delay_preset == '1_min':
            self.leadback_email_delay = 1
            self.leadback_email_delay_type = 'minutes'
        elif self.leadback_email_delay_preset == '5_min':
            self.leadback_email_delay = 5
            self.leadback_email_delay_type = 'minutes'
        elif self.leadback_email_delay_preset == '15_min':
            self.leadback_email_delay = 15
            self.leadback_email_delay_type = 'minutes'
        elif self.leadback_email_delay_preset == '1_hour':
            self.leadback_email_delay = 1
            self.leadback_email_delay_type = 'hours'
        # For 'custom', leave the fields as they are so user can edit
    
    @api.onchange('leadback_message_delay_preset')
    def _onchange_message_delay_preset(self):
        """Automatically set message delay amount and type based on preset"""
        if self.leadback_message_delay_preset == 'immediate':
            self.leadback_message_delay = 0
            self.leadback_message_delay_type = 'minutes'
        elif self.leadback_message_delay_preset == '1_min':
            self.leadback_message_delay = 1
            self.leadback_message_delay_type = 'minutes'
        elif self.leadback_message_delay_preset == '5_min':
            self.leadback_message_delay = 5
            self.leadback_message_delay_type = 'minutes'
        elif self.leadback_message_delay_preset == '15_min':
            self.leadback_message_delay = 15
            self.leadback_message_delay_type = 'minutes'
        elif self.leadback_message_delay_preset == '1_hour':
            self.leadback_message_delay = 1
            self.leadback_message_delay_type = 'hours'
        # For 'custom', leave the fields as they are so user can edit
    
    @api.onchange('qr_pattern')
    def _onchange_qr_pattern(self):
        """Regenerate the QR code image when the pattern changes."""
        if self.qr_code_data:
            self._generate_qr_code_image()

    def _generate_qr_code_data(self):
        """Generate and store QR code data based on the partner's information."""
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        redirect_url = f"{base_url}/qr/{self.id}"
        self.qr_code_data = redirect_url
    
    def action_regenerate_qr_code(self):
        """Regenerate QR code using the same logic as signup."""
        self.ensure_one()
        # Regenerate QR code data (ensures URL is correct)
        self._generate_qr_code_data()
        # Regenerate QR code image with current pattern and logo
        self._generate_qr_code_image()
        # Reload the form to show the updated QR code image
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'partner.vcard',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'current',
            'context': {'form_view_initial_mode': 'edit'},
        }
    
    def _generate_qr_code_image(self):
        """Generate QR code image based on stored data and current pattern."""
        if not self.qr_code_data:
            return
    
        # Generate QR code image using stored data
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_H,
            box_size=10,
            border=4,
        )
        qr.add_data(self.qr_code_data)
        qr.make(fit=True)
    
        # Select the appropriate pattern for the QR code
        module_drawer = {
            'dots': CircleModuleDrawer(),
            'rounded': RoundedModuleDrawer(),
            'classy-rounded': GappedSquareModuleDrawer(),
            'classy': GappedSquareModuleDrawer(),
            'square': SquareModuleDrawer()
        }.get(self.qr_pattern, SquareModuleDrawer())
    
        # Generate the QR code with the selected pattern
        img = qr.make_image(
            image_factory=StyledPilImage,
            module_drawer=module_drawer,
            fill_color='black',
            back_color='white',
        )
    
        # Overlay the logo if it exists
        if self.qr_logo:
            img = self._add_logo_to_qr_code(img)
    
        # Save QR code image
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        image_data = base64.b64encode(buffer.getvalue())
        self.qr_code = image_data

    def _add_logo_to_qr_code(self, img):
        """Overlay the provided logo on the QR code."""
        try:
            logo_data = base64.b64decode(self.qr_logo)
            logo = Image.open(io.BytesIO(logo_data))
            
            # Convert logo to RGBA if it's not already
            if logo.mode != 'RGBA':
                logo = logo.convert('RGBA')
        
            # Resize the logo based on the QR code size
            logo_size = min(img.size) // 3
            logo.thumbnail((logo_size, logo_size), Image.Resampling.LANCZOS)
        
            qr_width, qr_height = img.size
            logo_width, logo_height = logo.size
        
            # Center the logo
            logo_position = (
                (qr_width - logo_width) // 2,
                (qr_height - logo_height) // 2
            )
            
            # Paste the logo with transparency
            img.paste(logo, logo_position, logo)
            return img
        except Exception as e:
            # If logo processing fails, return the original QR code without logo
            import logging
            _logger = logging.getLogger(__name__)
            _logger.warning(f"Failed to add logo to QR code: {e}")
            return img

    @api.depends(
        'whatsapp_url', 'linkedin_url', 'youtube_url', 'facebook_url', 'telegram_url',
        'instagram_url', 'tumblr_url', 'xing_url', 'github_url', 'vimeo_url',
        'messenger_url', 'dribbble_url', 'skype_url', 'doordash_url', 'tripadvisor_url',
        'yelp_url', 'twitter_url', 'google_reviews_url', 'ubereats_url', 'line_url',
        'vkontakte_url', 'reddit_url', 'viber_url', 'pinterest_url', 'tiktok_url',
        'snapchat_url', 'signal_url'
    )
    def _compute_social_media_urls(self):
        """Automatically format the social media URLs if the user enters a slug."""
        url_patterns = {
            'whatsapp_url': ('https://wa.me/', r'^\d+$'),
            'linkedin_url': ('https://www.linkedin.com/in/', r'^[a-zA-Z0-9_-]+$'),
            'linkedin_url_company': ('https://www.linkedin.com/company/', r'^[a-zA-Z0-9_-]+$'),
            'youtube_url': ('https://www.youtube.com/channel/', r'^[a-zA-Z0-9_-]+$'),
            'facebook_url': ('https://www.facebook.com/', r'^[a-zA-Z0-9._-]+$'),
            'facebook_url_company': ('https://www.facebook.com/', r'^[a-zA-Z0-9._-]+$'),
            'telegram_url': ('https://t.me/', r'^[a-zA-Z0-9_-]+$'),
            'instagram_url': ('https://www.instagram.com/', r'^[a-zA-Z0-9._-]+$'),
            'instagram_url_company': ('https://www.instagram.com/', r'^[a-zA-Z0-9._-]+$'),
            'tumblr_url': ('https://', r'^[a-zA-Z0-9_-]+\.tumblr\.com$'),
            'xing_url': ('https://www.xing.com/profile/', r'^[a-zA-Z0-9_-]+$'),
            'github_url': ('https://github.com/', r'^[a-zA-Z0-9_-]+$'),
            'vimeo_url': ('https://vimeo.com/', r'^[a-zA-Z0-9_-]+$'),
            'messenger_url': ('https://m.me/', r'^[a-zA-Z0-9._-]+$'),
            'dribbble_url': ('https://dribbble.com/', r'^[a-zA-Z0-9_-]+$'),
            'skype_url': ('skype:', r'^[a-zA-Z0-9._-]+$'),
            'doordash_url': ('https://www.doordash.com/store/', r'^[a-zA-Z0-9._-]+$'),
            'tripadvisor_url': ('https://www.tripadvisor.com/Profile/', r'^[a-zA-Z0-9._-]+$'),
            'yelp_url': ('https://www.yelp.com/biz/', r'^[a-zA-Z0-9._-]+$'),
            'twitter_url': ('https://www.twitter.com/', r'^[a-zA-Z0-9._-]+$'),
            'twitter_url_company': ('https://www.twitter.com/', r'^[a-zA-Z0-9._-]+$'),
            'google_reviews_url': ('https://g.page/', r'^[a-zA-Z0-9._-]+$'),
            'ubereats_url': ('https://www.ubereats.com/store/', r'^[a-zA-Z0-9._-]+$'),
            'line_url': ('https://line.me/R/ti/p/', r'^[a-zA-Z0-9._-]+$'),
            'vkontakte_url': ('https://vk.com/', r'^[a-zA-Z0-9._-]+$'),
            'reddit_url': ('https://www.reddit.com/user/', r'^[a-zA-Z0-9._-]+$'),
            'viber_url': ('viber://chat?number=', r'^[0-9]+$'),
            'pinterest_url': ('https://www.pinterest.com/', r'^[a-zA-Z0-9._-]+$'),
            'tiktok_url': ('https://www.tiktok.com/@', r'^[a-zA-Z0-9._-]+$'),
            'snapchat_url': ('https://www.snapchat.com/add/', r'^[a-zA-Z0-9._-]+$'),
            'signal_url': ('https://signal.me/#p/', r'^[0-9]+$')
        }

        for field_name, (prefix, slug_pattern) in url_patterns.items():
            field_value = getattr(self, field_name)
            if field_value:
                # Check if the user entered a full URL
                if field_value.startswith('http') or field_value.startswith('https'):
                    continue
                elif re.match(slug_pattern, field_value):
                    # If it's a valid slug, append the correct prefix
                    setattr(self, field_name, prefix + field_value)

    @api.depends('website_slug')
    def _compute_website_full_url(self):
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        for record in self:
            if record.website_slug:
                record.website_full_url = base_url + "/" + record.website_slug
            else:
                record.website_full_url = base_url

    def _generate_vcf(self):
        """Generate vCard (.vcf) file for the partner."""
        vcard = (
            f"BEGIN:VCARD\n"
            f"VERSION:3.0\n"
            f"FN:{self.name}\n"
            f"ORG:{self.company_name or ''}\n"
            f"TITLE:{self.function or ''}\n"
            f"TEL;TYPE=CELL:{self.phone or ''}\n"
            f"TEL;TYPE=WORK,VOICE:{self.mobile or ''}\n"
            f"EMAIL:{self.email or ''}\n"
            f"ADR;TYPE=WORK,PREF:;;{self.street or ''};{self.city or ''};{self.state_id.name or ''};{self.zip or ''};{self.country_id.name or ''}\n"
            f"END:VCARD"
        )
        return vcard

    @api.onchange('website_slug', 'primary_color', 'secondary_color')
    def _onchange_website_slug(self):
        self._compute_website_full_url()

    @api.depends('image_url')
    def _update_attachment_if_image_changed(self):
        """Create or update the attachment when image_url is changed."""
        for record in self:
            if record.image_url:
                # Step 1: Check if an attachment already exists; if not, create it
                if not record.attachment_id:
                    # Create a new attachment for the uploaded image
                    new_attachment = self.env['ir.attachment'].create({
                        'name': f"Partner Image {record.name}",
                        'type': 'binary',
                        'datas': record.image_url,
                        'res_model': 'partner.vcard',
                        'res_id': record.id,
                        'public': True,  # Make it accessible to the public
                        'mimetype': 'image/png',  # Adjust based on the actual image type
                    })
                    # Link the newly created attachment to the record
                    record.attachment_id = new_attachment
                else:
                    # Step 2: Update the existing attachment (if an image already exists)
                    record.attachment_id.write({
                        'datas': record.image_url,
                        'name': f"Partner Image {record.name}",
                        'mimetype': 'image/png',  # Adjust MIME type if needed
                    })
    
    @api.onchange('image_url')
    def _onchange_image_url(self):
        """Trigger update when image_url changes and regenerate the website page."""
        # Call the function to handle attachment creation/update
        self._update_attachment_if_image_changed()
        # Optionally regenerate the website page if the slug is set
        if self.website_slug:
            self.action_generate_website_page()

    @api.depends('banner_image')
    def _update_banner_attachment_if_image_changed(self):
        """Create or update the attachment when banner_image is changed."""
        for record in self:
            if record.banner_image:
                # Step 1: Check if an attachment already exists; if not, create it
                if not record.banner_attachment_id:
                    # Create a new attachment for the uploaded banner image
                    new_attachment = self.env['ir.attachment'].create({
                        'name': f"Partner Banner Image {record.name}",
                        'type': 'binary',
                        'datas': record.banner_image,
                        'res_model': 'partner.vcard',
                        'res_id': record.id,
                        'public': True,  # Make it accessible to the public
                        'mimetype': 'image/png',  # Adjust based on the actual image type
                    })
                    # Link the newly created attachment to the record
                    record.banner_attachment_id = new_attachment
                else:
                    # Step 2: Update the existing attachment (if an image already exists)
                    record.banner_attachment_id.write({
                        'datas': record.banner_image,
                        'name': f"Partner Banner Image {record.name}",
                        'mimetype': 'image/png',  # Adjust MIME type if needed
                    })
            else:
                # Step 3: If banner_image is removed, clear the attachment reference
                if record.banner_attachment_id:
                    # Optionally delete the old attachment to clean up
                    old_attachment = record.banner_attachment_id
                    record.banner_attachment_id = False
                    try:
                        old_attachment.unlink()
                    except Exception:
                        # If deletion fails, just continue - the reference is already cleared
                        pass
    
    @api.onchange('banner_image')
    def _onchange_banner_image(self):
        """Trigger update when banner_image changes and regenerate the website page."""
        # Call the function to handle attachment creation/update
        self._update_banner_attachment_if_image_changed()
        # Optionally regenerate the website page if the slug is set
        if self.website_slug:
            self.action_generate_website_page()

    def action_generate_website_page(self):
        """Generate or update the website page dynamically when the button is clicked."""
        from odoo.exceptions import UserError
        
        try:
            for record in self:
                _logger.info(f"=== Generating website for {record.name} with template: {record.website_template} ===")
                
                # Step 1: Ensure that the image is attached and publicly accessible
                record._update_attachment_if_image_changed()
                record._update_banner_attachment_if_image_changed()
        
                # Step 2: Get the public URL for the attachment
                image_url = f'/website/image/ir.attachment/{record.attachment_id.id}/datas' if record.attachment_id else None
                banner_url = f'/website/image/ir.attachment/{record.banner_attachment_id.id}/datas' if record.banner_attachment_id else None
        
                # Step 3: Build the dynamic template, including color settings
                template = record._build_dynamic_template(image_url, banner_url)
                
                _logger.info(f"Generated template for {record.website_slug}, template type: {record.website_template}")
        
                # Check if a view already exists for this slug
                existing_view = self.env['ir.ui.view'].search([('key', '=', f'website.{record.website_slug}')], limit=1)
        
                if existing_view:
                    # Update the existing view with the dynamic template
                    _logger.info(f"Updating existing view for {record.website_slug}")
                    existing_view.write({
                        'arch_db': template,
                    })
                    # Clear all caches to ensure changes take effect
                    self.env['ir.ui.view'].clear_caches()
                    self.env['ir.qweb'].clear_caches()
                    view_id = existing_view.id
                    _logger.info(f"View updated successfully, ID: {view_id}")
                else:
                    # Create a new view with the dynamic template
                    new_view = self.env['ir.ui.view'].create({
                        'name': record.website_slug,
                        'type': 'qweb',
                        'key': f'website.{record.website_slug}',
                        'arch_db': template,  # Use the generated template
                        'website_id': self.env['website'].get_current_website().id,
                    })
                    view_id = new_view.id
        
                # Check if a website page exists for the slug, if not, create it
                existing_page = self.env['website.page'].search([('url', '=', f'/{record.website_slug}')], limit=1)
                if existing_page:
                    # Update the existing page
                    existing_page.write({
                        'name': record.website_slug,
                        'view_id': view_id,
                        'is_published': True,
                    })
                    record.website_page_id = existing_page.id  # Assign existing page ID to the partner
                else:
                    # Create the corresponding website.page entry and mark it as published
                    new_page = self.env['website.page'].create({
                        'name': record.website_slug,
                        'url': f"/{record.website_slug}",
                        'view_id': view_id,
                        'website_id': self.env['website'].get_current_website().id,
                        'is_published': True
                    })
                    # Store the created website page reference
                    record.website_page_id = new_page.id  # Assign new page ID to the partner
                
                _logger.info(f"=== Website generation complete for {record.name} ===")
            
            _logger.info("========== WEBSITE GENERATION FINISHED SUCCESSFULLY ==========")
            
            # Return a notification to the user
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Website Generated!',
                    'message': f'Your vCard website has been generated with the {self.website_template} template.',
                    'type': 'success',
                    'sticky': True,
                }
            }
        except Exception as e:
            _logger.error(f"========== ERROR GENERATING WEBSITE: {str(e)} ==========", exc_info=True)
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Error',
                    'message': f'Failed to generate website: {str(e)}',
                    'type': 'danger',
                    'sticky': True,
                }
            }


    def _get_lead_tag_ids_str(self):
        """Get comma-separated string of lead tag IDs for use in templates"""
        if not self.lead_tag_ids:
            return ''
        return ','.join(str(tag_id) for tag_id in self.lead_tag_ids.ids)
    
    def _get_google_maps_url(self):
        """Build Google Maps URL for the address"""
        if not any([self.street, self.city, self.state_id, self.country_id]):
            return None
        
        # Build address string
        address_parts = []
        if self.street:
            address_parts.append(self.street)
        if self.street2:
            address_parts.append(self.street2)
        if self.city:
            address_parts.append(self.city)
        if self.state_id and self.state_id.name:
            address_parts.append(self.state_id.name)
        if self.zip:
            address_parts.append(self.zip)
        if self.country_id and self.country_id.name:
            address_parts.append(self.country_id.name)
        
        if not address_parts:
            return None
        
        # Join address parts and URL encode
        import urllib.parse
        address = ', '.join(address_parts)
        encoded_address = urllib.parse.quote_plus(address)
        return f"https://www.google.com/maps/search/?api=1&query={encoded_address}"
    
    def _get_page_view_tracking_script(self):
        """Get JavaScript code to track page views"""
        if not self.website_slug:
            return ""
        slug_escaped = self.website_slug.replace("'", "\\'")
        return f"""
        <script>
        (function() {{
            // Track page view when page loads
            function trackPageView() {{
                // Only track once per page load
                var storageKey = 'vcard_view_tracked_{slug_escaped}';
                if (sessionStorage.getItem(storageKey)) {{
                    return;
                }}
                
                // Track the view
                var xhr = new XMLHttpRequest();
                xhr.open('POST', '/track_page_view/{slug_escaped}', true);
                xhr.setRequestHeader('Content-Type', 'application/json');
                xhr.onreadystatechange = function() {{
                    if (xhr.readyState === 4) {{
                        if (xhr.status === 200) {{
                            try {{
                                var response = JSON.parse(xhr.responseText);
                                if (response.success) {{
                                    console.log('Page view tracked successfully. Total views:', response.views);
                                }}
                            }} catch(e) {{
                                console.log('Page view tracking response parse error:', e);
                            }}
                        }} else {{
                            console.log('Page view tracking failed with status:', xhr.status);
                        }}
                        // Mark as tracked for this session regardless of success
                        sessionStorage.setItem(storageKey, 'true');
                    }}
                }};
                xhr.send(JSON.stringify({{}}));
            }}
            
            // Track when page is ready
            if (document.readyState === 'loading') {{
                document.addEventListener('DOMContentLoaded', trackPageView);
            }} else {{
                trackPageView();
            }}
        }})();
        </script>
        """
    
    def _build_dynamic_template(self, image_url, banner_url=None):
        """Build the dynamic website template based on selected template."""
        # CRITICAL: Compute referral URL at build time and ensure it has ref ID
        # This URL will be hardcoded in the template, so it's set once and never changes
        import logging
        _logger = logging.getLogger(__name__)
        
        _logger.info("=" * 80)
        _logger.info(f"TEMPLATE GENERATION: Building template for vCard {self.id} ({self.name})")
        _logger.info(f"  Template type: {self.website_template}")
        _logger.info(f"  Website slug: {self.website_slug}")
        referral_url = '/get-started'
        
        
        _logger.info(f"  Step 3: Building {self.website_template} template with hardcoded referral URL...")
        
        # Call the appropriate template building method based on selection
        # Pass referral_url to each template builder so it's embedded directly in the template
        if self.website_template == 'modern':
            template = self._build_modern_template(image_url, banner_url, referral_url)
        elif self.website_template == 'minimal':
            template = self._build_minimal_template(image_url, banner_url, referral_url)
        elif self.website_template == 'corporate':
            template = self._build_corporate_template(image_url, banner_url, referral_url)
        elif self.website_template == 'creative':
            template = self._build_creative_template(image_url, banner_url, referral_url)
        else:  # classic or default
            template = self._build_classic_template(image_url, banner_url, referral_url)
        
        # Verify the URL is in the template
        if referral_url in template:
            _logger.info(f"  ✓✓✓ VERIFIED: Referral URL '{referral_url}' is embedded in the template")
            _logger.info(f"  ✓ Footer link will use: {referral_url}")
        else:
            _logger.error(f"  ✗✗✗ ERROR: Referral URL '{referral_url}' NOT FOUND in generated template!")
            _logger.error(f"  ✗ Template may be using fallback URL")
        
        _logger.info("=" * 80)
        
        # Inject page view tracking script before closing template tag
        tracking_script = self._get_page_view_tracking_script()
        if tracking_script:
            # Insert script before the last closing </t> tag (the outer one)
            # Find the last occurrence of </t> which is the closing tag for the template
            last_closing_tag = template.rfind('</t>')
            if last_closing_tag != -1:
                template = template[:last_closing_tag] + tracking_script + '\n        ' + template[last_closing_tag:]
        
        return template
    
    def _build_classic_template(self, image_url, banner_url=None, referral_url=None):
        """Build the classic vCard template (original design)."""
        if referral_url is None:
            referral_url = self.get_referral_signup_url()
        
        google_maps_url = self._get_google_maps_url()
        google_maps_button = ''
        if google_maps_url:
            google_maps_button = f'<a href="{google_maps_url}" target="_blank" class="btn btn-sm btn-outline-light ms-2" style="padding: 2px 8px; font-size: 0.75rem; margin-top: 4px; display: inline-block;"><i class="fa fa-map me-1"></i>Directions</a>'
        
        address_display = ''
        if self.street or self.city:
            address_parts = []
            if self.street:
                address_parts.append(self.street)
            if self.city:
                address_parts.append(self.city)
            if self.state_id and self.state_id.name:
                address_parts.append(self.state_id.name)
            if self.zip:
                address_parts.append(f' {self.zip}')
            if self.country_id and self.country_id.name:
                address_parts.append(self.country_id.name)
            address_display = ', '.join(address_parts)
        
        address_html = ''
        if address_display:
            address_html = f'''<p class="text-white mb-2"><i class="fa fa-map-marker me-2"></i>{address_display}{google_maps_button}</p>'''
        
        return f"""
        <t t-name="website.{self.website_slug}">
            <t t-set="partner" t-value="request.env['partner.vcard'].sudo().browse({self.id})"/>
            <t t-call="website.layout">
                <div class="container mt-5 mb-5">
                    <div class="row justify-content-center">
                        <div class="col-md-8 col-lg-6">
                            <div class="card shadow-lg border-0" style="background: linear-gradient(135deg, {self.primary_color} 0%, {self.secondary_color} 100%);">
                                <div class="card-body text-center p-5">
                                    <!-- Profile Image -->
                                    <div class="mb-4">
                                        <img t-att-src="'{image_url}'" alt="Profile Image" class="rounded-circle" style="width: 150px; height: 150px; object-fit: cover; border: 5px solid white;"/>
                                    </div>
                                    
                                    <!-- Name and Title -->
                                    <h1 class="text-white mb-2">{self.name or ''}</h1>
                                    <h4 class="text-white-50 mb-3">{self.function or ''}</h4>
                                    <h5 class="text-white mb-4">{self.company_name or ''}</h5>
                                    
                                    <!-- Contact Info -->
                                    <div class="mb-4">
                                        <t t-if="partner.email">
                                            <p class="text-white mb-2"><i class="fa fa-envelope me-2"></i><t t-esc="partner.email"/></p>
                                        </t>
                                        <t t-if="partner.phone">
                                            <p class="text-white mb-2"><i class="fa fa-phone me-2"></i><t t-esc="partner.phone"/></p>
                                        </t>
                                        <t t-if="partner.mobile">
                                            <p class="text-white mb-2"><i class="fa fa-mobile me-2"></i><t t-esc="partner.mobile"/></p>
                                        </t>
                                        {address_html}
                                    </div>
                                    
                                    <!-- QR Code -->
                                        <div class="mb-4">
                                        <img t-att-src="'/vcard/qr_code/download/' + str(partner.id)" alt="QR Code" class="rounded" style="width: 150px; height: 150px; background: white; padding: 10px;"/>
                                        </div>
                                    
                                    <!-- vCard Download -->
                                    <div class="mb-4">
                                        <a t-att-href="'/website/vcard/download/' + str(partner.id)" class="btn btn-outline-light btn-lg">
                                            <i class="fa fa-download me-2"></i>Download vCard
                                        </a>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                    
                    <!-- Vinculum Footer Banner -->
                    <div style="background: rgba(255,255,255,0.95); border-top: 1px solid rgba(0,0,0,0.1); padding: 20px 0; text-align: center;">
                        <a href="{referral_url}" target="_blank" style="display: inline-block; color: #6c757d; text-decoration: none; font-size: 0.9rem; font-weight: 500; transition: all 0.3s ease; padding: 8px 16px; border-radius: 20px;">
                            Built with <strong style="color: #4c89c8;">Vinculum</strong> <span style="display: inline-block; transition: transform 0.3s ease; margin: 0 4px;">→</span> Create yours for <strong style="color: #4c89c8;">FREE</strong>
                        </a>
                    </div>
                </div>
            </t>
        </t>
        """
    
    def _build_modern_template(self, image_url, banner_url=None, referral_url=None):
        """Build the modern vCard template."""
        if referral_url is None:
            referral_url = self.get_referral_signup_url()
        
        google_maps_url = self._get_google_maps_url()
        google_maps_button = ''
        if google_maps_url:
            google_maps_button = f'<a href="{google_maps_url}" target="_blank" class="btn btn-sm btn-outline-light ms-2" style="padding: 2px 8px; font-size: 0.75rem;"><i class="fas fa-map me-1"></i>Directions</a>'
        
        address_display = ''
        if self.street or self.city:
            address_parts = []
            if self.street:
                address_parts.append(self.street)
            if self.city:
                address_parts.append(self.city)
            if self.state_id and self.state_id.name:
                address_parts.append(self.state_id.name)
            if self.zip:
                address_parts.append(f' {self.zip}')
            if self.country_id and self.country_id.name:
                address_parts.append(self.country_id.name)
            address_display = ', '.join(address_parts)
        
        address_html = ''
        if address_display:
            address_html = f'''<p class="mb-2"><i class="fas fa-map-marker-alt me-2"></i><span class="text-white">{address_display}</span>{google_maps_button}</p>'''
        
        return f"""
        <t t-name="website.{self.website_slug}">
            <t t-set="partner" t-value="request.env['partner.vcard'].sudo().browse({self.id})"/>
            <t t-call="website.layout">
                <div class="modern-vcard-container" style="background: linear-gradient(135deg, {self.primary_color} 0%, {self.secondary_color} 100%); min-height: 100vh;">
                    <div class="container py-5">
                        <div class="row align-items-center" style="min-height: 80vh;">
                            <div class="col-lg-6 text-white">
                                <div class="mb-4 text-center text-lg-start">
                                    <img t-att-src="'{image_url}'" class="rounded-circle mb-4" alt="Profile" style="width: 200px; height: 200px; object-fit: cover; border: 5px solid rgba(255,255,255,0.3);"/>
                                </div>
                                <h1 class="display-4 fw-bold mb-3">{self.name or ''}</h1>
                                <h2 class="h4 mb-3">{self.company_name or ''}</h2>
                                <p class="lead mb-4">{self.function or ''}</p>
                                <div class="contact-info">
                                    <t t-if="partner.email">
                                        <p class="mb-2"><i class="fas fa-envelope me-2"></i><a t-att-href="'mailto:' + partner.email" class="text-white text-decoration-none" t-esc="partner.email"/></p>
                                    </t>
                                    <t t-if="partner.phone">
                                        <p class="mb-2"><i class="fas fa-phone me-2"></i><a t-att-href="'tel:' + partner.phone" class="text-white text-decoration-none" t-esc="partner.phone"/></p>
                                    </t>
                                    {address_html}
                                </div>
                            </div>
                            <div class="col-lg-6 text-center mt-5 mt-lg-0">
                                <div class="qr-container">
                                    <img t-att-src="'/vcard/qr_code/download/' + str(partner.id)" class="qr-code" alt="QR Code" style="width: 250px; height: 250px; border-radius: 20px; background: white; padding: 20px; box-shadow: 0 10px 30px rgba(0,0,0,0.3);"/>
                                    <p class="mt-3 text-white">Scan to connect</p>
                                </div>
                                <div class="mt-4">
                                    <a t-att-href="'/website/vcard/download/' + str(partner.id)" class="btn btn-light btn-lg">
                                        <i class="fa fa-download me-2"></i>Download vCard
                                    </a>
                                </div>
                            </div>
                        </div>
                    </div>
                    
                    <!-- Vinculum Footer Banner -->
                    <div style="padding: 20px 0; background: ' + (partner.primary_color or '#ffffff') + '; border-top: 1px solid #e9ecef; text-align: center;">
                        <a href="{referral_url}" target="_blank" style="display: inline-block; color: #6c757d; text-decoration: none; font-size: 0.9rem; font-weight: 500; transition: all 0.3s ease; padding: 8px 16px; border-radius: 20px;">
                            Built with Vinculum <span style="display: inline-block; transition: transform 0.3s ease; margin: 0 4px;">→</span> Create yours
                        </a>
                    </div>
                </div>
            </t>
        </t>
        """
    
    def _build_minimal_template(self, image_url, banner_url=None, referral_url=None):
        """Build the minimal vCard template."""
        if referral_url is None:
            referral_url = self.get_referral_signup_url()
        
        google_maps_url = self._get_google_maps_url()
        google_maps_button = ''
        if google_maps_url:
            google_maps_button = f'<a href="{google_maps_url}" target="_blank" class="btn btn-sm btn-outline-dark ms-2" style="padding: 2px 8px; font-size: 0.75rem; margin-top: 4px; display: inline-block;"><i class="fas fa-map me-1"></i>Directions</a>'
        
        address_display = ''
        if self.street or self.city:
            address_parts = []
            if self.street:
                address_parts.append(self.street)
            if self.city:
                address_parts.append(self.city)
            if self.state_id and self.state_id.name:
                address_parts.append(self.state_id.name)
            if self.zip:
                address_parts.append(f' {self.zip}')
            if self.country_id and self.country_id.name:
                address_parts.append(self.country_id.name)
            address_display = ', '.join(address_parts)
        
        address_html = ''
        if address_display:
            address_html = f'''<p class="mb-2"><i class="fas fa-map-marker-alt me-2"></i><span>{address_display}</span>{google_maps_button}</p>'''
        
        return f"""
        <t t-name="website.{self.website_slug}">
            <t t-set="partner" t-value="request.env['partner.vcard'].sudo().browse({self.id})"/>
            <t t-call="website.layout">
                <div class="minimal-vcard-container" t-att-style="'min-height: 100vh; padding: 50px 0; background: ' + (partner.primary_color or '#ffffff') + ';'">
                    <div class="container">
                        <div class="row justify-content-center">
                            <div class="col-lg-6 text-center">
                                <img t-att-src="'{image_url}'" class="mb-4" alt="Profile" style="width: 150px; height: 150px; border-radius: 50%; object-fit: cover; border: 3px solid #e9ecef;"/>
                                <h1 class="display-5 fw-bold mb-2">{self.name or ''}</h1>
                                <h2 class="h5 text-muted mb-4">{self.company_name or ''}</h2>
                                <p class="lead mb-4">{self.function or ''}</p>
                                
                                <div class="contact-info mb-4">
                                    <t t-if="partner.email">
                                        <p class="mb-2"><i class="fas fa-envelope me-2"></i><a t-att-href="'mailto:' + partner.email" class="text-decoration-none" t-esc="partner.email"/></p>
                                    </t>
                                    <t t-if="partner.phone">
                                        <p class="mb-2"><i class="fas fa-phone me-2"></i><a t-att-href="'tel:' + partner.phone" class="text-decoration-none" t-esc="partner.phone"/></p>
                                    </t>
                                    {address_html}
                                </div>
                                        
                                <div class="qr-code-section mb-5">
                                    <img t-att-src="'/vcard/qr_code/download/' + str(partner.id)" alt="QR Code" style="width: 200px; height: 200px; border-radius: 10px;"/>
                                    </div>
                                    
                                <div>
                                    <a t-att-href="'/website/vcard/download/' + str(partner.id)" class="btn btn-dark btn-lg">
                                        <i class="fa fa-download me-2"></i>Download vCard
                                    </a>
                                </div>
                            </div>
                        </div>
                    </div>
                    
                    <!-- Vinculum Footer Banner -->
                    <div t-att-style="'padding: 20px 0; border-top: 1px solid #e9ecef; text-align: center; background: ' + (partner.primary_color or '#ffffff') + ';'">
                        <a href="{referral_url}" target="_blank" style="display: inline-block; color: #6c757d; text-decoration: none; font-size: 0.9rem; font-weight: 500; transition: all 0.3s ease; padding: 8px 16px; border-radius: 20px;">
                            Built with Vinculum <span style="display: inline-block; transition: transform 0.3s ease; margin: 0 4px;">→</span> Create yours
                        </a>
                    </div>
                                        </div>
                                    </t>
        </t>
        """
    
    def _build_corporate_template(self, image_url, banner_url=None, referral_url=None):
        """Build the corporate vCard template."""
        if referral_url is None:
            referral_url = self.get_referral_signup_url()
        
        google_maps_url = self._get_google_maps_url()
        google_maps_button = ''
        if google_maps_url:
            google_maps_button = f'<a href="{google_maps_url}" target="_blank" class="btn btn-sm btn-outline-primary ms-2" style="padding: 2px 8px; font-size: 0.75rem; margin-top: 4px; display: inline-block;"><i class="fas fa-map me-1"></i>Directions</a>'
        
        address_display = ''
        if self.street or self.city:
            address_parts = []
            if self.street:
                address_parts.append(self.street)
            if self.city:
                address_parts.append(self.city)
            if self.state_id and self.state_id.name:
                address_parts.append(self.state_id.name)
            if self.zip:
                address_parts.append(f' {self.zip}')
            if self.country_id and self.country_id.name:
                address_parts.append(self.country_id.name)
            address_display = ', '.join(address_parts)
        
        address_html = ''
        if address_display:
            address_html = f'''<p class="mb-3"><i class="fas fa-map-marker-alt me-2 text-primary"></i><span>{address_display}</span>{google_maps_button}</p>'''
        
        return f"""
        <t t-name="website.{self.website_slug}">
            <t t-set="partner" t-value="request.env['partner.vcard'].sudo().browse({self.id})"/>
            <t t-call="website.layout">
                <div class="corporate-vcard-container">
                    <div class="header-section" style="background: {self.primary_color or '#2c3e50'}; padding: 50px 0; border-bottom: 4px solid #34495e;">
                        <div class="container">
                            <div class="row align-items-center">
                                <div class="col-md-8">
                                    <h1 class="text-white display-6 fw-bold mb-2">{self.name or ''}</h1>
                                    <h2 class="text-white h4 mb-3">{self.company_name or ''}</h2>
                                    <p class="text-white-50 mb-0">{self.function or ''}</p>
                                        </div>
                                <div class="col-md-4 text-end">
                                    <img t-att-src="'{image_url}'" alt="Profile" style="width: 120px; height: 120px; border-radius: 10px; object-fit: cover; border: 2px solid white;"/>
                                </div>
                            </div>
                        </div>
                    </div>

                    <div class="content-section py-5">
                        <div class="container">
                            <div class="row">
                                <div class="col-lg-8">
                                    <h4 class="mb-4">Contact Information</h4>
                                    <div class="row">
                                        <div class="col-md-6">
                                            <t t-if="partner.email">
                                                <p class="mb-3"><i class="fas fa-envelope me-2 text-primary"></i><a t-att-href="'mailto:' + partner.email" class="text-decoration-none" t-esc="partner.email"/></p>
                                            </t>
                                            <t t-if="partner.phone">
                                                <p class="mb-3"><i class="fas fa-phone me-2 text-primary"></i><a t-att-href="'tel:' + partner.phone" class="text-decoration-none" t-esc="partner.phone"/></p>
                                            </t>
                                            {address_html}
                                        </div>
                                        <div class="col-md-6 text-center">
                                            <img t-att-src="'/vcard/qr_code/download/' + str(partner.id)" alt="QR Code" style="width: 150px; height: 150px; border-radius: 5px;"/>
                                        </div>
                                    </div>
                                    <div class="mt-4">
                                        <a t-att-href="'/website/vcard/download/' + str(partner.id)" class="btn btn-primary btn-lg">
                                            <i class="fa fa-download me-2"></i>Download vCard
                                        </a>
                                    </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                    
                    <!-- Vinculum Footer Banner -->
                    <div style="padding: 20px 0; background: ' + (partner.primary_color or '#ffffff') + '; border-top: 1px solid #e9ecef; text-align: center;">
                        <a href="{referral_url}" target="_blank" style="display: inline-block; color: #6c757d; text-decoration: none; font-size: 0.9rem; font-weight: 500; transition: all 0.3s ease; padding: 8px 16px; border-radius: 20px;">
                            Built with Vinculum <span style="display: inline-block; transition: transform 0.3s ease; margin: 0 4px;">→</span> Create yours
                        </a>
                    </div>
                </div>
            </t>
        </t>
        """
    
    def _build_creative_template(self, image_url, banner_url=None, referral_url=None):
        """Build the creative vCard template with animated background."""
        if referral_url is None:
            referral_url = self.get_referral_signup_url()
        
        google_maps_url = self._get_google_maps_url()
        google_maps_button = ''
        if google_maps_url:
            google_maps_button = f'<a href="{google_maps_url}" target="_blank" class="btn btn-sm ms-2" style="background: linear-gradient(45deg, #667eea, #764ba2); color: white; border: none; padding: 2px 8px; font-size: 0.75rem; margin-top: 4px; display: inline-block;"><i class="fas fa-map me-1"></i>Directions</a>'
        
        address_display = ''
        if self.street or self.city:
            address_parts = []
            if self.street:
                address_parts.append(self.street)
            if self.city:
                address_parts.append(self.city)
            if self.state_id and self.state_id.name:
                address_parts.append(self.state_id.name)
            if self.zip:
                address_parts.append(f' {self.zip}')
            if self.country_id and self.country_id.name:
                address_parts.append(self.country_id.name)
            address_display = ', '.join(address_parts)
        
        address_html = ''
        if address_display:
            address_html = f'''<div class="col-12 mb-3"><div class="p-3 bg-light rounded"><i class="fas fa-map-marker-alt me-2" style="color: #667eea;"></i><span>{address_display}</span>{google_maps_button}</div></div>'''
        
        return f"""
        <t t-name="website.{self.website_slug}">
            <t t-set="partner" t-value="request.env['partner.vcard'].sudo().browse({self.id})"/>
            <t t-call="website.layout">
                <style>
                    @keyframes gradientShift {{
                        0% {{ background-position: 0% 50%; }}
                        50% {{ background-position: 100% 50%; }}
                        100% {{ background-position: 0% 50%; }}
                    }}
                    .creative-bg {{
                        background: linear-gradient(45deg, #667eea, #764ba2, #f093fb);
                        background-size: 400% 400%;
                        animation: gradientShift 15s ease infinite;
                        min-height: 100vh;
                        padding: 50px 0;
                    }}
                    .creative-card {{
                        background: rgba(255,255,255,0.95);
                        border-radius: 30px;
                        padding: 40px;
                        box-shadow: 0 20px 40px rgba(0,0,0,0.2);
                    }}
                    .creative-name {{
                        font-size: 2.5rem;
                        font-weight: 700;
                        background: linear-gradient(45deg, #667eea, #764ba2);
                        -webkit-background-clip: text;
                        -webkit-text-fill-color: transparent;
                        background-clip: text;
                    }}
                </style>
                <div class="creative-bg">
                    <div class="container">
                        <div class="row justify-content-center">
                            <div class="col-lg-8">
                                <div class="creative-card">
                                    <div class="text-center mb-4">
                                        <img t-att-src="'{image_url}'" alt="Profile" style="width: 120px; height: 120px; border-radius: 50%; object-fit: cover; border: 4px solid white; box-shadow: 0 5px 15px rgba(0,0,0,0.2);"/>
                                        <h1 class="creative-name mt-3 mb-2">{self.name or ''}</h1>
                                        <h2 class="h5 text-muted mb-2">{self.function or ''}</h2>
                                        <h3 class="h6 text-secondary mb-4">{self.company_name or ''}</h3>
                </div>
                
                                    <div class="row mb-4">
                                        <div class="col-md-6 mb-3" t-if="partner.email">
                                            <div class="p-3 bg-light rounded">
                                                <i class="fas fa-envelope me-2" style="color: #667eea;"></i>
                                                <a t-att-href="'mailto:' + partner.email" class="text-decoration-none text-dark" t-esc="partner.email"/>
                                </div>
                                        </div>
                                        <div class="col-md-6 mb-3" t-if="partner.phone">
                                            <div class="p-3 bg-light rounded">
                                                <i class="fas fa-phone me-2" style="color: #667eea;"></i>
                                                <a t-att-href="'tel:' + partner.phone" class="text-decoration-none text-dark" t-esc="partner.phone"/>
                                        </div>
                                        </div>
                                        {address_html}
                                    </div>
                                    
                                    <div class="text-center mb-4">
                                        <img t-att-src="'/vcard/qr_code/download/' + str(partner.id)" alt="QR Code" style="width: 200px; height: 200px; border-radius: 20px; background: white; padding: 20px; box-shadow: 0 10px 30px rgba(0,0,0,0.15);"/>
                                </div>
                                    
                                    <div class="text-center">
                                        <a t-att-href="'/website/vcard/download/' + str(partner.id)" class="btn btn-lg text-white" style="background: linear-gradient(45deg, #667eea, #764ba2); border: none;">
                                            <i class="fa fa-download me-2"></i>Download vCard
                                        </a>
                                    </div>
                                </div>
                                </div>
                            </div>
                        </div>
                        
                        <!-- Vinculum Footer Banner -->
                        <div style="padding: 25px 0; background: rgba(255,255,255,0.95); border-top: 1px solid rgba(255,255,255,0.3); text-align: center;">
                            <a href="{referral_url}" target="_blank" style="display: inline-block; color: #6c757d; text-decoration: none; font-size: 0.9rem; font-weight: 500; transition: all 0.3s ease; padding: 8px 16px; border-radius: 20px;">
                                Built with Vinculum <span style="display: inline-block; transition: transform 0.3s ease; margin: 0 4px;">→</span> Create yours
                            </a>
                        </div>
                    </div>
            </t>
        </t>
        """

    @api.model
    def create(self, vals):
        partner = super(PartnerVCard, self).create(vals)
        # Generate QR code data during creation
        partner._generate_qr_code_data()
        # Generate QR code image with initial pattern
        partner._generate_qr_code_image()
        
        # Ensure referral_signup_url is computed
        partner._compute_referral_signup_url()
        
        return partner

    def write(self, vals):
        res = super(PartnerVCard, self).write(vals)
        # If the pattern or logo changes, regenerate the QR code image
        if 'qr_pattern' in vals or 'qr_logo' in vals:
            self._generate_qr_code_image()
        return res
    
    @api.depends(
    'whatsapp_url', 'linkedin_url', 'youtube_url', 'facebook_url', 'telegram_url',
    'instagram_url', 'tumblr_url', 'xing_url', 'github_url', 'vimeo_url',
    'messenger_url', 'dribbble_url', 'skype_url', 'doordash_url', 'tripadvisor_url',
    'yelp_url', 'twitter_url', 'google_reviews_url', 'ubereats_url', 'line_url',
    'vkontakte_url', 'reddit_url', 'viber_url', 'pinterest_url', 'tiktok_url',
    'snapchat_url', 'signal_url'
)
    def _compute_social_media_urls(self):
        """Automatically format the social media URLs if the user enters a slug (or correct the format)."""
        url_patterns = {
            'whatsapp_url': ('https://wa.me/', r'^\d+$'),
            'linkedin_url': ('https://www.linkedin.com/in/', r'^[a-zA-Z0-9_-]+$'),
            'linkedin_url_company': ('https://www.linkedin.com/company/', r'^[a-zA-Z0-9_-]+$'),
            'youtube_url': ('https://www.youtube.com/channel/', r'^[a-zA-Z0-9_-]+$'),
            'facebook_url': ('https://www.facebook.com/', r'^[a-zA-Z0-9._-]+$'),
            'facebook_url_company': ('https://www.facebook.com/', r'^[a-zA-Z0-9._-]+$'),
            'telegram_url': ('https://t.me/', r'^[a-zA-Z0-9_-]+$'),
            'instagram_url': ('https://www.instagram.com/', r'^[a-zA-Z0-9._-]+$'),
            'instagram_url_company': ('https://www.instagram.com/', r'^[a-zA-Z0-9._-]+$'),
            'tumblr_url': ('https://', r'^[a-zA-Z0-9_-]+\.tumblr\.com$'),
            'xing_url': ('https://www.xing.com/profile/', r'^[a-zA-Z0-9_-]+$'),
            'github_url': ('https://github.com/', r'^[a-zA-Z0-9_-]+$'),
            'vimeo_url': ('https://vimeo.com/', r'^[a-zA-Z0-9_-]+$'),
            'messenger_url': ('https://m.me/', r'^[a-zA-Z0-9._-]+$'),
            'dribbble_url': ('https://dribbble.com/', r'^[a-zA-Z0-9_-]+$'),
            'skype_url': ('skype:', r'^[a-zA-Z0-9._-]+$'),
            'doordash_url': ('https://www.doordash.com/store/', r'^[a-zA-Z0-9._-]+$'),
            'tripadvisor_url': ('https://www.tripadvisor.com/Profile/', r'^[a-zA-Z0-9._-]+$'),
            'yelp_url': ('https://www.yelp.com/biz/', r'^[a-zA-Z0-9._-]+$'),
            'twitter_url': ('https://www.twitter.com/', r'^[a-zA-Z0-9._-]+$'),
            'twitter_url_company': ('https://www.twitter.com/', r'^[a-zA-Z0-9._-]+$'),
            'google_reviews_url': ('https://g.page/', r'^[a-zA-Z0-9._-]+$'),
            'ubereats_url': ('https://www.ubereats.com/store/', r'^[a-zA-Z0-9._-]+$'),
            'line_url': ('https://line.me/R/ti/p/', r'^[a-zA-Z0-9._-]+$'),
            'vkontakte_url': ('https://vk.com/', r'^[a-zA-Z0-9._-]+$'),
            'reddit_url': ('https://www.reddit.com/user/', r'^[a-zA-Z0-9._-]+$'),
            'viber_url': ('viber://chat?number=', r'^[0-9]+$'),
            'pinterest_url': ('https://www.pinterest.com/', r'^[a-zA-Z0-9._-]+$'),
            'tiktok_url': ('https://www.tiktok.com/@', r'^[a-zA-Z0-9._-]+$'),
            'snapchat_url': ('https://www.snapchat.com/add/', r'^[a-zA-Z0-9._-]+$'),
            'signal_url': ('https://signal.me/#p/', r'^[0-9]+$')
        }

        for field_name, (prefix, slug_pattern) in url_patterns.items():
            field_value = getattr(self, field_name)
            if field_value:
                # Check if the user entered a full URL
                if field_value.startswith('http') or field_value.startswith('https'):
                    # If it's a full URL, do nothing
                    continue
                elif re.match(slug_pattern, field_value):
                    # If it's a valid slug, append the correct prefix
                    setattr(self, field_name, prefix + field_value)


    
    @api.depends('website_slug')
    def _compute_website_full_url(self):
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        for record in self:
            if record.website_slug:
                record.website_full_url = base_url + "/" + record.website_slug
            else:
                record.website_full_url = base_url
                
   
        
    def _generate_vcf(self):
        """Generate vCard (.vcf) file for the partner."""
        vcard = (
            f"BEGIN:VCARD\n"
            f"VERSION:3.0\n"
            f"FN:{self.name}\n"
            f"ORG:{self.company_name or ''}\n"
            f"TITLE:{self.function or ''}\n"
            f"TEL;TYPE=CELL:{self.phone or ''}\n"
            f"TEL;TYPE=WORK,VOICE:{self.mobile or ''}\n"
            f"EMAIL:{self.email or ''}\n"
            f"ADR;TYPE=WORK,PREF:;;{self.street or ''};{self.city or ''};{self.state_id.name or ''};{self.zip or ''};{self.country_id.name or ''}\n"
            f"END:VCARD"
        )
        return vcard
