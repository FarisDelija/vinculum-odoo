/**
 * Virtual Meeting Background Generator for Partner vCard (Odoo 17)
 * 
 * Features:
 * - Generate 1920x1080 backgrounds for Zoom/Teams
 * - Multiple layout templates (Classic, Modern, Minimal, Corporate)
 * - Solid colors, gradients, and custom image backgrounds
 * - All features unlocked (no plan restrictions for self-hosted)
 * - User's QR code and vCard data overlaid
 */

// Background type configurations
const BACKGROUND_COLORS = {
    navy: { name: 'Navy', color: '#1e3a5f', textColor: '#ffffff' },
    slate: { name: 'Slate', color: '#475569', textColor: '#ffffff' },
    charcoal: { name: 'Charcoal', color: '#374151', textColor: '#ffffff' },
    forest: { name: 'Forest', color: '#166534', textColor: '#ffffff' },
    teal: { name: 'Teal', color: '#0d9488', textColor: '#ffffff' },
    emerald: { name: 'Emerald', color: '#059669', textColor: '#ffffff' },
    burgundy: { name: 'Burgundy', color: '#7f1d1d', textColor: '#ffffff' },
    purple: { name: 'Purple', color: '#581c87', textColor: '#ffffff' },
    indigo: { name: 'Indigo', color: '#3730a3', textColor: '#ffffff' },
    bronze: { name: 'Bronze', color: '#78350f', textColor: '#ffffff' }
};

const BACKGROUND_GRADIENTS = {
    oceanBlue: { name: 'Ocean Blue', gradient: 'linear-gradient(135deg, #1e3a5f 0%, #0d9488 100%)', textColor: '#ffffff' },
    sunsetWarm: { name: 'Sunset', gradient: 'linear-gradient(135deg, #7f1d1d 0%, #ea580c 100%)', textColor: '#ffffff' },
    purpleHaze: { name: 'Purple Haze', gradient: 'linear-gradient(135deg, #581c87 0%, #3730a3 100%)', textColor: '#ffffff' },
    forestMist: { name: 'Forest Mist', gradient: 'linear-gradient(135deg, #166534 0%, #0d9488 100%)', textColor: '#ffffff' },
    midnight: { name: 'Midnight', gradient: 'linear-gradient(135deg, #0f172a 0%, #1e3a5f 100%)', textColor: '#ffffff' },
    corporate: { name: 'Corporate', gradient: 'linear-gradient(135deg, #1f2937 0%, #4b5563 100%)', textColor: '#ffffff' }
};

const BACKGROUND_IMAGES = {
    office: { name: 'Home Office', src: '/qr_code_odoo/static/src/img/virtual_bg/bg_office.jpg', textColor: '#ffffff' },
    modern: { name: 'Modern Shelf', src: '/qr_code_odoo/static/src/img/virtual_bg/bg_modern.jpg', textColor: '#ffffff' },
    minimal: { name: 'Minimal Room', src: '/qr_code_odoo/static/src/img/virtual_bg/bg_minimal.jpg', textColor: '#ffffff' },
    hotel: { name: 'Hotel Lobby', src: '/qr_code_odoo/static/src/img/virtual_bg/bg_hotel.jpg', textColor: '#ffffff' },
    white_wall: { name: 'White Wall', src: '/qr_code_odoo/static/src/img/virtual_bg/bg_white_wall.jpg', textColor: '#ffffff' },
    matrix: { name: 'Digital Rain', src: '/qr_code_odoo/static/src/img/virtual_bg/bg_matrix.jpg', textColor: '#ffffff' },
    coffee: { name: 'This is Fine', src: '/qr_code_odoo/static/src/img/virtual_bg/bg_coffee.jpg', textColor: '#ffffff' }
};

// Layout configurations
const LAYOUT_CONFIG = {
    classic: { name: 'Classic', description: 'Text top-left, QR top-right' },
    modern: { name: 'Modern', description: 'Centered with subtle overlay' },
    minimal: { name: 'Minimal', description: 'Small elements, clean space' },
    corporate: { name: 'Corporate', description: 'Professional with accent bar' }
};

// Canvas dimensions
const BG_WIDTH = 1920;
const BG_HEIGHT = 1080;

