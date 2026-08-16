/** @odoo-module **/

import {Component, onMounted, useRef, useState} from "@odoo/owl";
import {ControlPanel} from "@web/search/control_panel/control_panel";
import {SocialFilter} from "../social_filter/social_filter.esm";
import {_t} from "@web/core/l10n/translation";
import {useService} from "@web/core/utils/hooks";

const {DateTime} = luxon;

export class SocialChartAccount extends Component {
    static template = "social_media_base.SocialChartAccount";
    static props = {
        socialChartAccount: {type: Object, required: true},
    };
    static components = {
        ControlPanel,
        SocialFilter,
    };

    setup() {
        super.setup();
        this.ormService = useService("orm");
        this.notificationService = useService("notification");
        this.chartCtx = useRef("chartAccount");
        this.chart = null;
        onMounted(this.loadChart);
        this.state = useState({
            impressionCount: 0,
            commentCount: 0,
            reactionCount: 0,
            impressionCountTotal: null,
            commentCountTotal: null,
            reactionCountTotal: null,
        });
    }

    get chartAccount() {
        return this.props.socialChartAccount;
    }

    /**
     * The figures of the period always come with the statistics; the ones of
     * the whole account only come when the screen is loaded, since they do
     * not depend on the range, so a filter keeps the ones already shown.
     *
     * @param {Object} updateChart Statistics to display on the counters.
     */
    updateTotals(updateChart) {
        this.state.impressionCount = updateChart.impressionCount;
        this.state.reactionCount = updateChart.reactionCount;
        this.state.commentCount = updateChart.commentCount;
        if (updateChart.impressionCountTotal !== null) {
            this.state.impressionCountTotal = updateChart.impressionCountTotal;
            this.state.reactionCountTotal = updateChart.reactionCountTotal;
            this.state.commentCountTotal = updateChart.commentCountTotal;
        }
    }

    loadChart(labels, datasets) {
        if (this.chart) this.chart.destroy();
        this.updateTotals(this.chartAccount);
        this.chart = new window.Chart(this.chartCtx.el, {
            type: "line",
            data: {
                labels: labels ? labels : this.chartAccount.labels,
                datasets: datasets ? datasets : this.chartAccount.datasets,
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    title: {
                        display: true,
                        text: () => this.chartAccount.chartLabel,
                    },
                },
            },
        });
    }

    isRangeLongEnough(startDate, endDate, granularity) {
        if (!startDate || !endDate || !granularity) return true;
        const start = DateTime.fromISO(startDate);
        const end = DateTime.fromISO(endDate);
        if (!start.isValid || !end.isValid) return true;
        const units = {DAY: {days: 1}, WEEK: {weeks: 1}, MONTH: {months: 1}};
        const unit = units[granularity];
        return unit ? end >= start.plus(unit) : true;
    }

    async onFilterChart({id, startDate, endDate, chartFilterType}) {
        let updateChart = [];
        const granularity = chartFilterType ? chartFilterType.toUpperCase() : null;
        if (!this.isRangeLongEnough(startDate, endDate, granularity)) {
            this.notificationService.add(
                _t(
                    "The date range has to cover at least one %s.",
                    granularity.toLowerCase()
                ),
                {type: "warning"}
            );
            return;
        }
        if (startDate || endDate || chartFilterType)
            // The figures of the whole account are not asked for again: they
            // do not depend on the range and reading them costs another call
            // to the social media.
            updateChart = await this.ormService.call(
                "social.account",
                "get_chart_account_statistics",
                [id, startDate, endDate, granularity, false]
            );
        if (updateChart.length > 0) {
            this.loadChart(updateChart[0].labels, updateChart[0].datasets);
            this.updateTotals(updateChart[0]);
        }
    }
}
