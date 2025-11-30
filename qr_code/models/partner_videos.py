# -*- coding: utf-8 -*-
"""
Vinculum - Digital Business Cards Module
Copyright (C) 2024 Faris Delija. All Rights Reserved.
Licensed under OPL-1 (Odoo Proprietary License v1.0)

Unauthorized copying, modification, or distribution prohibited.
"""
from odoo import models, fields, api
from odoo.exceptions import ValidationError
from urllib.parse import urlparse

class vCardVideos(models.Model):
    _name = 'partner.vcard.videos'
    _description = 'Partner Videos'
    
    # Link to partner.vcard model, not res.partner
    partner_id = fields.Many2one('partner.vcard', string="Partner", required=True, ondelete='cascade')
    video_url = fields.Char(string="Video URL", required=True)
    name = fields.Char(string="Video Name", required=False)
    embed_url = fields.Char(string="Embed URL", compute='_compute_embed_url', store=True)
    active = fields.Boolean(string='Active', default=True, help='Archive this video to hide it from the vCard without deleting it')

    @api.depends('video_url')
    def _compute_embed_url(self):
        for record in self:
            url = record.video_url
            if not url:
                record.embed_url = ''
                continue
                
            import logging
            _logger = logging.getLogger(__name__)
            _logger.info(f"Processing video URL: {url}")
                
            parsed_url = urlparse(url)
            domain = parsed_url.netloc.lower()
            
            if 'youtube.com' in domain or 'youtu.be' in domain:
                video_id = None
                
                if 'youtube.com' in domain:
                    # Handle different YouTube URL formats
                    if 'watch' in parsed_url.path:
                        # Standard watch URL: https://www.youtube.com/watch?v=VIDEO_ID
                        query_params = parsed_url.query
                        if 'v=' in query_params:
                            video_id = query_params.split('v=')[1].split('&')[0]
                    elif 'embed' in parsed_url.path:
                        # Already an embed URL: https://www.youtube.com/embed/VIDEO_ID
                        video_id = parsed_url.path.split('/')[-1]
                    elif 'shorts' in parsed_url.path:
                        # YouTube Shorts: https://www.youtube.com/shorts/VIDEO_ID
                        video_id = parsed_url.path.split('/')[-1]
                elif 'youtu.be' in domain:
                    # Short URL: https://youtu.be/VIDEO_ID
                    video_id = parsed_url.path.split('/')[1]
                
                if video_id:
                    record.embed_url = f'https://www.youtube.com/embed/{video_id}'
                    _logger.info(f"Generated YouTube embed URL: {record.embed_url}")
                else:
                    record.embed_url = url  # Fallback to original URL
                    _logger.warning(f"Could not extract video ID from URL: {url}")
                    
            elif 'vimeo.com' in domain:
                if 'player.vimeo.com' in domain:
                    # Already a player URL: https://player.vimeo.com/video/VIDEO_ID
                    video_id = parsed_url.path.split('/')[-1]
                else:
                    # Regular Vimeo URL: https://vimeo.com/VIDEO_ID
                    video_id = parsed_url.path.split('/')[1]
                
                if video_id and video_id != 'video':
                    record.embed_url = f'https://player.vimeo.com/video/{video_id}'
                    _logger.info(f"Generated Vimeo embed URL: {record.embed_url}")
                else:
                    record.embed_url = url
                    _logger.warning(f"Could not extract video ID from Vimeo URL: {url}")
            else:
                record.embed_url = url  # Use original URL if not a known video site