// Current state
let currentLayout = 'classic';
let currentBgType = 'color';
let currentBgValue = 'navy';
let currentBgImage = null;
let currentLogoImg = null;
let vbgData = {};
let vbgRecordId = null;

/**
 * Get record ID from URL (same as signature generator)
 */
function getVbgRecordId() {
    const urlHash = window.location.hash || '';
    const urlPath = window.location.pathname || '';

    console.log('VBG getRecordId - Hash:', urlHash, 'Path:', urlPath);

    // Method 1: Parse hash parameters
    if (urlHash) {
        const hashParams = new URLSearchParams(urlHash.substring(1));
        const hashId = hashParams.get('id');
        if (hashId) {
            console.log('VBG Found ID from hash params:', hashId);
            return hashId;
        }

        const match = urlHash.match(/[#&]id=(\d+)/);
        if (match) {
            console.log('VBG Found ID from hash regex:', match[1]);
            return match[1];
        }
    }

    // Method 2: Path-based format
    let match = urlPath.match(/\/odoo\/[^/]+\/(\d+)/);
    if (match) return match[1];

    match = urlPath.match(/\/partner\.vcard\/(\d+)/);
    if (match) return match[1];

    // Method 3: OWL component
    try {
        const formView = document.querySelector('.o_form_view');
        if (formView && formView.__owl__) {
            const component = formView.__owl__;
            if (component.props && component.props.resId) return String(component.props.resId);
            if (component.state && component.state.resId) return String(component.state.resId);
        }
    } catch (e) { }

    // Method 4: Data attributes
    const formEl = document.querySelector('.o_form_view, [data-res-id], [data-id]');
    if (formEl) {
        const resId = formEl.dataset.resId || formEl.dataset.id;
        if (resId) return resId;
    }

    // Method 5: URL search params
    const params = new URLSearchParams(window.location.search);
    const idParam = params.get('id');
    if (idParam) return idParam;

    console.log('VBG: No record ID found');
    return null;
}

/**
 * Fetch vCard data for background generation
 */
async function fetchVbgData(id) {
    const baseUrl = window.location.origin;

    try {
        const response = await fetch('/web/dataset/call_kw/partner.vcard/read', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                jsonrpc: '2.0',
                method: 'call',
                params: {
                    model: 'partner.vcard',
                    method: 'read',
                    args: [[parseInt(id)]],
                    kwargs: {
                        fields: [
                            'name', 'function', 'company_name',
                            'qr_code', 'secondary_color',
                            'website_full_url', 'website_slug'
                        ]
                    }
                },
                id: Math.floor(Math.random() * 1000000)
            })
        });

        const data = await response.json();
        console.log('Virtual BG RPC Response:', data);

        if (data.result && data.result.length > 0) {
            const record = data.result[0];

            let vcardUrl = record.website_full_url || '';
            if (!vcardUrl && record.website_slug) {
                vcardUrl = `${baseUrl}/${record.website_slug}`;
            }
            if (!vcardUrl) {
                vcardUrl = `${baseUrl}/vcard/${id}`;
            }

            let qrCode = record.qr_code || null;
            if (!qrCode && vcardUrl) {
                qrCode = `https://api.qrserver.com/v1/create-qr-code/?size=200x200&data=${encodeURIComponent(vcardUrl)}`;
            }

            return {
                name: record.name || 'Your Name',
                title: record.function || '',
                company: record.company_name || '',
                qrCode: qrCode,
                brandColor: record.secondary_color || '#4C75A3',
                vcardUrl: vcardUrl
            };
        }
    } catch (error) {
        console.error('Error fetching vCard data for virtual background:', error);
    }

    return {
        name: 'Your Name',
        title: 'Your Title',
        company: 'Your Company',
        qrCode: null,
        brandColor: '#4C75A3',
        vcardUrl: ''
    };
}

/**
 * Draw background on canvas
 */
