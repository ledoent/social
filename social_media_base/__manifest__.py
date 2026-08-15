# Copyright 2025 Binhex <https://www.binhex.cloud>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
{
    "name": "Social Media Base",
    "summary": "Basic module for social media management.",
    "version": "19.0.1.0.0",
    "category": "Social Network",
    "development_status": "Beta",
    "license": "AGPL-3",
    "author": "BinhexTeam,Odoo Community Association (OCA)",
    "website": "https://github.com/OCA/social",
    "maintainers": ["edescalona"],
    "depends": ["base", "web", "mail", "utm", "link_tracker"],
    # The Enterprise "social" module declares the same social.media, social.account
    # and social.post models, so the two cannot live in the same database.
    "excludes": ["social"],
    "data": [
        "security/social_media_base_groups.xml",
        "security/ir.model.access.csv",
        "security/social_account_security.xml",
        "security/social_post_security.xml",
        "security/social_post_account_security.xml",
        "security/wizard_social_account_security.xml",
        "data/utm_medium_data.xml",
        "data/ir_cron_data.xml",
        "views/social_media_views.xml",
        "views/social_account_views.xml",
        "views/social_post_views.xml",
        "views/social_post_account_views.xml",
        "views/utm_campaign_views.xml",
        "views/social_action_client_views.xml",
        "wizards/wizard_social_account.xml",
        "views/social_media_base_menus.xml",
    ],
    "assets": {
        "web.assets_backend": [
            ("include", "web.chartjs_lib"),
            "social_media_base/static/src/xml/**/*.xml",
            # Partials first: SCSS assets are compiled as a single unit, so
            # mixins must be declared before the stylesheets using them.
            "social_media_base/static/src/scss/app/_social_mixins.scss",
            "social_media_base/static/src/scss/**/*.scss",
            "social_media_base/static/src/js/app/**/*.js",
            "social_media_base/static/src/js/services/**/*.js",
            "social_media_base/static/src/components/**/*.xml",
            "social_media_base/static/src/components/**/*.js",
            "social_media_base/static/src/components/**/*.scss",
            "social_media_base/static/src/js/views/**/*.xml",
            "social_media_base/static/src/js/views/**/*.js",
        ],
    },
    "installable": True,
}
