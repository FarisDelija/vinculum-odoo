/**
 * Email Signature Generator for Partner vCard (Odoo 17)
 * 
 * Features:
 * - 5 signature templates (Modern, Classic, Minimal, Corporate, Creative)
 * - All templates unlocked (no plan restrictions for self-hosted)
 * - Fetches data via RPC for reliability
 * - User's brand color from secondary_color field
 * - Website link from website_full_url field
 * - Proper HTML copy to clipboard
 */

// Template configuration
const TEMPLATE_CONFIG = {
    modern: { name: 'Modern Template', icon: 'fa-bolt' },
    classic: { name: 'Classic Template', icon: 'fa-columns' },
    minimal: { name: 'Minimal Template', icon: 'fa-minus' },
    corporate: { name: 'Corporate Template', icon: 'fa-building' },
    creative: { name: 'Creative Template', icon: 'fa-paint-brush' }
};

// Current state
let currentTemplate = 'modern';
let currentData = {};
let recordId = null;

/**
 * Generate signature HTML templates
 * All templates use table-based layouts for maximum email client compatibility
 */
const SignatureTemplates = {
    classic: (d) => `
<table cellpadding="0" cellspacing="0" border="0" style="font-family: Arial, Helvetica, sans-serif; font-size: 14px; line-height: 1.4; color: #333333; max-width: 600px;">
    <tr>
        <td width="110" valign="top" style="padding-right: 20px;">
            ${d.profileImage ? `<img src="${d.profileImage}" alt="${d.name}" width="100" height="100" style="width: 100px; height: 100px; border-radius: 50%; display: block; margin-bottom: 15px; border: 2px solid #e5e7eb;" />` : ''}
            <img src="https://api.qrserver.com/v1/create-qr-code/?size=80x80&amp;data=${encodeURIComponent(d.vcardUrl)}" alt="QR Code" width="80" height="80" style="width: 80px; height: 80px; display: block; margin: 0 auto;" />
            <p style="font-size: 10px; color: #666666; margin: 5px 0 0 0; text-align: center;">Scan to Connect</p>
        </td>
        <td valign="top" style="border-left: 3px solid ${d.color}; padding-left: 20px;">
            <p style="font-weight: bold; font-size: 18px; color: #333333; margin: 0 0 2px 0;">${d.name}</p>
            <p style="color: ${d.color}; font-size: 14px; margin: 0 0 4px 0; font-weight: 600;">${d.jobTitle}</p>
            ${d.company ? `<p style="color: #666666; font-size: 14px; margin: 0 0 12px 0;">${d.company}</p>` : ''}
            <table cellpadding="0" cellspacing="0" border="0" style="font-size: 13px; color: #666666;">
                ${d.phone ? `<tr><td style="padding: 2px 8px 2px 0; color: ${d.color};">Phone:</td><td style="padding: 2px 0;"><a href="tel:${d.phone}" style="text-decoration: none; color: #333333;">${d.phone}</a></td></tr>` : ''}
                ${d.mobile ? `<tr><td style="padding: 2px 8px 2px 0; color: ${d.color};">Mobile:</td><td style="padding: 2px 0;"><a href="tel:${d.mobile}" style="text-decoration: none; color: #333333;">${d.mobile}</a></td></tr>` : ''}
                ${d.email ? `<tr><td style="padding: 2px 8px 2px 0; color: ${d.color};">Email:</td><td style="padding: 2px 0;"><a href="mailto:${d.email}" style="text-decoration: none; color: #333333;">${d.email}</a></td></tr>` : ''}
                ${d.vcardUrl ? `<tr><td style="padding: 2px 8px 2px 0; color: ${d.color};">Website:</td><td style="padding: 2px 0;"><a href="${d.vcardUrl}" style="text-decoration: none; color: ${d.color};">${d.vcardUrl}</a></td></tr>` : ''}
            </table>
            ${d.hasSocials ? `
            <table cellpadding="0" cellspacing="0" border="0" style="margin-top: 10px;">
                <tr>
                    ${d.linkedin ? `<td style="padding-right: 8px;"><a href="${d.linkedin}"><img src="https://cdn-icons-png.flaticon.com/32/174/174857.png" alt="LinkedIn" width="24" height="24" style="display: block; border: 0;" /></a></td>` : ''}
                    ${d.instagram ? `<td style="padding-right: 8px;"><a href="${d.instagram}"><img src="https://cdn-icons-png.flaticon.com/32/174/174855.png" alt="Instagram" width="24" height="24" style="display: block; border: 0;" /></a></td>` : ''}
                    ${d.twitter ? `<td style="padding-right: 8px;"><a href="${d.twitter}"><img src="https://cdn-icons-png.flaticon.com/32/5969/5969020.png" alt="Twitter" width="24" height="24" style="display: block; border: 0;" /></a></td>` : ''}
                    ${d.youtube ? `<td style="padding-right: 8px;"><a href="${d.youtube}"><img src="https://cdn-icons-png.flaticon.com/32/1384/1384060.png" alt="YouTube" width="24" height="24" style="display: block; border: 0;" /></a></td>` : ''}
                    ${d.facebook ? `<td style="padding-right: 8px;"><a href="${d.facebook}"><img src="https://cdn-icons-png.flaticon.com/32/733/733547.png" alt="Facebook" width="24" height="24" style="display: block; border: 0;" /></a></td>` : ''}
                </tr>
            </table>` : ''}
            <table cellpadding="0" cellspacing="0" border="0" style="margin-top: 12px;">
                <tr>
                    <td><a href="${d.vcfUrl}" style="background-color: ${d.color}; color: #ffffff; text-decoration: none; padding: 8px 16px; border-radius: 4px; font-size: 12px; font-weight: bold; display: inline-block;">Save Contact</a></td>
                </tr>
            </table>
        </td>
    </tr>
</table>`,

    modern: (d) => `
<table cellpadding="0" cellspacing="0" border="0" style="font-family: Arial, Helvetica, sans-serif; font-size: 14px; color: #333333; max-width: 600px;">
    <tr>
        <td colspan="3" style="padding-bottom: 12px; border-bottom: 3px solid ${d.color};">
            <span style="font-size: 20px; font-weight: bold; text-transform: uppercase; letter-spacing: 0.5px;">${d.name}</span>
            <span style="color: #999999; margin: 0 8px;">|</span>
            <span style="color: ${d.color}; font-weight: 600;">${d.jobTitle}</span>
        </td>
    </tr>
    <tr>
        <td style="padding-top: 15px;">
            <table cellpadding="0" cellspacing="0" border="0" width="100%">
                <tr>
                    <td width="90" valign="top" style="padding-right: 15px;">
                        ${d.profileImage ? `<img src="${d.profileImage}" alt="${d.name}" width="80" height="80" style="width: 80px; height: 80px; border-radius: 8px; display: block; margin-bottom: 10px; border: 1px solid #e5e7eb;" />` : ''}
                        <a href="${d.vcfUrl}" style="background-color: ${d.color}; color: #ffffff; text-decoration: none; padding: 6px 10px; border-radius: 4px; font-size: 10px; font-weight: bold; display: block; text-align: center;">Save Contact</a>
                    </td>
                    <td valign="top">
                        ${d.company ? `<p style="margin: 0 0 8px 0; font-weight: bold;">${d.company}</p>` : ''}
                        <table cellpadding="0" cellspacing="0" border="0" style="font-size: 12px;">
                            ${d.email ? `<tr><td style="padding: 2px 0;"><span style="color: ${d.color}; margin-right: 5px;">&#9993;</span><a href="mailto:${d.email}" style="text-decoration: none; color: #333333;">${d.email}</a></td></tr>` : ''}
                            ${d.mobile || d.phone ? `<tr><td style="padding: 2px 0;"><span style="color: ${d.color}; margin-right: 5px;">&#9742;</span><a href="tel:${d.mobile || d.phone}" style="text-decoration: none; color: #333333;">${d.mobile || d.phone}</a></td></tr>` : ''}
                            ${d.vcardUrl ? `<tr><td style="padding: 2px 0;"><span style="color: ${d.color}; margin-right: 5px;">&#127760;</span><a href="${d.vcardUrl}" style="text-decoration: none; color: ${d.color};">${d.vcardUrl}</a></td></tr>` : ''}
                        </table>
                        ${d.hasSocials ? `
                        <table cellpadding="0" cellspacing="0" border="0" style="margin-top: 8px;">
                            <tr>
                                ${d.linkedin ? `<td style="padding-right: 6px;"><a href="${d.linkedin}"><img src="https://cdn-icons-png.flaticon.com/32/174/174857.png" alt="LinkedIn" width="20" height="20" style="display: block; border: 0;" /></a></td>` : ''}
                                ${d.instagram ? `<td style="padding-right: 6px;"><a href="${d.instagram}"><img src="https://cdn-icons-png.flaticon.com/32/174/174855.png" alt="Instagram" width="20" height="20" style="display: block; border: 0;" /></a></td>` : ''}
                                ${d.twitter ? `<td style="padding-right: 6px;"><a href="${d.twitter}"><img src="https://cdn-icons-png.flaticon.com/32/5969/5969020.png" alt="Twitter" width="20" height="20" style="display: block; border: 0;" /></a></td>` : ''}
                            </tr>
                        </table>` : ''}
                    </td>
                    <td width="90" valign="top" align="right" style="padding-left: 15px;">
                        <img src="https://api.qrserver.com/v1/create-qr-code/?size=80x80&amp;data=${encodeURIComponent(d.vcardUrl)}" alt="QR Code" width="80" height="80" style="width: 80px; height: 80px; display: block; border: 1px solid #e2e8f0; padding: 2px;" />
                        <p style="font-size: 9px; color: #666666; margin: 5px 0 0 0; text-align: center; white-space: nowrap;">Scan to Connect</p>
                    </td>
                </tr>
            </table>
        </td>
    </tr>
</table>`,

    minimal: (d) => `
<table cellpadding="0" cellspacing="0" border="0" style="font-family: Helvetica, Arial, sans-serif; font-size: 13px; color: #333333; max-width: 500px;">
    <tr>
        <td width="75" valign="top" style="padding-right: 15px;">
            ${d.profileImage ? `<img src="${d.profileImage}" alt="${d.name}" width="60" height="60" style="width: 60px; height: 60px; border-radius: 50%; display: block; margin-bottom: 10px; border: 1px solid #ddd;" />` : ''}
            <img src="https://api.qrserver.com/v1/create-qr-code/?size=60x60&amp;data=${encodeURIComponent(d.vcardUrl)}" alt="QR" width="60" height="60" style="width: 60px; height: 60px; display: block;" />
            <p style="font-size: 8px; color: #666666; margin: 4px 0 0 0; text-align: center;">Scan to Connect</p>
        </td>
        <td valign="top">
            <p style="margin: 0 0 4px 0;"><strong style="font-size: 16px; color: #000000;">${d.name}</strong></p>
            <p style="margin: 0 0 8px 0; color: #666666;">${d.jobTitle}${d.company ? ' at ' + d.company : ''}</p>
            <table cellpadding="0" cellspacing="0" border="0" style="border-top: 1px solid #eeeeee; padding-top: 8px;">
                <tr>
                    ${d.mobile || d.phone ? `<td style="padding-right: 15px;"><a href="tel:${d.mobile || d.phone}" style="text-decoration: none; color: ${d.color}; font-weight: bold;">${d.mobile || d.phone}</a></td>` : ''}
                    ${d.email ? `<td style="padding-right: 15px;"><a href="mailto:${d.email}" style="text-decoration: none; color: ${d.color}; font-weight: bold;">${d.email}</a></td>` : ''}
                </tr>
            </table>
            ${d.vcardUrl ? `<p style="margin: 8px 0;"><a href="${d.vcardUrl}" style="text-decoration: none; color: ${d.color};">${d.vcardUrl}</a></p>` : ''}
            ${d.hasSocials ? `
            <table cellpadding="0" cellspacing="0" border="0" style="margin-top: 6px;">
                <tr>
                    ${d.linkedin ? `<td style="padding-right: 6px;"><a href="${d.linkedin}"><img src="https://cdn-icons-png.flaticon.com/32/174/174857.png" alt="LinkedIn" width="18" height="18" style="display: block; border: 0;" /></a></td>` : ''}
                    ${d.instagram ? `<td style="padding-right: 6px;"><a href="${d.instagram}"><img src="https://cdn-icons-png.flaticon.com/32/174/174855.png" alt="Instagram" width="18" height="18" style="display: block; border: 0;" /></a></td>` : ''}
                </tr>
            </table>` : ''}
            <table cellpadding="0" cellspacing="0" border="0" style="margin-top: 10px;">
                <tr>
                    <td><a href="${d.vcfUrl}" style="background-color: ${d.color}; color: #ffffff; text-decoration: none; padding: 8px 14px; border-radius: 4px; font-size: 12px; font-weight: bold; display: inline-block;">Save Contact</a></td>
                </tr>
            </table>
        </td>
    </tr>
</table>`,

    corporate: (d) => `
<table cellpadding="0" cellspacing="0" border="0" style="font-family: Verdana, Arial, sans-serif; font-size: 12px; color: #333333; max-width: 600px; background: #f9f9f9;">
    <tr>
        <td width="120" valign="middle" align="center" style="background: ${d.color}; padding: 20px;">
            ${d.profileImage ? `<img src="${d.profileImage}" alt="${d.name}" width="80" height="80" style="width: 80px; height: 80px; border-radius: 4px; border: 2px solid white; display: block; margin: 0 auto 15px auto;" />` : ''}
            <a href="${d.vcfUrl}" style="background: rgba(255,255,255,0.2); color: #ffffff; text-decoration: none; padding: 6px 12px; border-radius: 4px; font-size: 10px; font-weight: bold; display: inline-block;">Save Contact</a>
        </td>
        <td valign="top" style="padding: 20px; background: #ffffff; border: 1px solid #e2e8f0; border-left: none; border-right: none;">
            <p style="font-size: 18px; font-weight: bold; color: #333333; margin: 0 0 2px 0;">${d.name}</p>
            <p style="font-size: 11px; text-transform: uppercase; letter-spacing: 1px; color: #666666; margin: 0 0 15px 0;">${d.jobTitle}</p>
            <table cellpadding="0" cellspacing="0" border="0" width="100%" style="font-size: 12px;">
                ${d.mobile || d.phone ? `<tr><td width="20" valign="top" style="color: ${d.color}; font-weight: bold;">P</td><td style="padding-bottom: 6px;">${d.mobile || d.phone}</td></tr>` : ''}
                ${d.email ? `<tr><td width="20" valign="top" style="color: ${d.color}; font-weight: bold;">E</td><td style="padding-bottom: 6px;"><a href="mailto:${d.email}" style="text-decoration: none; color: #333333;">${d.email}</a></td></tr>` : ''}
                ${d.vcardUrl ? `<tr><td width="20" valign="top" style="color: ${d.color}; font-weight: bold;">W</td><td style="padding-bottom: 6px;"><a href="${d.vcardUrl}" style="text-decoration: none; color: ${d.color};">${d.vcardUrl}</a></td></tr>` : ''}
            </table>
            ${d.hasSocials ? `
            <table cellpadding="0" cellspacing="0" border="0" style="margin-top: 8px;">
                <tr>
                    ${d.linkedin ? `<td style="padding-right: 6px;"><a href="${d.linkedin}"><img src="https://cdn-icons-png.flaticon.com/32/174/174857.png" alt="LinkedIn" width="18" height="18" style="display: block; border: 0;" /></a></td>` : ''}
                    ${d.twitter ? `<td style="padding-right: 6px;"><a href="${d.twitter}"><img src="https://cdn-icons-png.flaticon.com/32/5969/5969020.png" alt="Twitter" width="18" height="18" style="display: block; border: 0;" /></a></td>` : ''}
                </tr>
            </table>` : ''}
        </td>
        <td width="100" valign="middle" align="center" style="padding: 20px; background: #ffffff; border: 1px solid #e2e8f0; border-left: none;">
            <img src="https://api.qrserver.com/v1/create-qr-code/?size=80x80&amp;data=${encodeURIComponent(d.vcardUrl)}" alt="QR" width="80" height="80" style="width: 80px; height: 80px; display: block;" />
            <p style="font-size: 9px; color: #666666; margin: 5px 0 0 0; text-align: center;">Scan to Connect</p>
        </td>
    </tr>
</table>`,

    creative: (d) => `
<table cellpadding="0" cellspacing="0" border="0" style="font-family: Georgia, serif; font-size: 14px; color: #333333; max-width: 600px;">
    <tr>
        <td width="130" valign="middle" align="center" style="padding-right: 20px;">
            ${d.profileImage ? `<img src="${d.profileImage}" alt="${d.name}" width="100" height="100" style="width: 100px; height: 100px; border-radius: 50px 0 50px 0; display: block; margin-bottom: 15px; border: 2px solid #e5e7eb;" />` : ''}
            <img src="https://api.qrserver.com/v1/create-qr-code/?size=80x80&amp;data=${encodeURIComponent(d.vcardUrl)}" alt="QR" width="80" height="80" style="width: 80px; height: 80px; display: block; border: 1px solid ${d.color}; padding: 2px;" />
            <p style="font-size: 10px; color: #666666; margin: 5px 0 0 0; text-align: center;">Scan to Connect</p>
        </td>
        <td valign="middle">
            <p style="margin: 0 0 5px 0; font-size: 22px; font-family: Arial, sans-serif; color: ${d.color}; font-weight: bold;">${d.name}</p>
            <p style="margin: 0 0 15px 0; font-style: italic; color: #666666;">${d.jobTitle}${d.company ? ' | ' + d.company : ''}</p>
            <table cellpadding="0" cellspacing="0" border="0" style="border-top: 2px solid #e2e8f0; padding-top: 10px;">
                <tr>
                    ${d.mobile || d.phone ? `<td style="padding-right: 15px; font-family: Arial, sans-serif; font-size: 12px;"><strong style="color: ${d.color};">M:</strong> ${d.mobile || d.phone}</td>` : ''}
                    ${d.email ? `<td style="padding-right: 15px; font-family: Arial, sans-serif; font-size: 12px;"><strong style="color: ${d.color};">E:</strong> <a href="mailto:${d.email}" style="text-decoration: none; color: #333333;">${d.email}</a></td>` : ''}
                </tr>
            </table>
            ${d.vcardUrl ? `<p style="margin: 8px 0; font-family: Arial, sans-serif; font-size: 12px;"><strong style="color: ${d.color};">W:</strong> <a href="${d.vcardUrl}" style="text-decoration: none; color: ${d.color};">${d.vcardUrl}</a></p>` : ''}
            ${d.hasSocials ? `
            <table cellpadding="0" cellspacing="0" border="0" style="margin-top: 8px;">
                <tr>
                    ${d.linkedin ? `<td style="padding-right: 6px;"><a href="${d.linkedin}"><img src="https://cdn-icons-png.flaticon.com/32/174/174857.png" alt="LinkedIn" width="20" height="20" style="display: block; border: 0;" /></a></td>` : ''}
                    ${d.instagram ? `<td style="padding-right: 6px;"><a href="${d.instagram}"><img src="https://cdn-icons-png.flaticon.com/32/174/174855.png" alt="Instagram" width="20" height="20" style="display: block; border: 0;" /></a></td>` : ''}
                    ${d.twitter ? `<td style="padding-right: 6px;"><a href="${d.twitter}"><img src="https://cdn-icons-png.flaticon.com/32/5969/5969020.png" alt="Twitter" width="20" height="20" style="display: block; border: 0;" /></a></td>` : ''}
                    ${d.youtube ? `<td style="padding-right: 6px;"><a href="${d.youtube}"><img src="https://cdn-icons-png.flaticon.com/32/1384/1384060.png" alt="YouTube" width="20" height="20" style="display: block; border: 0;" /></a></td>` : ''}
                    ${d.facebook ? `<td style="padding-right: 6px;"><a href="${d.facebook}"><img src="https://cdn-icons-png.flaticon.com/32/733/733547.png" alt="Facebook" width="20" height="20" style="display: block; border: 0;" /></a></td>` : ''}
                </tr>
            </table>` : ''}
            <table cellpadding="0" cellspacing="0" border="0" style="margin-top: 12px;">
                <tr>
                    <td><a href="${d.vcfUrl}" style="background-color: ${d.color}; color: #ffffff; text-decoration: none; padding: 8px 16px; border-radius: 4px; font-size: 12px; font-weight: bold; display: inline-block; font-family: Arial, sans-serif;">Save Contact</a></td>
                </tr>
            </table>
        </td>
    </tr>
</table>`
};

/**
 * Extract record ID from Odoo 17 URL or DOM
 * Odoo 17 uses OWL framework and hash-based routing
 */
function getRecordId() {
    const urlHash = window.location.hash || '';
    const urlPath = window.location.pathname || '';

    console.log('getRecordId - Hash:', urlHash, 'Path:', urlPath);

    // Method 1: Parse hash parameters (Odoo 17 standard format)
    // Hash looks like: #id=5&cids=1&menu_id=228&action=297&model=partner.vcard&view_type=form
    // or: #action=297&id=5&model=partner.vcard&view_type=form&cids=1&menu_id=228
    if (urlHash) {
        // Remove the leading # and parse as URL params
        const hashParams = new URLSearchParams(urlHash.substring(1));
        const hashId = hashParams.get('id');
        if (hashId) {
            console.log('Found ID from hash params:', hashId);
            return hashId;
        }

        // Alternative: regex match for id= anywhere in hash
        const match = urlHash.match(/[#&]id=(\d+)/);
        if (match) {
            console.log('Found ID from hash regex:', match[1]);
            return match[1];
        }
    }

    // Method 2: Try Odoo 17 new path format /odoo/partner.vcard/XX
    let match = urlPath.match(/\/odoo\/[^/]+\/(\d+)/);
    if (match) {
        console.log('Found ID from odoo path:', match[1]);
        return match[1];
    }

    // Method 3: Try path-based format /partner.vcard/XX
    match = urlPath.match(/\/partner\.vcard\/(\d+)/);
    if (match) {
        console.log('Found ID from model path:', match[1]);
        return match[1];
    }

    // Method 4: Try to get from OWL component __owl__ property
    try {
        const formView = document.querySelector('.o_form_view');
        if (formView && formView.__owl__) {
            const component = formView.__owl__;
            // OWL stores resId in component props or state
            if (component.props && component.props.resId) {
                console.log('Found ID from OWL props:', component.props.resId);
                return String(component.props.resId);
            }
            if (component.state && component.state.resId) {
                console.log('Found ID from OWL state:', component.state.resId);
                return String(component.state.resId);
            }
        }
    } catch (e) {
        console.log('OWL access error:', e);
    }

    // Method 5: Try to find the record ID in action manager's state
    try {
        if (window.odoo && window.odoo.__DEBUG__ && window.odoo.__DEBUG__.services) {
            const actionService = window.odoo.__DEBUG__.services['action_service'] ||
                window.odoo.__DEBUG__.services['action'];
            if (actionService && actionService.currentController) {
                const resId = actionService.currentController.props?.resId;
                if (resId) {
                    console.log('Found ID from action service:', resId);
                    return String(resId);
                }
            }
        }
    } catch (e) {
        console.log('Action service access error:', e);
    }

    // Method 6: Look for data attributes in the form
    const formEl = document.querySelector('.o_form_view, [data-res-id], [data-id]');
    if (formEl) {
        const resId = formEl.dataset.resId || formEl.dataset.id ||
            formEl.getAttribute('data-res-id') || formEl.getAttribute('data-id');
        if (resId) {
            console.log('Found ID from data attribute:', resId);
            return resId;
        }
    }

    // Method 7: Look for hidden input fields
    const hiddenId = document.querySelector('input[name="id"], input.o_field_id');
    if (hiddenId && hiddenId.value) {
        console.log('Found ID from hidden input:', hiddenId.value);
        return hiddenId.value;
    }

    // Method 8: URL search params
    const params = new URLSearchParams(window.location.search);
    const idParam = params.get('id');
    if (idParam) {
        console.log('Found ID from search params:', idParam);
        return idParam;
    }

    console.log('No record ID found by any method');
    return '';
}

/**
 * Fetch vCard data via Odoo RPC
 */
async function fetchVCardData(id) {
    const baseUrl = window.location.origin;

    try {
        const response = await fetch('/web/dataset/call_kw/partner.vcard/read', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                jsonrpc: '2.0',
                method: 'call',
                params: {
                    model: 'partner.vcard',
                    method: 'read',
                    args: [[parseInt(id)]],
                    kwargs: {
                        fields: [
                            'name', 'function', 'company_name', 'email', 'phone', 'mobile',
                            'secondary_color', 'website_full_url', 'website_slug',
                            'linkedin_url', 'instagram_url', 'twitter_url', 'youtube_url', 'facebook_url',
                            'image_url'
                        ]
                    }
                },
                id: Math.floor(Math.random() * 1000000)
            })
        });

        const data = await response.json();
        console.log('RPC Response:', data);

        if (data.result && data.result.length > 0) {
            const record = data.result[0];

            // Build the profile image as base64 data URI for email client compatibility
            let profileImage = '';
            if (record.image_url) {
                profileImage = `data:image/png;base64,${record.image_url}`;
            }

            // Build vCard URL
            let vcardUrl = record.website_full_url || '';
            if (!vcardUrl && record.website_slug) {
                vcardUrl = `${baseUrl}/${record.website_slug}`;
            }
            if (!vcardUrl) {
                vcardUrl = `${baseUrl}/vcard/${id}`;
            }

            const vcfUrl = `${baseUrl}/website/vcard/download/${id}`;

            const linkedin = record.linkedin_url || '';
            const instagram = record.instagram_url || '';
            const twitter = record.twitter_url || '';
            const youtube = record.youtube_url || '';
            const facebook = record.facebook_url || '';

            return {
                name: record.name || 'Your Name',
                jobTitle: record.function || 'Job Title',
                company: record.company_name || '',
                email: record.email || '',
                phone: record.phone || '',
                mobile: record.mobile || '',
                color: record.secondary_color || '#4C75A3',
                vcardUrl: vcardUrl,
                vcfUrl: vcfUrl,
                linkedin, instagram, twitter, youtube, facebook,
                profileImage,
                hasSocials: linkedin || instagram || twitter || youtube || facebook
            };
        }
    } catch (error) {
        console.error('RPC Error:', error);
    }

    // Return defaults if RPC fails
    return {
        name: 'Your Name',
        jobTitle: 'Job Title',
        company: '',
        email: '',
        phone: '',
        mobile: '',
        color: '#4C75A3',
        vcardUrl: `${baseUrl}/vcard/${id}`,
        vcfUrl: `${baseUrl}/website/vcard/download/${id}`,
        linkedin: '', instagram: '', twitter: '', youtube: '', facebook: '',
        profileImage: '',
        hasSocials: false
    };
}

/**
 * Update the signature preview
 */
async function updatePreview() {
    if (!recordId) {
        recordId = getRecordId();
    }

    if (!recordId) {
        console.error('No record ID found');
        return;
    }

    // Fetch data from backend
    currentData = await fetchVCardData(recordId);
    console.log('Signature Generator Data:', currentData);

    const preview = document.getElementById('sig-preview');
    if (preview && SignatureTemplates[currentTemplate]) {
        preview.innerHTML = SignatureTemplates[currentTemplate](currentData);
    }

    // Update template header
    updateTemplateHeader(currentData.color);
}

/**
 * Update the template header (icon and name)
 */
function updateTemplateHeader(color) {
    const config = TEMPLATE_CONFIG[currentTemplate];
    if (!config) return;

    const iconEl = document.getElementById('sig-template-icon');
    const nameEl = document.getElementById('sig-template-name');
    const copyBtn = document.getElementById('copy-sig-btn');

    if (iconEl) {
        iconEl.style.background = color;
        iconEl.innerHTML = `<i class="fa ${config.icon}" style="color: white; font-size: 14px;"></i>`;
    }

    if (nameEl) {
        nameEl.textContent = config.name;
    }

    if (copyBtn) {
        copyBtn.style.background = color;
    }
}

/**
 * Copy signature HTML to clipboard
 */
function copySignature() {
    const preview = document.getElementById('sig-preview');
    if (!preview) return;

    const copyBtn = document.getElementById('copy-sig-btn');
    const originalColor = currentData.color || '#4C75A3';

    try {
        const htmlContent = preview.innerHTML;
        const blob = new Blob([htmlContent], { type: 'text/html' });
        const clipboardItem = new ClipboardItem({
            'text/html': blob,
            'text/plain': new Blob([preview.innerText], { type: 'text/plain' })
        });

        navigator.clipboard.write([clipboardItem]).then(() => {
            showCopySuccess(copyBtn, originalColor);
        }).catch(() => {
            fallbackCopy(preview, copyBtn, originalColor);
        });
    } catch (e) {
        fallbackCopy(preview, copyBtn, originalColor);
    }
}

/**
 * Fallback copy method using selection
 */
function fallbackCopy(element, btn, color) {
    const range = document.createRange();
    range.selectNodeContents(element);
    const selection = window.getSelection();
    selection.removeAllRanges();
    selection.addRange(range);

    try {
        document.execCommand('copy');
        showCopySuccess(btn, color);
    } catch (err) {
        console.error('Copy failed:', err);
        if (btn) {
            btn.innerHTML = '<i class="fa fa-times"></i> Failed';
            btn.style.background = '#ef4444';
            setTimeout(() => {
                btn.innerHTML = '<i class="fa fa-copy"></i> Copy Signature';
                btn.style.background = color;
            }, 2000);
        }
    }

    selection.removeAllRanges();
}

/**
 * Show copy success feedback
 */
function showCopySuccess(btn, color) {
    if (!btn) return;
    btn.innerHTML = '<i class="fa fa-check"></i> Copied!';
    btn.style.background = '#10b981';
    setTimeout(() => {
        btn.innerHTML = '<i class="fa fa-copy"></i> Copy Signature';
        btn.style.background = color;
    }, 2000);
}

/**
 * Handle template change
 */
function onTemplateChange(e) {
    currentTemplate = e.target.value;
    updatePreview();
}

/**
 * Initialize signature generator
 */
function initSignatureGenerator() {
    const gallery = document.querySelector('.signature-gallery');
    if (!gallery || gallery.dataset.initialized) return;

    gallery.dataset.initialized = 'true';
    recordId = getRecordId();
    console.log('Initializing signature generator for record:', recordId);

    // Setup template selector
    const templateSelect = document.getElementById('sig-template-select');
    if (templateSelect) {
        templateSelect.addEventListener('change', onTemplateChange);
    }

    // Setup copy button
    const copyBtn = document.getElementById('copy-sig-btn');
    if (copyBtn) {
        copyBtn.addEventListener('click', function (e) {
            e.preventDefault();
            e.stopPropagation();
            copySignature();
        });
    }

    // Initial render
    updatePreview();
}

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', function () {
    initSignatureGenerator();

    if (document.body) {
        const observer = new MutationObserver((mutations) => {
            const gallery = document.querySelector('.signature-gallery');
            if (gallery && !gallery.dataset.initialized) {
                initSignatureGenerator();
            }
        });

        observer.observe(document.body, { childList: true, subtree: true });
    }
});

// Also try to initialize if loaded after DOMContentLoaded
if (document.readyState === 'complete' || document.readyState === 'interactive') {
    setTimeout(initSignatureGenerator, 100);
}