function drawBackground(ctx, type, value, customImg = null) {
    if (type === 'custom' && customImg) {
        const imgRatio = customImg.width / customImg.height;
        const canvasRatio = BG_WIDTH / BG_HEIGHT;
        let drawWidth, drawHeight, drawX, drawY;

        if (imgRatio > canvasRatio) {
            drawHeight = BG_HEIGHT;
            drawWidth = drawHeight * imgRatio;
            drawX = (BG_WIDTH - drawWidth) / 2;
            drawY = 0;
        } else {
            drawWidth = BG_WIDTH;
            drawHeight = drawWidth / imgRatio;
            drawX = 0;
            drawY = (BG_HEIGHT - drawHeight) / 2;
        }
        ctx.drawImage(customImg, drawX, drawY, drawWidth, drawHeight);
    } else if (type === 'image' && currentBgImage) {
        const imgRatio = currentBgImage.width / currentBgImage.height;
        const canvasRatio = BG_WIDTH / BG_HEIGHT;
        let drawWidth, drawHeight, drawX, drawY;

        if (imgRatio > canvasRatio) {
            drawHeight = BG_HEIGHT;
            drawWidth = drawHeight * imgRatio;
            drawX = (BG_WIDTH - drawWidth) / 2;
            drawY = 0;
        } else {
            drawWidth = BG_WIDTH;
            drawHeight = drawWidth / imgRatio;
            drawX = 0;
            drawY = (BG_HEIGHT - drawHeight) / 2;
        }
        ctx.drawImage(currentBgImage, drawX, drawY, drawWidth, drawHeight);
    } else if (type === 'gradient' && BACKGROUND_GRADIENTS[value]) {
        const gradientDef = BACKGROUND_GRADIENTS[value].gradient;
        const gradient = ctx.createLinearGradient(0, 0, BG_WIDTH, BG_HEIGHT);
        const colorMatch = gradientDef.match(/#[a-fA-F0-9]{6}/g);
        if (colorMatch && colorMatch.length >= 2) {
            gradient.addColorStop(0, colorMatch[0]);
            gradient.addColorStop(1, colorMatch[1]);
        }
        ctx.fillStyle = gradient;
        ctx.fillRect(0, 0, BG_WIDTH, BG_HEIGHT);
    } else {
        const colorDef = BACKGROUND_COLORS[value] || BACKGROUND_COLORS.navy;
        ctx.fillStyle = colorDef.color;
        ctx.fillRect(0, 0, BG_WIDTH, BG_HEIGHT);
    }
}

/**
 * Draw gradient scrim behind text areas
 */
function drawScrim(ctx, layout) {
    if (currentBgType !== 'image' && currentBgType !== 'custom') return;

    ctx.save();
    if (layout === 'classic') {
        const gradient = ctx.createRadialGradient(0, 0, 0, 0, 0, 2500);
        gradient.addColorStop(0, 'rgba(0, 0, 0, 0.6)');
        gradient.addColorStop(0.1, 'rgba(0, 0, 0, 0.45)');
        gradient.addColorStop(0.25, 'rgba(0, 0, 0, 0.25)');
        gradient.addColorStop(0.5, 'rgba(0, 0, 0, 0.1)');
        gradient.addColorStop(0.75, 'rgba(0, 0, 0, 0.02)');
        gradient.addColorStop(1, 'rgba(0, 0, 0, 0)');
        ctx.fillStyle = gradient;
        ctx.fillRect(0, 0, BG_WIDTH, BG_HEIGHT);
    } else if (layout === 'modern') {
        const h = 500;
        const gradient = ctx.createLinearGradient(0, 0, 0, h);
        gradient.addColorStop(0, 'rgba(0, 0, 0, 0.7)');
        gradient.addColorStop(0.2, 'rgba(0, 0, 0, 0.55)');
        gradient.addColorStop(0.4, 'rgba(0, 0, 0, 0.35)');
        gradient.addColorStop(0.6, 'rgba(0, 0, 0, 0.15)');
        gradient.addColorStop(0.8, 'rgba(0, 0, 0, 0.04)');
        gradient.addColorStop(1, 'rgba(0, 0, 0, 0)');
        ctx.fillStyle = gradient;
        ctx.fillRect(0, 0, BG_WIDTH, h);
    } else if (layout === 'minimal' || layout === 'corporate') {
        const h = 450;
        const startY = BG_HEIGHT - h;
        const gradient = ctx.createLinearGradient(0, startY, 0, BG_HEIGHT);
        gradient.addColorStop(0, 'rgba(0, 0, 0, 0)');
        gradient.addColorStop(0.2, 'rgba(0, 0, 0, 0.04)');
        gradient.addColorStop(0.4, 'rgba(0, 0, 0, 0.15)');
        gradient.addColorStop(0.6, 'rgba(0, 0, 0, 0.35)');
        gradient.addColorStop(0.8, 'rgba(0, 0, 0, 0.6)');
        gradient.addColorStop(1, 'rgba(0, 0, 0, 0.85)');
        ctx.fillStyle = gradient;
        ctx.fillRect(0, startY, BG_WIDTH, h);
    }
    ctx.restore();
}

/**
 * Get text color based on background
 */
function getTextColor(type, value) {
    if (type === 'gradient' && BACKGROUND_GRADIENTS[value]) {
        return BACKGROUND_GRADIENTS[value].textColor;
    } else if (type === 'image' && BACKGROUND_IMAGES[value]) {
        return BACKGROUND_IMAGES[value].textColor;
    } else if (type === 'color' && BACKGROUND_COLORS[value]) {
        return BACKGROUND_COLORS[value].textColor;
    }
    return '#ffffff';
}

/**
 * Draw QR code on canvas
 */
function drawQrCode(ctx, qrCodeBase64, x, y, size) {
    return new Promise((resolve) => {
        if (!qrCodeBase64) {
            resolve();
            return;
        }

        const img = new Image();
        img.onload = () => {
            ctx.save();
            ctx.shadowColor = 'rgba(0, 0, 0, 0.2)';
            ctx.shadowBlur = 15;
            ctx.shadowOffsetX = 0;
            ctx.shadowOffsetY = 4;

            ctx.fillStyle = '#ffffff';
            ctx.beginPath();
            ctx.roundRect(x - 10, y - 10, size + 20, size + 20, 12);
            ctx.fill();
            ctx.restore();

            ctx.drawImage(img, x, y, size, size);
            resolve();
        };
        img.onerror = () => resolve();
        img.src = qrCodeBase64.startsWith('data:') ? qrCodeBase64 : `data:image/png;base64,${qrCodeBase64}`;
    });
}

/**
 * Draw text with proper styling
 */
function drawText(ctx, text, x, y, fontSize, fontWeight, color) {
    ctx.save();
    ctx.font = `${fontWeight} ${fontSize}px Inter, system-ui, sans-serif`;
    ctx.shadowColor = 'rgba(0, 0, 0, 0.5)';
    ctx.shadowBlur = 4;
    ctx.shadowOffsetX = 0;
    ctx.shadowOffsetY = 2;
    ctx.fillStyle = color;
    ctx.fillText(text, x, y);
    ctx.restore();
}

/**
 * Draw logo based on layout
 */
function drawLogo(ctx, layout) {
    if (!currentLogoImg) return 0;

    const getFitDims = (maxW, maxH) => {
        const ratio = Math.min(maxW / currentLogoImg.width, maxH / currentLogoImg.height);
        return { w: currentLogoImg.width * ratio, h: currentLogoImg.height * ratio };
    };

    if (layout === 'classic') {
        const dims = getFitDims(200, 80);
        const x = BG_WIDTH - 60 - dims.w;
        const y = 50;
        ctx.drawImage(currentLogoImg, x, y, dims.w, dims.h);
        return dims.h + 20;
    } else if (layout === 'modern') {
        const dims = getFitDims(300, 100);
        const x = (BG_WIDTH - dims.w) / 2;
        const y = 50;
        ctx.drawImage(currentLogoImg, x, y, dims.w, dims.h);
        return dims.h + 20;
    } else if (layout === 'minimal') {
        const dims = getFitDims(150, 60);
        const x = BG_WIDTH - 50 - dims.w;
        const y = BG_HEIGHT - 50 - 100 - 20 - dims.h;
        ctx.drawImage(currentLogoImg, x, y, dims.w, dims.h);
        return 0;
    } else if (layout === 'corporate') {
        const dims = getFitDims(250, 80);
        const x = BG_WIDTH - 80 - dims.w;
        const y = 40;
        ctx.drawImage(currentLogoImg, x, y, dims.w, dims.h);
        return 0;
    }
    return 0;
}

/**
 * Draw Classic layout
 */
async function drawClassicLayout(ctx, data) {
    drawScrim(ctx, 'classic');
    const logoOffset = drawLogo(ctx, 'classic');
    const textColor = getTextColor(currentBgType, currentBgValue);
    const padding = 60;
    const qrSize = 150;

    drawText(ctx, data.name || 'Your Name', padding, padding + 40, 48, '700', textColor);
    if (data.title) drawText(ctx, data.title, padding, padding + 80, 28, '400', textColor);
    if (data.company) {
        const subColor = textColor === '#ffffff' ? 'rgba(255,255,255,0.8)' : 'rgba(31,41,55,0.8)';
        drawText(ctx, data.company, padding, padding + 115, 24, '400', subColor);
    }

    if (data.qrCode) await drawQrCode(ctx, data.qrCode, BG_WIDTH - padding - qrSize, padding + logoOffset, qrSize);

    const watermarkColor = textColor === '#ffffff' ? 'rgba(255,255,255,0.5)' : 'rgba(31,41,55,0.5)';
    ctx.fillStyle = watermarkColor;
    ctx.font = '500 18px Inter, system-ui, sans-serif';
    ctx.fillText('Made with Vinc', BG_WIDTH - padding - 130, BG_HEIGHT - padding);
}

/**
 * Draw Modern layout
 */
async function drawModernLayout(ctx, data) {
    drawScrim(ctx, 'modern');
    const logoOffset = drawLogo(ctx, 'modern');
    const textColor = getTextColor(currentBgType, currentBgValue);
    const qrSize = 120;
    const centerX = BG_WIDTH / 2;
    const textBaseY = 100 + logoOffset;

    ctx.textAlign = 'center';
    drawText(ctx, data.name || 'Your Name', centerX, textBaseY, 42, '700', textColor);
    const subtitle = [data.title, data.company].filter(Boolean).join(' • ');
    if (subtitle) {
        const subColor = textColor === '#ffffff' ? 'rgba(255,255,255,0.9)' : 'rgba(31,41,55,0.9)';
        drawText(ctx, subtitle, centerX, textBaseY + 45, 24, '400', subColor);
    }
    ctx.textAlign = 'left';

    if (data.qrCode) await drawQrCode(ctx, data.qrCode, BG_WIDTH - 80 - qrSize, BG_HEIGHT - 80 - qrSize, qrSize);

    const watermarkColor = textColor === '#ffffff' ? 'rgba(255,255,255,0.5)' : 'rgba(31,41,55,0.5)';
    ctx.fillStyle = watermarkColor;
    ctx.font = '500 18px Inter, system-ui, sans-serif';
    ctx.fillText('Made with Vinc', 60, BG_HEIGHT - 50);
}

/**
 * Draw Minimal layout
 */
async function drawMinimalLayout(ctx, data) {
    drawScrim(ctx, 'minimal');
    drawLogo(ctx, 'minimal');
    const textColor = getTextColor(currentBgType, currentBgValue);
    const padding = 50;
    const qrSize = 100;

    drawText(ctx, data.name || 'Your Name', padding, BG_HEIGHT - padding - 50, 32, '600', textColor);
    const subtitle = [data.title, data.company].filter(Boolean).join(' | ');
    if (subtitle) {
        const subColor = textColor === '#ffffff' ? 'rgba(255,255,255,0.7)' : 'rgba(31,41,55,0.7)';
        drawText(ctx, subtitle, padding, BG_HEIGHT - padding - 15, 20, '400', subColor);
    }

    if (data.qrCode) await drawQrCode(ctx, data.qrCode, BG_WIDTH - padding - qrSize, BG_HEIGHT - padding - qrSize, qrSize);

    const watermarkColor = textColor === '#ffffff' ? 'rgba(255,255,255,0.3)' : 'rgba(31,41,55,0.3)';
    ctx.fillStyle = watermarkColor;
    ctx.font = '400 14px Inter, system-ui, sans-serif';
    ctx.fillText('Made with Vinc', BG_WIDTH - padding - qrSize, BG_HEIGHT - padding + 20);
}

/**
 * Draw Corporate layout
 */
async function drawCorporateLayout(ctx, data) {
    drawScrim(ctx, 'corporate');
    drawLogo(ctx, 'corporate');
    const textColor = getTextColor(currentBgType, currentBgValue);
    const qrSize = 140;
    const padding = 80;

    drawText(ctx, data.name || 'Your Name', padding, BG_HEIGHT - 110, 44, '700', textColor);
    const subtitle = [data.title, data.company].filter(Boolean).join(' • ');
    if (subtitle) {
        const subColor = textColor === '#ffffff' ? 'rgba(255,255,255,0.9)' : 'rgba(31,41,55,0.9)';
        drawText(ctx, subtitle, padding, BG_HEIGHT - 60, 26, '400', subColor);
    }

    if (data.qrCode) await drawQrCode(ctx, data.qrCode, BG_WIDTH - padding - qrSize, BG_HEIGHT - 165, qrSize);

    const watermarkColor = textColor === '#ffffff' ? 'rgba(255,255,255,0.4)' : 'rgba(31,41,55,0.4)';
    ctx.fillStyle = watermarkColor;
    ctx.font = '400 16px Inter, system-ui, sans-serif';
    ctx.fillText('Made with Vinc', BG_WIDTH - 180, 40);
}

/**
 * Generate the full background canvas
 */
async function generateBackground(flip = true) {
    const canvas = document.createElement('canvas');
    canvas.width = BG_WIDTH;
    canvas.height = BG_HEIGHT;
    const ctx = canvas.getContext('2d');

    // Flip horizontally to compensate for meeting platform mirroring
    // Meeting platforms (Zoom/Teams/Google Meet) flip the image, so we flip it here
    // so it appears correctly when they flip it back
    if (flip) {
        ctx.save();
        ctx.translate(BG_WIDTH, 0);
        ctx.scale(-1, 1);
    }

    drawBackground(ctx, currentBgType, currentBgValue, currentBgImage);

    switch (currentLayout) {
        case 'modern': await drawModernLayout(ctx, vbgData); break;
        case 'minimal': await drawMinimalLayout(ctx, vbgData); break;
        case 'corporate': await drawCorporateLayout(ctx, vbgData); break;
        case 'classic':
        default: await drawClassicLayout(ctx, vbgData); break;
    }

    if (flip) {
        ctx.restore();
    }

    return canvas;
}

/**
 * Update the preview canvas.
 * The preview shows the NON-FLIPPED (human-readable) version so you can see
 * what your background actually looks like. The pre-flipped "for Zoom/Teams"
 * variant is available via the download button. We display the full-size
 * 1920x1080 source canvas directly via CSS at width: 100%, which fills the
 * preview column crisply on any screen without an extra resample step.
 */
async function updateVbgPreview() {
    const previewContainer = document.getElementById('vbg-preview');
    if (!previewContainer) return;

    previewContainer.innerHTML = '<p style="color: #9ca3af; font-style: italic;">Generating preview...</p>';

    try {
        const canvas = await generateBackground(false);
        canvas.style.width = '100%';
        canvas.style.height = 'auto';
        canvas.style.display = 'block';
        canvas.style.borderRadius = '8px';
        canvas.style.boxShadow = '0 4px 12px rgba(0,0,0,0.15)';

        previewContainer.innerHTML = '';
        previewContainer.appendChild(canvas);
    } catch (error) {
        console.error('Error generating preview:', error);
        previewContainer.innerHTML = '<p style="color: #ef4444;">Error generating preview</p>';
    }
}

/**
 * Download the background as PNG
 */
async function downloadVbgBackground() {
    const btn = document.getElementById('download-vbg-btn');
    if (btn) btn.innerHTML = '<i class="fa fa-spinner fa-spin"></i> Generating...';

    try {
        const canvas = await generateBackground(true); // Flipped for meeting platforms
        canvas.toBlob((blob) => {
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `vinc-background-${currentLayout}-${Date.now()}.png`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);

            if (btn) btn.innerHTML = '<i class="fa fa-download"></i> Download Background (1920×1080)';
        }, 'image/png');
    } catch (error) {
        console.error('Error downloading background:', error);
        if (btn) btn.innerHTML = '<i class="fa fa-download"></i> Download Background (1920×1080)';
    }
}

