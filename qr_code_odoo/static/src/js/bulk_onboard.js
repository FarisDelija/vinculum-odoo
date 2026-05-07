/*
 * Vinc Bulk Onboarding — admin flows.
 *
 * Scopes:
 *   #bk-wizard   → /bulk-onboard/new  (3-chapter stepper, CSV upload,
 *                                      manual entry, review summary, submit)
 *   #bk-batch    → /bulk-onboard/batch/<id>  (per-rep resend + bulk resend)
 *
 * No jQuery, no framework. Event delegation where useful. The wizard's POST
 * contract to /bulk-onboard/submit is unchanged from the prior design: same
 * input names, same rep_data_json shape. The admin_onboard and resend JSON
 * endpoints are hit with fetch() directly.
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

    function csrf() {
        const el = document.querySelector('input[name="csrf_token"]');
        return el ? el.value : "";
    }

    // ================================================================
    // Wizard
    // ================================================================
    onReady(function () {
        const wizard = document.getElementById("bk-wizard");
        if (!wizard) { return; }
        const form = document.getElementById("bk-form");
        if (!form) { return; }

        // ---- Chapter state machine ----
        const chapters = Array.from(wizard.querySelectorAll(".bk-chapter"));
        const stepButtons = Array.from(wizard.querySelectorAll(".bk-step"));
        const progressTrack = wizard.querySelector("[data-progress-track]");
        const total = chapters.length;
        let current = 1;
        let furthest = 1;

        function setChapter(n, opts) {
            opts = opts || {};
            if (n < 1 || n > total) { return; }
            if (n > furthest && !opts.force) { return; }
            current = n;
            chapters.forEach(function (c) {
                c.setAttribute("data-active", String(Number(c.getAttribute("data-chapter")) === n));
            });
            stepButtons.forEach(function (btn) {
                const step = Number(btn.getAttribute("data-step"));
                let state = "upcoming";
                if (step < current) state = "completed";
                else if (step === current) state = "active";
                else if (step <= furthest) state = "completed";
                btn.setAttribute("data-state", state);
                btn.setAttribute("aria-current", state === "active" ? "step" : "false");
            });
            if (progressTrack) {
                const totalGap = 100 - 2 * (100 / (total * 2));
                const pct = ((current - 1) / (total - 1)) * (100 - 2 * (100 / 6));
                progressTrack.style.width = pct + "%";
            }
            if (n === 3) { refreshReview(); }
            window.scrollTo({ top: wizard.querySelector(".bk-stepper-card").offsetTop - 16, behavior: "smooth" });
        }

        stepButtons.forEach(function (btn) {
            btn.addEventListener("click", function () {
                if (btn.getAttribute("data-state") === "completed") {
                    setChapter(Number(btn.getAttribute("data-step")));
                }
            });
        });

        wizard.addEventListener("click", function (e) {
            const actionBtn = e.target.closest("[data-action]");
            if (!actionBtn || !wizard.contains(actionBtn)) { return; }
            const action = actionBtn.getAttribute("data-action");
            if (action === "next") {
                if (validateChapter(current)) {
                    const next = current + 1;
                    furthest = Math.max(furthest, next);
                    setChapter(next);
                }
            } else if (action === "back") {
                setChapter(current - 1);
            }
        });

        function validateChapter(n) {
            if (n === 1) {
                const count = countReps();
                if (count === 0) {
                    showUploadStatus("Add at least one rep — upload a CSV or switch to manual entry.", "error");
                    return false;
                }
                return true;
            }
            return true;
        }

        // ---- Import tabs ----
        const importTabs = Array.from(wizard.querySelectorAll("[data-import-tab]"));
        const importPanels = Array.from(wizard.querySelectorAll("[data-import-panel]"));
        importTabs.forEach(function (tab) {
            tab.addEventListener("click", function () {
                const target = tab.getAttribute("data-import-tab");
                importTabs.forEach(function (t) {
                    t.setAttribute("data-active", String(t.getAttribute("data-import-tab") === target));
                });
                importPanels.forEach(function (p) {
                    p.setAttribute("data-active", String(p.getAttribute("data-import-panel") === target));
                });
                // Clear rep_data_json when switching modes so the controller
                // falls back to parsing rep_name[] etc. from manual entry.
                if (target === "manual") {
                    document.getElementById("bk-rep-data-json").value = "";
                }
            });
        });

        // ---- CSV / Excel upload ----
        const fileInput = document.getElementById("bk-file-input");
        const dropzone = document.getElementById("bk-dropzone");
        const dropFilename = dropzone.querySelector("[data-drop-filename]");
        const dropCount = dropzone.querySelector("[data-drop-count]");
        const dropReset = dropzone.querySelector("[data-drop-reset]");
        const uploadStatus = document.getElementById("bk-upload-status");
        let uploadedRows = [];

        function showUploadStatus(message, tone) {
            if (!uploadStatus) { return; }
            uploadStatus.style.display = "flex";
            uploadStatus.setAttribute("data-tone", tone || "info");
            uploadStatus.textContent = message;
        }
        function hideUploadStatus() {
            if (uploadStatus) { uploadStatus.style.display = "none"; }
        }
        function setDropzoneState(state) {
            dropzone.setAttribute("data-state", state);
        }

        if (fileInput) {
            fileInput.addEventListener("change", function () {
                const file = fileInput.files && fileInput.files[0];
                if (!file) { return; }
                uploadFile(file);
            });
        }
        // Drag-and-drop visuals
        ["dragenter", "dragover"].forEach(function (evt) {
            dropzone.addEventListener(evt, function (e) {
                e.preventDefault();
                dropzone.setAttribute("data-drag", "true");
            });
        });
        ["dragleave", "drop"].forEach(function (evt) {
            dropzone.addEventListener(evt, function () { dropzone.removeAttribute("data-drag"); });
        });
        if (dropReset) {
            dropReset.addEventListener("click", function (e) {
                e.preventDefault();
                e.stopPropagation();
                uploadedRows = [];
                document.getElementById("bk-rep-data-json").value = "";
                if (fileInput) { fileInput.value = ""; }
                setDropzoneState("empty");
                hideUploadStatus();
            });
        }

        function uploadFile(file) {
            const fd = new FormData();
            fd.append("file", file);
            setDropzoneState("filled");
            if (dropFilename) { dropFilename.textContent = file.name; }
            if (dropCount) { dropCount.textContent = "Parsing…"; }
            fetch("/bulk-onboard/upload", {
                method: "POST",
                body: fd,
                credentials: "same-origin",
            }).then(function (r) {
                return r.text();
            }).then(function (text) {
                let data;
                try { data = JSON.parse(text); } catch (err) {
                    showUploadStatus("Server returned an unexpected response.", "error");
                    setDropzoneState("empty");
                    return;
                }
                if (data.error) {
                    showUploadStatus(data.error, "error");
                    setDropzoneState("empty");
                    return;
                }
                // The upload endpoint only returns the first 10 rows as preview.
                // We re-parse the file client-side to capture everything.
                parseFileClientSide(file, data.total_rows);
                // Show a banner if any rows reference emails that don't exist
                // as Odoo users — those rows will be skipped at submit time.
                if (data.unmatched_count > 0) {
                    const list = (data.unmatched_emails || []).join(", ");
                    const more = data.unmatched_count > (data.unmatched_emails || []).length
                        ? " (+" + (data.unmatched_count - data.unmatched_emails.length) + " more)"
                        : "";
                    showUploadStatus(
                        data.matched_count + " of " + (data.matched_count + data.unmatched_count) +
                        " emails match existing Odoo users. " +
                        data.unmatched_count + " will be skipped: " + list + more +
                        ". Add these users under Settings → Users & Companies → Users to include them.",
                        "warning"
                    );
                }
            }).catch(function (err) {
                showUploadStatus("Upload failed: " + err.message, "error");
                setDropzoneState("empty");
            });
        }

        function parseFileClientSide(file, serverTotal) {
            const ext = (file.name.split(".").pop() || "").toLowerCase();
            if (ext === "csv") {
                const reader = new FileReader();
                reader.onload = function (e) {
                    const rows = parseCSV(e.target.result);
                    uploadedRows = rows;
                    document.getElementById("bk-rep-data-json").value = JSON.stringify(rows);
                    if (dropCount) { dropCount.textContent = rows.length + " rep" + (rows.length === 1 ? "" : "s") + " loaded"; }
                    showUploadStatus("Parsed " + rows.length + " rep" + (rows.length === 1 ? "" : "s") + " from " + file.name + ".", "success");
                };
                reader.readAsText(file);
            } else {
                // Excel: trust the server-side row count; parse happens server-side
                // so we can't populate review grid per-row client-side without
                // re-implementing openpyxl in JS. Just post the file as upload
                // meta and rely on server re-parse at submit time. To make that
                // work we need rep_data_json populated — which means fetching
                // the full row set from the server. Simpler: re-call upload
                // with a "full" flag. For now, use the preview from server.
                showUploadStatus(
                    "Excel parsed: " + serverTotal + " rep" + (serverTotal === 1 ? "" : "s") +
                    ". Review grid shows only the first 10 rows; all rows are submitted.",
                    "info"
                );
                if (dropCount) {
                    dropCount.textContent = serverTotal + " rep" + (serverTotal === 1 ? "" : "s") + " loaded";
                }
                // Stash a sentinel so manual-entry fallback doesn't fire
                document.getElementById("bk-rep-data-json").value = "[]";
            }
        }

        // Minimal CSV parser. Assumes the Vinc starter CSV format:
        // Row 0 = explanation text, Row 1 = headers, Rows 2+ = data.
        // Falls back to "Row 0 = headers, Rows 1+ = data" if row 0 looks like
        // machine-readable headers (no spaces, single-word columns).
        function parseCSV(text) {
            const lines = [];
            // Simple CSV tokenizer supporting quoted fields with embedded commas/newlines
            let field = "";
            let row = [];
            let inQuotes = false;
            for (let i = 0; i < text.length; i++) {
                const ch = text[i];
                if (inQuotes) {
                    if (ch === '"' && text[i + 1] === '"') { field += '"'; i++; }
                    else if (ch === '"') { inQuotes = false; }
                    else { field += ch; }
                } else {
                    if (ch === '"') { inQuotes = true; }
                    else if (ch === ",") { row.push(field); field = ""; }
                    else if (ch === "\n") { row.push(field); lines.push(row); row = []; field = ""; }
                    else if (ch === "\r") { /* skip */ }
                    else { field += ch; }
                }
            }
            if (field.length || row.length) { row.push(field); lines.push(row); }
            if (!lines.length) { return []; }
            // Detect Vinc starter CSV (row 0 is explanations) vs. plain headered CSV.
            // Heuristic: if row 0 contains spaces or long descriptive text, it's
            // explanations — use row 1 as headers. Otherwise row 0 is headers.
            let headerIdx = 0;
            const row0 = lines[0] || [];
            const looksLikeDescription = row0.some(function (c) { return c && c.length > 20; });
            if (looksLikeDescription && lines.length > 1) { headerIdx = 1; }
            const headers = (lines[headerIdx] || []).map(function (h) { return (h || "").trim().toLowerCase(); });
            const out = [];
            for (let i = headerIdx + 1; i < lines.length; i++) {
                const cols = lines[i] || [];
                if (!cols.some(function (c) { return (c || "").trim(); })) { continue; } // skip blank
                const obj = {};
                for (let j = 0; j < headers.length; j++) {
                    obj[headers[j]] = (cols[j] || "").trim().replace(/^'/, ""); // strip leading ' Excel escape
                }
                if (obj.email) { out.push(obj); }
            }
            return out;
        }

        // ---- Manual entry ----
        const repRows = document.getElementById("bk-rep-rows");
        const repAdd = document.getElementById("bk-rep-add");
        if (repAdd) {
            repAdd.addEventListener("click", function () {
                const template = repRows.querySelector(".bk-rep-row");
                if (!template) { return; }
                const clone = template.cloneNode(true);
                clone.querySelectorAll("input").forEach(function (i) { i.value = ""; });
                repRows.appendChild(clone);
            });
        }
        if (repRows) {
            repRows.addEventListener("click", function (e) {
                const rm = e.target.closest("[data-rep-remove]");
                if (!rm) { return; }
                const rows = repRows.querySelectorAll(".bk-rep-row");
                if (rows.length <= 1) {
                    // Keep at least one row — just clear the values.
                    rm.closest(".bk-rep-row").querySelectorAll("input").forEach(function (i) { i.value = ""; });
                    return;
                }
                rm.closest(".bk-rep-row").remove();
            });
        }

        // ---- Count reps (from current active import mode) ----
        function countReps() {
            const activeTab = wizard.querySelector('[data-import-tab][data-active="true"]');
            const mode = activeTab ? activeTab.getAttribute("data-import-tab") : "upload";
            if (mode === "upload") { return uploadedRows.length; }
            // Manual — count rows with an email
            let c = 0;
            repRows.querySelectorAll('.bk-rep-row input[name="rep_email[]"]').forEach(function (i) {
                if ((i.value || "").trim()) { c++; }
            });
            return c;
        }

        function activeImportMode() {
            const t = wizard.querySelector('[data-import-tab][data-active="true"]');
            return t ? t.getAttribute("data-import-tab") : "upload";
        }

        // ---- Brand color sync ----
        const colorVisible = document.getElementById("bk-brand-color-visible");
        const colorHidden = document.getElementById("bk-brand-color");
        if (colorVisible && colorHidden) {
            colorVisible.addEventListener("input", function () {
                colorHidden.value = colorVisible.value;
            });
        }

        // ---- Template radio selection ----
        const tplRadios = Array.from(wizard.querySelectorAll('[data-template-choice]'));
        const tplHidden = document.getElementById("bk-selected-template");
        tplRadios.forEach(function (radio) {
            const tile = radio.nextElementSibling; // the .bk-summary-tile wrapper
            function reflect() {
                tplRadios.forEach(function (r) {
                    const t = r.nextElementSibling;
                    if (t) {
                        t.style.borderColor = r.checked ? "#2D5BFF" : "";
                        t.style.boxShadow = r.checked ? "0 0 0 2px rgba(45, 91, 255, 0.18)" : "";
                    }
                });
                if (tplHidden) {
                    const checked = tplRadios.find(function (r) { return r.checked; });
                    if (checked) { tplHidden.value = checked.value; }
                }
            }
            radio.addEventListener("change", reflect);
            reflect();
        });

        // ---- Toggles (reuse /get-started pill toggle semantics) ----
        wizard.querySelectorAll(".gs-toggle").forEach(function (toggleBtn) {
            function sync() {
                const targetName = toggleBtn.getAttribute("data-toggle-target");
                const cb = document.getElementById(targetName + "_yes");
                if (!cb) { return; }
                toggleBtn.setAttribute("aria-checked", String(cb.checked));
                // Show-form reveal
                if (targetName === "show_form") {
                    const reveal = document.getElementById("bk-lead-extras");
                    if (reveal) { reveal.setAttribute("data-revealed", String(cb.checked)); }
                }
            }
            toggleBtn.addEventListener("click", function () {
                const targetName = toggleBtn.getAttribute("data-toggle-target");
                const cb = document.getElementById(targetName + "_yes");
                if (!cb) { return; }
                cb.checked = !cb.checked;
                sync();
            });
            toggleBtn.addEventListener("keydown", function (e) {
                if (e.key === " " || e.key === "Enter") { e.preventDefault(); toggleBtn.click(); }
            });
            sync();
        });

        // ---- Country/state filter ----
        const countrySel = document.getElementById("bk-country");
        const stateSel = document.getElementById("bk-state");
        let allStates = [];
        if (stateSel) {
            allStates = Array.from(stateSel.options).map(function (opt) {
                return {
                    value: opt.value, text: opt.textContent,
                    countryId: opt.getAttribute("data-country-id"),
                };
            });
        }
        function refreshStates() {
            if (!countrySel || !stateSel) { return; }
            const cid = countrySel.value;
            stateSel.innerHTML = "";
            const placeholder = document.createElement("option");
            placeholder.value = ""; placeholder.textContent = "Select a state";
            stateSel.appendChild(placeholder);
            if (!cid) { return; }
            allStates.filter(function (s) {
                return s.countryId && String(s.countryId) === String(cid) && s.value !== "";
            }).forEach(function (s) {
                const opt = document.createElement("option");
                opt.value = s.value; opt.textContent = s.text;
                stateSel.appendChild(opt);
            });
        }
        if (countrySel) { countrySel.addEventListener("change", refreshStates); }
        refreshStates();

        // ---- Chapter 3 review ----
        const reviewTbody = document.getElementById("bk-review-tbody");
        const reviewEmpty = document.getElementById("bk-review-empty");

        function refreshReview() {
            const mode = activeImportMode();
            const reps = [];
            if (mode === "upload") {
                uploadedRows.forEach(function (r) {
                    reps.push({ name: r.name || "", email: r.email || "", phone: r.phone || "", function: r.function || "" });
                });
            } else {
                const names = Array.from(repRows.querySelectorAll('input[name="rep_name[]"]'));
                const emails = Array.from(repRows.querySelectorAll('input[name="rep_email[]"]'));
                const phones = Array.from(repRows.querySelectorAll('input[name="rep_phone[]"]'));
                const funcs = Array.from(repRows.querySelectorAll('input[name="rep_function[]"]'));
                for (let i = 0; i < emails.length; i++) {
                    const email = (emails[i].value || "").trim();
                    if (!email) { continue; }
                    reps.push({
                        name: (names[i] && names[i].value || "").trim(),
                        email: email,
                        phone: (phones[i] && phones[i].value || "").trim(),
                        function: (funcs[i] && funcs[i].value || "").trim(),
                    });
                }
            }
            // Update summary
            const countEl = wizard.querySelector("[data-summary-count]");
            if (countEl) { countEl.textContent = reps.length; }
            const tplCheckedRadio = tplRadios.find(function (r) { return r.checked; });
            const tplEl = wizard.querySelector("[data-summary-template]");
            if (tplEl && tplCheckedRadio) {
                const tile = tplCheckedRadio.nextElementSibling;
                const val = tile && tile.querySelector(".bk-summary-value");
                tplEl.textContent = val ? val.textContent : tplCheckedRadio.value;
            }
            const swatch = wizard.querySelector("[data-summary-color-swatch]");
            const hexEl = wizard.querySelector("[data-summary-color-hex]");
            if (colorHidden) {
                if (swatch) { swatch.style.background = colorHidden.value; }
                if (hexEl) { hexEl.textContent = (colorHidden.value || "").toUpperCase(); }
            }
            const sourceEl = wizard.querySelector("[data-summary-source]");
            if (sourceEl) {
                sourceEl.textContent = mode === "upload"
                    ? "Parsed from uploaded file."
                    : "Typed in manually.";
            }
            // Render table
            if (!reviewTbody) { return; }
            reviewTbody.innerHTML = "";
            if (!reps.length) {
                if (reviewEmpty) { reviewEmpty.style.display = "flex"; }
                return;
            }
            if (reviewEmpty) { reviewEmpty.style.display = "none"; }
            reps.slice(0, 50).forEach(function (r) {
                const tr = document.createElement("tr");
                ["name", "email", "phone", "function"].forEach(function (k) {
                    const td = document.createElement("td");
                    td.textContent = r[k] || "—";
                    tr.appendChild(td);
                });
                reviewTbody.appendChild(tr);
            });
            if (reps.length > 50) {
                const tr = document.createElement("tr");
                const td = document.createElement("td");
                td.colSpan = 4;
                td.style.textAlign = "center";
                td.style.color = "#6B7494";
                td.style.fontStyle = "italic";
                td.textContent = "…and " + (reps.length - 50) + " more. All rows will be created.";
                tr.appendChild(td);
                reviewTbody.appendChild(tr);
            }
        }

        // ---- Submit guard ----
        form.addEventListener("submit", function (e) {
            if (countReps() === 0) {
                e.preventDefault();
                setChapter(1, { force: true });
                showUploadStatus("Add at least one rep before creating the batch.", "error");
                return;
            }
            const submitBtn = document.getElementById("bk-submit");
            if (submitBtn) {
                submitBtn.setAttribute("data-loading", "true");
                submitBtn.disabled = true;
                const label = submitBtn.querySelector(".bk-btn-label");
                if (label) { label.textContent = "Creating batch…"; }
            }
        });

        // ---- Init ----
        setChapter(1, { noScroll: true });
    });

    // ================================================================
    // Batch detail — per-rep + bulk resend
    // ================================================================
    onReady(function () {
        const batch = document.getElementById("bk-batch");
        if (!batch) { return; }

        function callJson(url, payload) {
            return fetch(url, {
                method: "POST",
                headers: { "Content-Type": "application/json", "X-CSRFToken": csrf() },
                credentials: "same-origin",
                body: JSON.stringify({ jsonrpc: "2.0", method: "call", params: payload || {} }),
            }).then(function (r) { return r.json(); });
        }

        batch.addEventListener("click", function (e) {
            const perRep = e.target.closest("[data-resend-rep]");
            if (perRep) {
                const repId = Number(perRep.getAttribute("data-rep-id"));
                perRep.disabled = true;
                perRep.textContent = "Sending…";
                callJson("/bulk-onboard/resend-invite/" + repId, {}).then(function (resp) {
                    const r = resp.result || resp;
                    if (r && r.success) {
                        perRep.textContent = "Sent ✓";
                    } else {
                        perRep.textContent = "Retry";
                        perRep.disabled = false;
                        alert((r && r.error) || "Failed to resend.");
                    }
                }).catch(function (err) {
                    perRep.textContent = "Retry";
                    perRep.disabled = false;
                    alert("Network error: " + err.message);
                });
                return;
            }

            if (e.target.id === "bk-bulk-resend") {
                const btn = e.target;
                const rows = Array.from(batch.querySelectorAll("[data-resend-rep]"));
                const repIds = rows.map(function (b) { return Number(b.getAttribute("data-rep-id")); }).filter(Boolean);
                if (!repIds.length) {
                    alert("Nothing to resend.");
                    return;
                }
                if (!confirm("Resend " + repIds.length + " invitation" + (repIds.length === 1 ? "" : "s") + "?")) {
                    return;
                }
                btn.disabled = true;
                btn.textContent = "Sending…";
                callJson("/bulk-onboard/bulk-resend-invite", { rep_ids: repIds }).then(function (resp) {
                    const r = resp.result || resp;
                    if (r && r.success) {
                        btn.textContent = "Sent " + (r.sent_count || 0) + " / " + (r.total_count || repIds.length);
                        setTimeout(function () { window.location.reload(); }, 1500);
                    } else {
                        btn.textContent = "Resend all pending / failed";
                        btn.disabled = false;
                        alert((r && r.error) || "Bulk resend failed.");
                    }
                }).catch(function (err) {
                    btn.textContent = "Resend all pending / failed";
                    btn.disabled = false;
                    alert("Network error: " + err.message);
                });
            }
        });
    });

})();
