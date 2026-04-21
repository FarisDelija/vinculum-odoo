/*
 * Vinc /get-started — chapter state machine + field components.
 *
 * Wires the redesigned template together:
 *   - pill stepper (linear forward w/ validation, free backward on completed)
 *   - chapter-scoped validation (required, email format, slug format)
 *   - slug auto-fill from name + availability check (/vcard/check_slug_availability)
 *   - color swatch grid bound to the hidden native <input type="color">
 *   - file dropzone shim over the native file input
 *   - pill toggle switches synced with hidden checkboxes
 *   - conditional reveals for lead form + instant leadback
 *   - dynamic websites/videos with add / remove
 *   - country/state filtering
 *   - QR logo overlay preview
 *   - template card selection
 *   - live /vcard/preview iframe refresh on chapter advance + template change
 *   - localStorage draft save/load
 *   - submit guard (spinner + disable)
 *   - mobile preview pill -> sheet
 */
(function () {
    "use strict";

    function onReady(fn) {
        if (document.readyState === "loading") {
            document.addEventListener("DOMContentLoaded", fn);
        } else {
            fn();
        }
    }

    onReady(function () {
        const root = document.getElementById("gs-root");
        if (!root) { return; }

        const form = document.getElementById("gs-form");
        if (!form) { return; }

        // ----------------------------------------------------------------
        // Preview-section state hoisted to the top so early code paths
        // (swatch init, template picker init, etc.) can call schedulePreviewUpdate
        // without hitting a temporal-dead-zone ReferenceError.
        // ----------------------------------------------------------------
        const previewIframe = document.getElementById("vcard-preview-iframe");
        const previewLoading = document.getElementById("preview-loading");
        const previewIframeMobile = document.getElementById("vcard-preview-iframe-mobile");
        let previewDebounce = null;
        let lastPreviewPayload = null;
        let profileImageDataUrl = null;
        let bannerImageDataUrl = null;

        // ================================================================
        // Chapter state machine
        // ================================================================
        const chapters = Array.from(root.querySelectorAll(".gs-chapter"));
        const stepButtons = Array.from(root.querySelectorAll(".gs-step"));
        const progressTrack = root.querySelector("[data-progress-track]");
        const liveRegion = document.getElementById("gs-live-region");
        const totalChapters = chapters.length;
        let currentChapter = 1;
        let furthestReached = 1;

        function setChapter(n, opts) {
            opts = opts || {};
            if (n < 1 || n > totalChapters) { return; }
            // Can't jump to an upcoming chapter unless forced via Next
            if (n > furthestReached && !opts.force) { return; }

            currentChapter = n;
            chapters.forEach(function (c) {
                c.setAttribute("data-active", String(Number(c.getAttribute("data-chapter")) === n));
            });
            stepButtons.forEach(function (btn) {
                const step = Number(btn.getAttribute("data-step"));
                let state = "upcoming";
                if (step < currentChapter) {
                    state = "completed";
                } else if (step === currentChapter) {
                    state = "active";
                } else if (step <= furthestReached) {
                    state = "completed"; // edited earlier but progress held
                }
                btn.setAttribute("data-state", state);
                btn.setAttribute("aria-current", state === "active" ? "step" : "false");
            });
            if (progressTrack) {
                const pct = ((currentChapter - 1) / (totalChapters - 1)) * 80;
                progressTrack.style.width = pct + "%";
            }
            if (liveRegion) {
                const label = stepButtons[n - 1].querySelector(".gs-step-label");
                liveRegion.textContent = "Chapter " + n + " of " + totalChapters +
                    (label ? ", " + label.textContent.trim() : "");
            }
            // Focus first focusable field in the new chapter
            const active = chapters[n - 1];
            if (active && !opts.suppressFocus) {
                const target = active.querySelector("input:not([type=hidden]):not([type=file]), textarea, select, button");
                if (target) {
                    setTimeout(function () {
                        try { target.focus({ preventScroll: true }); } catch (e) { /* noop */ }
                    }, 80);
                }
            }
            // Scroll to stepper so user sees their progress
            if (!opts.noScroll) {
                window.scrollTo({ top: root.querySelector(".gs-stepper-card").offsetTop - 16, behavior: "smooth" });
            }
            // Refresh preview at chapter advance
            updateTemplatePreview(getSelectedTemplate());
        }

        stepButtons.forEach(function (btn) {
            btn.addEventListener("click", function () {
                const target = Number(btn.getAttribute("data-step"));
                if (btn.getAttribute("data-state") === "completed") {
                    setChapter(target);
                }
            });
        });

        root.addEventListener("click", function (e) {
            const actionBtn = e.target.closest("[data-action]");
            if (!actionBtn || !root.contains(actionBtn)) { return; }
            const action = actionBtn.getAttribute("data-action");
            if (action === "next") {
                if (validateChapter(currentChapter)) {
                    const next = currentChapter + 1;
                    furthestReached = Math.max(furthestReached, next);
                    setChapter(next);
                }
            } else if (action === "back") {
                setChapter(currentChapter - 1);
            }
        });

        // ================================================================
        // Per-chapter validation
        // ================================================================
        function validateChapter(n) {
            const chapter = chapters[n - 1];
            if (!chapter) { return true; }
            let ok = true;
            let firstInvalid = null;

            // Clear previous
            chapter.querySelectorAll(".gs-field.is-invalid").forEach(function (f) {
                f.classList.remove("is-invalid");
            });

            // Required fields
            chapter.querySelectorAll("[required]").forEach(function (el) {
                const v = (el.value || "").trim();
                if (!v) {
                    const field = el.closest(".gs-field");
                    if (field) { field.classList.add("is-invalid"); }
                    ok = false;
                    if (!firstInvalid) { firstInvalid = el; }
                }
            });

            // Email format
            chapter.querySelectorAll('input[type="email"]').forEach(function (el) {
                const v = (el.value || "").trim();
                if (v && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v)) {
                    const field = el.closest(".gs-field");
                    if (field) { field.classList.add("is-invalid"); }
                    ok = false;
                    if (!firstInvalid) { firstInvalid = el; }
                }
            });

            // Slug format
            const slugEl = chapter.querySelector('input[name="website_slug"]');
            if (slugEl) {
                const v = (slugEl.value || "").trim();
                if (v && !/^[a-zA-Z0-9-]+$/.test(v)) {
                    const field = slugEl.closest(".gs-field");
                    if (field) { field.classList.add("is-invalid"); }
                    ok = false;
                    if (!firstInvalid) { firstInvalid = slugEl; }
                }
            }

            // Required-when-enabled
            chapter.querySelectorAll('[data-required-when-enabled="1"]').forEach(function (el) {
                const showForm = document.getElementById("show_form_yes");
                if (showForm && showForm.checked) {
                    if (!(el.value || "").trim()) {
                        const field = el.closest(".gs-field");
                        if (field) { field.classList.add("is-invalid"); }
                        ok = false;
                        if (!firstInvalid) { firstInvalid = el; }
                    }
                }
            });

            // Messaging channels: at least one required when click-to-chat is enabled
            const messagingEnabled = document.getElementById("leadback_enable_messaging_yes");
            if (messagingEnabled && messagingEnabled.checked) {
                const anyChecked = chapter.querySelectorAll('input[name="leadback_channels[]"]:checked').length > 0;
                if (!anyChecked) {
                    const group = chapter.querySelector('[data-check-group="leadback_channels"]');
                    if (group) {
                        group.classList.add("gs-check-row-invalid");
                        ok = false;
                        if (!firstInvalid) { firstInvalid = group; }
                    }
                }
            }

            if (!ok && firstInvalid) {
                setTimeout(function () {
                    firstInvalid.scrollIntoView({ behavior: "smooth", block: "center" });
                    try { firstInvalid.focus({ preventScroll: true }); } catch (e) {}
                }, 50);
            }
            return ok;
        }

        // Clear invalid state + drive preview updates from any input (delegated so
        // it also covers cloned website/video items without re-binding).
        form.addEventListener("input", function (e) {
            const field = e.target.closest(".gs-field");
            if (field && field.classList.contains("is-invalid") && (e.target.value || "").trim()) {
                field.classList.remove("is-invalid");
            }
            // Clear messaging-channel group invalid state when a channel is toggled
            const group = e.target.closest('[data-check-group="leadback_channels"]');
            if (group) { group.classList.remove("gs-check-row-invalid"); }
            saveDraft();
            schedulePreviewUpdate();
        });
        form.addEventListener("change", function () {
            saveDraft();
            schedulePreviewUpdate();
        });

        // ================================================================
        // Color swatch grid
        // ================================================================
        const swatchGrid = root.querySelector("[data-swatch-grid]");
        const nativeColor = document.getElementById("secondary_color");

        function pickSwatch(color, isCustom) {
            if (!nativeColor) { return; }
            nativeColor.value = color;
            if (swatchGrid) {
                swatchGrid.querySelectorAll(".gs-swatch").forEach(function (sw) {
                    sw.setAttribute("data-selected", "false");
                });
                let match = null;
                if (isCustom) {
                    match = swatchGrid.querySelector('[data-custom="true"]');
                    if (match) { match.style.setProperty("--gs-swatch-custom-color", color); }
                } else {
                    match = swatchGrid.querySelector('[data-color="' + color.toLowerCase() + '"]')
                         || swatchGrid.querySelector('[data-color="' + color.toUpperCase() + '"]');
                    if (!match) {
                        // Color not in presets — mark custom swatch as selected & display the color
                        match = swatchGrid.querySelector('[data-custom="true"]');
                        if (match) { match.style.setProperty("--gs-swatch-custom-color", color); }
                    }
                }
                if (match) { match.setAttribute("data-selected", "true"); }
            }
            // Also update default-color on website_color inputs that still hold the previous default
            const websiteColorInputs = document.querySelectorAll('input[name="website_color[]"]');
            websiteColorInputs.forEach(function (input) {
                const prev = (input.getAttribute("data-default-color") || "#2D5BFF").toLowerCase();
                if ((input.value || "").toLowerCase() === prev) {
                    input.value = color;
                }
                input.setAttribute("data-default-color", color);
            });
            schedulePreviewUpdate();
        }

        if (swatchGrid) {
            swatchGrid.addEventListener("click", function (e) {
                const sw = e.target.closest(".gs-swatch");
                if (!sw) { return; }
                if (sw.getAttribute("data-custom") === "true") {
                    // Open native picker
                    if (nativeColor) {
                        // Native color input is visually hidden; temporarily show it to click
                        try {
                            nativeColor.click();
                        } catch (err) {
                            // Fallback: dispatch a click
                            const ev = document.createEvent("MouseEvents");
                            ev.initEvent("click", true, true);
                            nativeColor.dispatchEvent(ev);
                        }
                    }
                } else {
                    pickSwatch(sw.getAttribute("data-color"), false);
                }
            });
        }
        if (nativeColor) {
            nativeColor.addEventListener("input", function () {
                pickSwatch(nativeColor.value, true);
            });
            nativeColor.addEventListener("change", function () {
                pickSwatch(nativeColor.value, true);
            });
        }
        // Init: pick the initial color
        if (nativeColor) {
            pickSwatch(nativeColor.value || "#2D5BFF", false);
        }

        // ================================================================
        // File dropzones
        // ================================================================
        root.querySelectorAll(".gs-drop").forEach(function (drop) {
            const input = drop.querySelector('input[type="file"]');
            const thumb = drop.querySelector(".gs-drop-thumb");
            const filenameEl = drop.querySelector(".gs-drop-filename");
            if (!input) { return; }

            input.addEventListener("change", function () {
                const file = input.files && input.files[0];
                if (!file) {
                    drop.setAttribute("data-state", "empty");
                    return;
                }
                drop.setAttribute("data-state", "filled");
                if (filenameEl) { filenameEl.textContent = file.name; }
                if (file.type && file.type.indexOf("image/") === 0 && thumb) {
                    const reader = new FileReader();
                    reader.onload = function (e) {
                        thumb.style.backgroundImage = 'url("' + e.target.result + '")';
                    };
                    reader.readAsDataURL(file);
                }
                schedulePreviewUpdate();
            });

            // Drag-and-drop visual
            ["dragenter", "dragover"].forEach(function (evt) {
                drop.addEventListener(evt, function (e) {
                    e.preventDefault();
                    drop.setAttribute("data-drag", "true");
                });
            });
            ["dragleave", "drop"].forEach(function (evt) {
                drop.addEventListener(evt, function () {
                    drop.removeAttribute("data-drag");
                });
            });
        });

        // ================================================================
        // Pill toggle switches (linked to hidden checkbox)
        // ================================================================
        function setToggle(toggleBtn, checked) {
            toggleBtn.setAttribute("aria-checked", String(!!checked));
            const targetName = toggleBtn.getAttribute("data-toggle-target");
            const checkbox = document.getElementById(targetName + "_yes");
            if (checkbox) {
                checkbox.checked = !!checked;
                checkbox.dispatchEvent(new Event("change", { bubbles: true }));
            }
            // Reveal conditional block bound to this toggle
            const reveal = root.querySelector('.gs-reveal[data-reveal-for="' + targetName + '"]');
            if (reveal) { reveal.setAttribute("data-revealed", String(!!checked)); }
            // Show_form has its own reveal (#lead_extra_fields)
            if (targetName === "show_form") {
                const leadExtra = document.getElementById("lead_extra_fields");
                if (leadExtra) { leadExtra.setAttribute("data-revealed", String(!!checked)); }
            }
            schedulePreviewUpdate();
        }

        root.querySelectorAll(".gs-toggle").forEach(function (toggleBtn) {
            toggleBtn.addEventListener("click", function () {
                const currently = toggleBtn.getAttribute("aria-checked") === "true";
                setToggle(toggleBtn, !currently);
            });
            toggleBtn.addEventListener("keydown", function (e) {
                if (e.key === " " || e.key === "Enter") {
                    e.preventDefault();
                    toggleBtn.click();
                }
            });
        });

        // Chip checkboxes (leadback channels): the chip is a <label> wrapping the
        // native checkbox, so clicks on the label already toggle it natively.
        // We only sync the data-checked visual attribute on the change event.
        root.querySelectorAll('[data-check-group] .gs-check').forEach(function (chip) {
            const cb = chip.querySelector('input[type="checkbox"]');
            if (!cb) { return; }
            function sync() { chip.setAttribute("data-checked", String(cb.checked)); }
            cb.addEventListener("change", sync);
            sync();
        });

        // ================================================================
        // Websites / videos dynamic
        // ================================================================
        function updateRemoveButtons(container) {
            const items = container.querySelectorAll(".gs-item");
            items.forEach(function (item) {
                const btn = item.querySelector(".gs-item-remove");
                if (!btn) { return; }
                if (items.length > 1) { btn.removeAttribute("hidden"); }
                else { btn.setAttribute("hidden", "hidden"); }
            });
        }

        function cloneItem(container, type) {
            const first = container.querySelector(".gs-item");
            if (!first) { return; }
            const clone = first.cloneNode(true);
            clone.querySelectorAll("input").forEach(function (i) {
                if (i.type !== "color") { i.value = ""; }
                else {
                    const def = nativeColor ? (nativeColor.value || "#2D5BFF") : "#2D5BFF";
                    i.value = def;
                    i.setAttribute("data-default-color", def);
                }
            });
            const removeBtn = clone.querySelector(".gs-item-remove");
            if (removeBtn) { removeBtn.removeAttribute("hidden"); }
            container.appendChild(clone);
            updateRemoveButtons(container);
        }

        const websitesContainer = document.getElementById("websites-container");
        const videosContainer = document.getElementById("videos-container");
        const addWebsiteBtn = document.getElementById("add-website");
        const addVideoBtn = document.getElementById("add-video");

        if (addWebsiteBtn && websitesContainer) {
            addWebsiteBtn.addEventListener("click", function () { cloneItem(websitesContainer, "website"); });
        }
        if (addVideoBtn && videosContainer) {
            addVideoBtn.addEventListener("click", function () { cloneItem(videosContainer, "video"); });
        }
        [websitesContainer, videosContainer].forEach(function (container) {
            if (!container) { return; }
            container.addEventListener("click", function (e) {
                const remove = e.target.closest('[data-action="remove-item"]');
                if (!remove) { return; }
                const item = remove.closest(".gs-item");
                if (!item) { return; }
                item.remove();
                updateRemoveButtons(container);
                schedulePreviewUpdate();
            });
            updateRemoveButtons(container);
        });

        // ================================================================
        // Country / state filtering
        // ================================================================
        const countrySelect = document.getElementById("vcard_country");
        const stateSelect = document.getElementById("vcard_state");
        const stateGroup = document.getElementById("state_group");
        let allStates = [];
        if (stateSelect) {
            allStates = Array.from(stateSelect.options).map(function (opt) {
                return {
                    value: opt.value,
                    text: opt.textContent,
                    countryId: opt.getAttribute("data-country-id"),
                };
            });
        }

        function refreshStates() {
            if (!countrySelect || !stateSelect) { return; }
            const cid = countrySelect.value;
            stateSelect.innerHTML = "";
            const placeholder = document.createElement("option");
            placeholder.value = "";
            placeholder.textContent = "Select a state";
            stateSelect.appendChild(placeholder);
            if (!cid) {
                if (stateGroup) { stateGroup.setAttribute("hidden", "hidden"); }
                return;
            }
            const matching = allStates.filter(function (s) {
                return s.countryId && String(s.countryId) === String(cid) && s.value !== "";
            });
            matching.forEach(function (s) {
                const opt = document.createElement("option");
                opt.value = s.value;
                opt.textContent = s.text;
                stateSelect.appendChild(opt);
            });
            if (stateGroup) {
                if (matching.length > 0) { stateGroup.removeAttribute("hidden"); }
                else { stateGroup.setAttribute("hidden", "hidden"); }
            }
        }
        if (countrySelect) {
            countrySelect.addEventListener("change", function () {
                refreshStates();
                schedulePreviewUpdate();
            });
        }
        if (stateSelect) {
            stateSelect.addEventListener("change", schedulePreviewUpdate);
        }
        refreshStates();

        // ================================================================
        // QR logo overlay
        // ================================================================
        const qrInput = document.getElementById("qr_logo_input");
        const qrOverlay = document.getElementById("qr_logo_overlay_container");
        const qrLogoImg = document.getElementById("qr_logo_image");
        if (qrInput) {
            qrInput.addEventListener("change", function () {
                const file = qrInput.files && qrInput.files[0];
                if (!file) {
                    if (qrOverlay) { qrOverlay.setAttribute("data-shown", "false"); }
                    return;
                }
                const reader = new FileReader();
                reader.onload = function (e) {
                    if (qrLogoImg) { qrLogoImg.src = e.target.result; }
                    if (qrOverlay) { qrOverlay.setAttribute("data-shown", "true"); }
                };
                reader.readAsDataURL(file);
            });
        }

        // ================================================================
        // Template picker
        // ================================================================
        const templateCards = Array.from(root.querySelectorAll(".gs-template"));
        const selectedTemplateInput = document.getElementById("selected_template");

        function selectTemplate(name) {
            if (!name) { return; }
            if (selectedTemplateInput) { selectedTemplateInput.value = name; }
            templateCards.forEach(function (card) {
                card.setAttribute("data-selected", String(card.getAttribute("data-template") === name));
            });
            schedulePreviewUpdate();
        }
        function getSelectedTemplate() {
            return (selectedTemplateInput && selectedTemplateInput.value) || "modern";
        }
        templateCards.forEach(function (card) {
            card.addEventListener("click", function () {
                selectTemplate(card.getAttribute("data-template"));
            });
        });
        selectTemplate(getSelectedTemplate());

        // ================================================================
        // Slug auto-fill + availability check
        // ================================================================
        const slugField = document.getElementById("gs-slug");
        const nameField = document.getElementById("gs-name");
        const slugStatus = root.querySelector("[data-slug-status]");
        const slugEcho = root.querySelector("[data-slug-echo]");
        let slugManuallyEdited = false;
        let slugDebounce = null;

        function generateSlug(name) {
            return (name || "").toLowerCase().trim()
                .replace(/\s+/g, "-")
                .replace(/[^a-z0-9-]/g, "")
                .replace(/-+/g, "-")
                .replace(/^-|-$/g, "");
        }

        function paintSlugStatus(status) {
            if (!slugStatus) { return; }
            if (!status) {
                slugStatus.removeAttribute("data-status");
                slugStatus.textContent = "";
                return;
            }
            slugStatus.setAttribute("data-status", status);
            if (status === "checking") {
                slugStatus.innerHTML = '<span class="gs-slug-spinner" aria-hidden="true"></span>Checking';
            } else if (status === "available") {
                slugStatus.textContent = "Available";
            } else if (status === "taken") {
                slugStatus.textContent = "Taken, try another";
            } else if (status === "error") {
                slugStatus.textContent = "Couldn't check";
            }
        }

        function echoSlug() {
            if (slugEcho && slugField) {
                slugEcho.textContent = (slugField.value || "").trim() || "your-slug";
            }
        }

        async function checkSlug(slug) {
            try {
                const csrfToken = document.querySelector('input[name="csrf_token"]');
                const headers = { "Content-Type": "application/json" };
                if (csrfToken) { headers["X-CSRFToken"] = csrfToken.value; }
                const res = await fetch("/vcard/check_slug_availability", {
                    method: "POST",
                    headers: headers,
                    credentials: "same-origin",
                    body: JSON.stringify({ slug: slug }),
                });
                if (!res.ok) { return { available: false, error: true }; }
                const data = await res.json();
                return data.result ? data.result : data;
            } catch (err) {
                return { available: false, error: true };
            }
        }

        function runSlugCheck() {
            if (!slugField) { return; }
            const v = (slugField.value || "").trim();
            if (!v) { paintSlugStatus(null); return; }
            if (!/^[a-zA-Z0-9-]+$/.test(v)) { paintSlugStatus("error"); return; }
            paintSlugStatus("checking");
            if (slugDebounce) { clearTimeout(slugDebounce); }
            slugDebounce = setTimeout(async function () {
                const result = await checkSlug(v);
                if (result && result.error) { paintSlugStatus("error"); return; }
                if (result && result.available === true) { paintSlugStatus("available"); }
                else { paintSlugStatus("taken"); }
            }, 400);
        }

        if (slugField) {
            slugField.addEventListener("input", function () {
                slugField.value = slugField.value.toLowerCase().replace(/[^a-z0-9-]/g, "");
                slugManuallyEdited = true;
                echoSlug();
                runSlugCheck();
            });
        }

        async function autoFillSlug() {
            if (!nameField || !slugField) { return; }
            if (slugManuallyEdited) { return; }
            const base = generateSlug(nameField.value);
            if (!base) { return; }
            // If slug already matches the generated name, leave it
            if (slugField.value && slugField.value !== base && !slugField.value.startsWith(base + "-")) { return; }
            paintSlugStatus("checking");
            const result = await checkSlug(base);
            if (result && result.available === true) {
                slugField.value = base;
            } else if (result && result.suggestion) {
                slugField.value = result.suggestion;
            } else {
                slugField.value = base;
            }
            echoSlug();
            runSlugCheck();
        }

        if (nameField) {
            nameField.addEventListener("input", function () {
                autoFillSlug();
            });
        }

        // ================================================================
        // Auto-fill mailing list name from person name
        // ================================================================
        const mailingListInput = document.getElementById("gs-list");
        function autoFillMailingList() {
            if (!mailingListInput || !nameField) { return; }
            const n = (nameField.value || "").trim();
            if (n && !(mailingListInput.value || "").trim()) {
                mailingListInput.value = n + "'s List";
            }
        }
        if (nameField && mailingListInput) {
            nameField.addEventListener("change", autoFillMailingList);
            nameField.addEventListener("blur", autoFillMailingList);
        }

        // ================================================================
        // Live preview (iframe) — matches old /vcard/preview contract
        // State vars (previewIframe, previewDebounce, etc.) are hoisted above.
        // ================================================================
        const profilePhotoInput = document.getElementById("profile_photo_input");
        const bannerImageInput = document.getElementById("banner_image_input");
        if (profilePhotoInput) {
            profilePhotoInput.addEventListener("change", function (e) {
                const file = e.target.files && e.target.files[0];
                if (!file) { return; }
                const reader = new FileReader();
                reader.onload = function (ev) {
                    profileImageDataUrl = ev.target.result;
                    schedulePreviewUpdate();
                };
                reader.readAsDataURL(file);
            });
        }
        if (bannerImageInput) {
            bannerImageInput.addEventListener("change", function (e) {
                const file = e.target.files && e.target.files[0];
                if (!file) { return; }
                const reader = new FileReader();
                reader.onload = function (ev) {
                    bannerImageDataUrl = ev.target.result;
                    schedulePreviewUpdate();
                };
                reader.readAsDataURL(file);
            });
        }

        function formValue(name) {
            const el = form.querySelector('[name="' + name + '"]');
            return el ? (el.value || "") : "";
        }
        function formValues(name) {
            return Array.from(form.querySelectorAll('[name="' + name + '"]'))
                .map(function (el) { return el.value || ""; });
        }
        function formChecked(name) {
            return Array.from(form.querySelectorAll('[name="' + name + '"]:checked'))
                .map(function (el) { return el.value; });
        }

        function schedulePreviewUpdate() {
            if (previewDebounce) { clearTimeout(previewDebounce); }
            previewDebounce = setTimeout(updateTemplatePreview, 500);
        }

        function updateTemplatePreview(templateOverride) {
            if (!previewIframe) { return; }
            if (previewLoading) { previewLoading.setAttribute("data-shown", "true"); }

            const data = {
                name: formValue("name") || "Your Name",
                company_name: formValue("company_name") || "",
                function: formValue("function") || "",
                email: formValue("email") || "email@example.com",
                phone: formValue("phone") || "",
                mobile: formValue("mobile") || "",
                about: formValue("about") || "",
                primary_color: formValue("primary_color") || "#ffffff",
                secondary_color: formValue("secondary_color") || "#2D5BFF",
                website_template: templateOverride || getSelectedTemplate(),
                linkedin_url: formValue("linkedin_url") || "",
                twitter_url: formValue("twitter_url") || "",
                instagram_url: formValue("instagram_url") || "",
                facebook_url: formValue("facebook_url") || "",
                youtube_url: formValue("youtube_url") || "",
                whatsapp_url: formValue("whatsapp_url") || "",
                linkedin_url_company: formValue("linkedin_url_company") || "",
                twitter_url_company: formValue("twitter_url_company") || "",
                instagram_url_company: formValue("instagram_url_company") || "",
                facebook_url_company: formValue("facebook_url_company") || "",
                calendly_url: formValue("calendly_url") || "",
                street: formValue("street") || "",
                street2: formValue("street2") || "",
                city: formValue("city") || "",
                zip: formValue("zip") || "",
                country_id: formValue("country_id") || "",
                state_id: formValue("state_id") || "",
                show_form: !!(document.getElementById("show_form_yes") && document.getElementById("show_form_yes").checked),
                show_reviews: !!(document.getElementById("show_reviews_yes") && document.getElementById("show_reviews_yes").checked),
                mailing_list_name: formValue("mailing_list_name") || "Leads",
                lead_button_label: formValue("lead_button_label") || "Get In Touch",
                form_thank_you_message: formValue("form_thank_you_message") || "",
                website_url: formValues("website_url[]"),
                website_name: formValues("website_name[]"),
                website_color: formValues("website_color[]"),
                video_url: formValues("video_url[]"),
                video_name: formValues("video_name[]"),
                leadback_channels: formChecked("leadback_channels[]"),
            };

            if (profileImageDataUrl) {
                const idx = profileImageDataUrl.indexOf(",");
                data.image_base64 = idx >= 0 ? profileImageDataUrl.slice(idx + 1) : profileImageDataUrl;
            }
            if (bannerImageDataUrl) {
                const idx = bannerImageDataUrl.indexOf(",");
                data.banner_image_base64 = idx >= 0 ? bannerImageDataUrl.slice(idx + 1) : bannerImageDataUrl;
            }

            const payloadStr = JSON.stringify(data);
            if (payloadStr === lastPreviewPayload) {
                if (previewLoading) { previewLoading.setAttribute("data-shown", "false"); }
                return;
            }
            lastPreviewPayload = payloadStr;

            fetch("/vcard/preview", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: payloadStr,
            }).then(function (r) {
                if (!r.ok) { throw new Error("HTTP " + r.status); }
                return r.json();
            }).then(function (response) {
                const result = response.result || response;
                if (result && (result.success === true || result.success === "true")) {
                    const url = result.preview_url;
                    previewIframe.onload = function () {
                        if (previewLoading) { previewLoading.setAttribute("data-shown", "false"); }
                        disarmIframeLinks(previewIframe);
                    };
                    previewIframe.src = url;
                    if (previewIframeMobile) {
                        previewIframeMobile.onload = function () { disarmIframeLinks(previewIframeMobile); };
                        previewIframeMobile.src = url;
                    }
                } else {
                    if (previewLoading) { previewLoading.setAttribute("data-shown", "false"); }
                }
            }).catch(function () {
                if (previewLoading) { previewLoading.setAttribute("data-shown", "false"); }
            });
        }

        // Preview iframe is same-origin, so we can hook into the loaded document
        // and short-circuit any navigation or form submits while keeping scroll/
        // hover behaviour intact.
        function disarmIframeLinks(iframe) {
            try {
                const doc = iframe.contentDocument;
                if (!doc) { return; }
                doc.addEventListener("click", function (e) {
                    const a = e.target.closest && e.target.closest("a, button, [role='button']");
                    if (a) { e.preventDefault(); e.stopPropagation(); }
                }, true);
                doc.addEventListener("submit", function (e) {
                    e.preventDefault(); e.stopPropagation();
                }, true);
            } catch (err) { /* cross-origin — nothing we can do */ }
        }

        // Initial preview
        setTimeout(function () { updateTemplatePreview(getSelectedTemplate()); }, 400);

        // Broad input listener for any field that affects preview
        const previewTriggers = ["name", "company_name", "function", "email", "phone", "mobile",
            "about", "calendly_url", "website_slug", "linkedin_url", "twitter_url", "instagram_url",
            "facebook_url", "youtube_url", "whatsapp_url", "street", "street2", "city", "zip",
            "lead_button_label", "form_thank_you_message", "mailing_list_name"];
        previewTriggers.forEach(function (n) {
            const el = form.querySelector('[name="' + n + '"]');
            if (el) { el.addEventListener("input", schedulePreviewUpdate); }
        });

        if (slugField) { slugField.addEventListener("input", echoSlug); }
        echoSlug();

        // ================================================================
        // Mobile preview sheet
        // ================================================================
        const pillBtn = document.getElementById("gs-preview-pill-btn");
        const sheet = document.getElementById("gs-preview-sheet");
        function openSheet() {
            if (!sheet) { return; }
            sheet.setAttribute("data-open", "true");
            sheet.setAttribute("aria-hidden", "false");
            document.body.classList.add("gs-sheet-open");
            // Sync iframe src to current preview
            if (previewIframe && previewIframeMobile && previewIframe.src && previewIframe.src !== "about:blank") {
                if (previewIframeMobile.src !== previewIframe.src) {
                    previewIframeMobile.src = previewIframe.src;
                }
            }
        }
        function closeSheet() {
            if (!sheet) { return; }
            sheet.setAttribute("data-open", "false");
            sheet.setAttribute("aria-hidden", "true");
            document.body.classList.remove("gs-sheet-open");
        }
        if (pillBtn) { pillBtn.addEventListener("click", openSheet); }
        if (sheet) {
            sheet.addEventListener("click", function (e) {
                if (e.target === sheet) { closeSheet(); return; }
                if (e.target.closest('[data-action="close-sheet"]')) { closeSheet(); }
            });
        }
        document.addEventListener("keydown", function (e) {
            if (e.key === "Escape" && sheet && sheet.getAttribute("data-open") === "true") {
                closeSheet();
            }
        });

        // ================================================================
        // localStorage draft save / load
        // ================================================================
        const DRAFT_KEY = "vcard_form_data";
        let saveTimer = null;

        function saveDraft() {
            if (saveTimer) { clearTimeout(saveTimer); }
            saveTimer = setTimeout(function () {
                try {
                    const data = new FormData(form);
                    const out = {};
                    for (const [k, v] of data.entries()) {
                        if (k === "csrf_token") { continue; }
                        if (k === "image_url" || k === "banner_image" || k === "qr_logo") { continue; }
                        if (Array.isArray(out[k])) { out[k].push(v); }
                        else if (k in out) { out[k] = [out[k], v]; }
                        else { out[k] = v; }
                    }
                    localStorage.setItem(DRAFT_KEY, JSON.stringify(out));
                } catch (err) { /* ignore quota errors */ }
            }, 400);
        }

        function loadDraft() {
            try {
                const raw = localStorage.getItem(DRAFT_KEY);
                if (!raw) { return; }
                const data = JSON.parse(raw);
                Object.keys(data).forEach(function (k) {
                    const els = form.querySelectorAll('[name="' + k + '"]');
                    if (!els.length) { return; }
                    if (els[0].type === "file") { return; }
                    if (els[0].type === "checkbox") {
                        const val = data[k];
                        els.forEach(function (el) {
                            if (Array.isArray(val)) {
                                el.checked = val.indexOf(el.value) !== -1;
                            } else {
                                el.checked = el.value === val || val === "yes";
                            }
                            el.dispatchEvent(new Event("change", { bubbles: true }));
                        });
                        return;
                    }
                    if (Array.isArray(data[k])) {
                        data[k].forEach(function (val, i) {
                            if (els[i]) { els[i].value = val; }
                        });
                    } else {
                        els[0].value = data[k];
                    }
                });
                // Sync toggle visuals from checkbox state
                root.querySelectorAll(".gs-toggle").forEach(function (t) {
                    const targetName = t.getAttribute("data-toggle-target");
                    const cb = document.getElementById(targetName + "_yes");
                    if (cb) {
                        t.setAttribute("aria-checked", String(cb.checked));
                        const reveal = root.querySelector('.gs-reveal[data-reveal-for="' + targetName + '"]');
                        if (reveal) { reveal.setAttribute("data-revealed", String(cb.checked)); }
                        if (targetName === "show_form") {
                            const le = document.getElementById("lead_extra_fields");
                            if (le) { le.setAttribute("data-revealed", String(cb.checked)); }
                        }
                    }
                });
                // Re-sync check chips
                root.querySelectorAll('[data-check-group] .gs-check').forEach(function (chip) {
                    const cb = chip.querySelector('input[type="checkbox"]');
                    chip.setAttribute("data-checked", String(cb && cb.checked));
                });
                // Re-sync swatch selection from native color
                if (nativeColor) { pickSwatch(nativeColor.value, false); }
                refreshStates();
            } catch (err) { /* ignore parse errors */ }
        }
        loadDraft();

        // ================================================================
        // Submit guard
        // ================================================================
        form.addEventListener("submit", function (e) {
            // Validate all chapters
            let ok = true;
            for (let i = 1; i <= totalChapters; i++) {
                if (!validateChapter(i)) {
                    ok = false;
                    furthestReached = Math.max(furthestReached, i);
                    setChapter(i, { force: true });
                    break;
                }
            }
            if (!ok) {
                e.preventDefault();
                return;
            }
            const submitBtn = document.getElementById("gs-submit");
            if (submitBtn) {
                submitBtn.setAttribute("data-loading", "true");
                submitBtn.disabled = true;
                const label = submitBtn.querySelector(".gs-btn-label");
                if (label) { label.textContent = "Creating your card…"; }
            }
            try { localStorage.removeItem(DRAFT_KEY); } catch (err) {}
        });

        // If the server prefilled the name, trigger slug + mailing-list autofill on load.
        if (nameField && nameField.value && nameField.value.trim()) {
            setTimeout(function () {
                autoFillMailingList();
                autoFillSlug();
            }, 300);
        }

        // ================================================================
        // Init
        // ================================================================
        setChapter(1, { noScroll: true, suppressFocus: true });
    });
})();