/**
 * Download the background as PNG (non-flipped version)
 */
async function downloadVbgBackgroundNonFlipped() {
    const btn = document.getElementById('download-vbg-btn-nonflipped');
    if (btn) {
        btn.innerHTML = '<i class="fa fa-spinner fa-spin"></i> Generating...';
    }

    try {
        const canvas = await generateBackground(false); // Non-flipped version

        // Convert to blob and download
        canvas.toBlob((blob) => {
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `vinc-background-${currentLayout}-original-${Date.now()}.png`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);

            if (btn) {
                btn.innerHTML = '<i class="fa fa-download"></i> Download Original (1920×1080)';
            }
        }, 'image/png');
    } catch (error) {
        console.error('Error downloading background:', error);
        if (btn) {
            btn.innerHTML = '<i class="fa fa-download"></i> Download Original (1920×1080)';
        }
    }
}

/**
 * Handle image selection
 */
function handleImageSelection(key) {
    if (!BACKGROUND_IMAGES[key]) return;

    const img = new Image();
    img.crossOrigin = "Anonymous";
    img.onload = () => {
        currentBgImage = img;
        currentBgType = 'image';
        currentBgValue = key;
        updateVbgPreview();

        document.querySelectorAll('.vbg-bg-option').forEach(el => el.classList.remove('selected'));
        const option = document.querySelector(`.vbg-image-option[data-image="${key}"]`);
        if (option) option.classList.add('selected');
    };
    img.src = BACKGROUND_IMAGES[key].src;
}

