"""
License enforcement for all Vinc models.

Overrides create() and write() on every user-facing model so that no data
can be created or modified unless the Vinc license is active (or in the
30-day warning window).  Read access is never blocked.
"""

from odoo import api, fields, models


def _check(env):
    if env.context.get("install_mode") or env.context.get("module"):
        return  # skip during module install/upgrade data loading
    env["vinc.license"].sudo().check_license()


class GuardPartnerVcard(models.Model):
    _inherit = "partner.vcard"

    vinc_license_ok = fields.Boolean(
        compute="_compute_vinc_license_ok",
        string="License OK",
    )

    def _compute_vinc_license_ok(self):
        lic = self.env["vinc.license"].sudo()._get_license_record()
        ok = lic._effective_status() in ("active", "warning")
        for rec in self:
            rec.vinc_license_ok = ok

    @api.model_create_multi
    def create(self, vals_list):
        _check(self.env)
        return super().create(vals_list)

    def write(self, vals):
        _check(self.env)
        return super().write(vals)


class GuardVcardWebsite(models.Model):
    _inherit = "partner.vcard.website"

    @api.model_create_multi
    def create(self, vals_list):
        _check(self.env)
        return super().create(vals_list)

    def write(self, vals):
        _check(self.env)
        return super().write(vals)


class GuardVcardVideos(models.Model):
    _inherit = "partner.vcard.videos"

    @api.model_create_multi
    def create(self, vals_list):
        _check(self.env)
        return super().create(vals_list)

    def write(self, vals):
        _check(self.env)
        return super().write(vals)


class GuardVcardReviews(models.Model):
    _inherit = "partner.vcard.reviews"

    @api.model_create_multi
    def create(self, vals_list):
        _check(self.env)
        return super().create(vals_list)

    def write(self, vals):
        _check(self.env)
        return super().write(vals)


class GuardVcardSpeciality(models.Model):
    _inherit = "partner.vcard.speciality"

    @api.model_create_multi
    def create(self, vals_list):
        _check(self.env)
        return super().create(vals_list)

    def write(self, vals):
        _check(self.env)
        return super().write(vals)


class GuardVcardService(models.Model):
    _inherit = "partner.vcard.service"

    @api.model_create_multi
    def create(self, vals_list):
        _check(self.env)
        return super().create(vals_list)

    def write(self, vals):
        _check(self.env)
        return super().write(vals)


class GuardVcardServiceQuestion(models.Model):
    _inherit = "partner.vcard.service.question"

    @api.model_create_multi
    def create(self, vals_list):
        _check(self.env)
        return super().create(vals_list)

    def write(self, vals):
        _check(self.env)
        return super().write(vals)


class GuardUserDashboard(models.TransientModel):
    _inherit = "user.dashboard"

    @api.model
    def get_dashboard(self):
        """Redirect to license form if not licensed."""
        lic = self.env["vinc.license"].sudo()._get_license_record()
        if lic.license_status not in ("active", "warning"):
            return lic
        return super().get_dashboard()


class GuardLeadbackChannel(models.Model):
    _inherit = "leadback.messaging.channel"

    @api.model_create_multi
    def create(self, vals_list):
        _check(self.env)
        return super().create(vals_list)

    def write(self, vals):
        _check(self.env)
        return super().write(vals)


class GuardLeadbackEmail(models.Model):
    _inherit = "leadback.scheduled.email"

    @api.model_create_multi
    def create(self, vals_list):
        _check(self.env)
        return super().create(vals_list)

    def write(self, vals):
        _check(self.env)
        return super().write(vals)


class GuardLeadTag(models.Model):
    _inherit = "lead.tag"

    @api.model_create_multi
    def create(self, vals_list):
        _check(self.env)
        return super().create(vals_list)

    def write(self, vals):
        _check(self.env)
        return super().write(vals)


class GuardFollowupReminder(models.Model):
    _inherit = "followup.reminder"

    @api.model_create_multi
    def create(self, vals_list):
        _check(self.env)
        return super().create(vals_list)

    def write(self, vals):
        _check(self.env)
        return super().write(vals)


class GuardFollowupScheduled(models.Model):
    _inherit = "followup.scheduled.reminder"

    @api.model_create_multi
    def create(self, vals_list):
        _check(self.env)
        return super().create(vals_list)

    def write(self, vals):
        _check(self.env)
        return super().write(vals)


## leadback.preview — TransientModel (wizard only), not guarded


class GuardBulkOnboardingBatch(models.Model):
    _inherit = "bulk.onboarding.batch"

    @api.model_create_multi
    def create(self, vals_list):
        _check(self.env)
        return super().create(vals_list)

    def write(self, vals):
        _check(self.env)
        return super().write(vals)


class GuardBulkOnboardingRep(models.Model):
    _inherit = "bulk.onboarding.rep"

    @api.model_create_multi
    def create(self, vals_list):
        _check(self.env)
        return super().create(vals_list)

    def write(self, vals):
        _check(self.env)
        return super().write(vals)


class GuardBulkOnboardingToken(models.Model):
    _inherit = "bulk.onboarding.token"

    @api.model_create_multi
    def create(self, vals_list):
        _check(self.env)
        return super().create(vals_list)

    def write(self, vals):
        _check(self.env)
        return super().write(vals)
