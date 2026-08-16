/** @odoo-module **/
import {Component, onMounted, useState} from "@odoo/owl";
import {SocialChartAccount} from "@social_media_base/components/social_chart_account/social_chart_account.esm";
import {SocialMediaMixin} from "../../js/app/social_media_mixin.esm";
import {registry} from "@web/core/registry";
import {useService} from "@web/core/utils/hooks";

/** Client action showing the statistics chart of every connected account. */
export class SocialChart extends SocialMediaMixin(Component) {
    static template = "social_media_base.SocialChart";
    static props = ["*"];
    static components = {
        SocialChartAccount,
    };

    /** The statistics are loaded once mounted, so the loader is rendered. */
    setup() {
        super.setup();
        this.ormService = useService("orm");
        this.socialState = useState({
            statistics: [],
            loaderChart: true,
        });
        onMounted(async () => {
            await this._loadAccountStatistics();
        });
        this.notifView = "chart";
        this.notificationService = useService("notification");
        this.busService = this.env.services.bus_service;
        this.enableSocialNotifications();
    }

    get socialAccountStatistics() {
        return this.socialState.statistics;
    }

    async _loadAccountStatistics() {
        this.socialState.loaderChart = true;
        try {
            this.socialState.statistics = await this.ormService.call(
                "social.account",
                "get_chart_account_statistics",
                [[]]
            );
        } finally {
            this.socialState.loaderChart = false;
        }
    }
}

registry.category("actions").add("social_media_chart", SocialChart);