/**
 * Handle custom image upload
 */
function handleCustomImageUpload(file) {
    if (!file || !file.type.startsWith('image/')) {
        alert('Please upload an image file');
        return;
    }

    const reader = new FileReader();
    reader.onload = (e) => {
        const img = new Image();
        img.onload = () => {
            currentBgImage = img;
            currentBgType = 'custom';
            currentBgValue = 'custom_upload';
            updateVbgPreview();

            document.querySelectorAll('.vbg-bg-option').forEach(el => el.classList.remove('selected'));
            const customOption = document.getElementById('vbg-custom-option');
            if (customOption) customOption.classList.add('selected');
        };
        img.src = e.target.result;
    };
    reader.readAsDataURL(file);
}

/**
 * Handle logo upload
 */
function handleLogoUpload(file) {
    if (!file || !file.type.startsWith('image/')) {
        alert('Please upload an image file for the logo.');
        return;
    }

    const reader = new FileReader();
    reader.onload = (e) => {
        const img = new Image();
        img.onload = () => {
            currentLogoImg = img;
            const logoPreviewContainer = document.getElementById('vbg-logo-preview-container');
            const logoPreview = document.getElementById('vbg-logo-preview');
            if (logoPreviewContainer && logoPreview) {
                logoPreview.src = e.target.result;
                logoPreviewContainer.style.display = 'flex';
            }
            updateVbgPreview();
        };
        img.src = e.target.result;
    };
    reader.readAsDataURL(file);
}

/**
 * Setup event listeners
 */
function setupVbgEventListeners() {
    // Layout selector
    const layoutSelect = document.getElementById('vbg-layout-select');
    if (layoutSelect) {
        layoutSelect.addEventListener('change', (e) => {
            currentLayout = e.target.value;
            updateVbgPreview();
        });
    }

    // Color options
    document.querySelectorAll('.vbg-color-option').forEach(el => {
        el.addEventListener('click', () => {
            currentBgType = 'color';
            currentBgValue = el.dataset.color;
            document.querySelectorAll('.vbg-bg-option').forEach(opt => opt.classList.remove('selected'));
            el.classList.add('selected');
            updateVbgPreview();
        });
    });

    // Gradient options
    document.querySelectorAll('.vbg-gradient-option').forEach(el => {
        el.addEventListener('click', () => {
            currentBgType = 'gradient';
            currentBgValue = el.dataset.gradient;
            document.querySelectorAll('.vbg-bg-option').forEach(opt => opt.classList.remove('selected'));
            el.classList.add('selected');
            updateVbgPreview();
        });
    });

    // Image options
    document.querySelectorAll('.vbg-image-option').forEach(el => {
        el.addEventListener('click', () => handleImageSelection(el.dataset.image));
    });

    // Custom background upload
    const customInput = document.getElementById('vbg-custom-input');
    if (customInput) {
        customInput.addEventListener('change', (e) => {
            if (e.target.files && e.target.files[0]) handleCustomImageUpload(e.target.files[0]);
        });
    }

    // Logo upload
    const logoInput = document.getElementById('vbg-logo-input');
    if (logoInput) {
        logoInput.addEventListener('change', (e) => {
            if (e.target.files && e.target.files[0]) handleLogoUpload(e.target.files[0]);
        });
    }

    // Remove logo (delegated)
    document.addEventListener('click', (e) => {
        const btn = e.target.closest('#vbg-remove-logo');
        if (btn) {
            e.preventDefault();
            e.stopPropagation();
            currentLogoImg = null;
            const previewContainer = document.getElementById('vbg-logo-preview-container');
            const input = document.getElementById('vbg-logo-input');
            if (previewContainer) previewContainer.style.display = 'none';
            if (input) input.value = '';
            updateVbgPreview();
        }
    });

    // Download button (flipped for meeting platforms)
    const downloadBtn = document.getElementById('download-vbg-btn');
    if (downloadBtn) {
        downloadBtn.addEventListener('click', (e) => {
            e.preventDefault();
            e.stopPropagation();
            downloadVbgBackground();
        });
    }

    // Download button (non-flipped)
    const downloadBtnNonFlipped = document.getElementById('download-vbg-btn-nonflipped');
    if (downloadBtnNonFlipped) {
        downloadBtnNonFlipped.addEventListener('click', (e) => {
            e.preventDefault();
            e.stopPropagation();
            downloadVbgBackgroundNonFlipped();
        });
    }
}

/**
 * Load dynamic backgrounds from server
 */
async function loadDynamicBackgrounds() {
    try {
        const response = await fetch('/qr_code_odoo/virtual_bg/list', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ jsonrpc: '2.0', method: 'call', params: {} })
        });
        const result = await response.json();

        if (result.result && result.result.backgrounds) {
            const container = document.getElementById('vbg-image-options-container');
            if (!container) return;

            const existingSrcs = new Set(Object.values(BACKGROUND_IMAGES).map(b => b.src));

            result.result.backgrounds.forEach(bg => {
                if (existingSrcs.has(bg.src)) {
                    return;
                }

                // Add to configuration
                BACKGROUND_IMAGES[bg.key] = {
                    name: bg.name,
                    src: bg.src,
                    textColor: bg.textColor || '#ffffff'
                };

                // Create DOM element
                const el = document.createElement('div');
                el.className = 'vbg-bg-option vbg-image-option';
                el.dataset.image = bg.key;
                el.style.width = '80px';
                el.style.height = '45px';
                el.style.borderRadius = '8px';
                el.style.backgroundImage = `url('${bg.src}')`;
                el.style.backgroundPosition = 'center';
                el.style.backgroundSize = 'cover';
                el.style.cursor = 'pointer';
                el.style.border = '3px solid transparent';
                el.title = bg.name;

                // Add click listener to new element
                el.addEventListener('click', () => handleImageSelection(bg.key));

                container.appendChild(el);
            });
        }
    } catch (e) {
        console.error('Error loading dynamic backgrounds:', e);
    }
}

/**
 * Initialize virtual background generator
 */
async function initVirtualBgGenerator() {
    const gallery = document.querySelector('.virtual-bg-gallery');
    if (!gallery || gallery.dataset.initialized) return;

    gallery.dataset.initialized = 'true';
    vbgRecordId = getVbgRecordId();
    console.log('Initializing virtual background generator for record:', vbgRecordId);

    // Load dynamic backgrounds from backend
    await loadDynamicBackgrounds();

    if (vbgRecordId) {
        vbgData = await fetchVbgData(vbgRecordId);
        console.log('Virtual BG Data loaded:', vbgData);
    } else {
        vbgData = {
            name: 'Your Name',
            title: 'Your Title',
            company: 'Your Company',
            qrCode: null,
            brandColor: '#4C75A3',
            vcardUrl: ''
        };
    }

    setupVbgEventListeners();
    updateVbgPreview();
}

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', function () {
    setTimeout(initVirtualBgGenerator, 200);

    if (document.body) {
        const observer = new MutationObserver((mutations) => {
            const gallery = document.querySelector('.virtual-bg-gallery');
            if (gallery && !gallery.dataset.initialized) {
                setTimeout(initVirtualBgGenerator, 100);
            }
        });

        observer.observe(document.body, { childList: true, subtree: true });
    }
});

if (document.readyState === 'complete' || document.readyState === 'interactive') {
    setTimeout(initVirtualBgGenerator, 300);
}
