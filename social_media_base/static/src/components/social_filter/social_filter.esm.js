/** @odoo-module **/
import {Component, useState} from "@odoo/owl";
import {Dropdown} from "@web/core/dropdown/dropdown";
import {DropdownItem} from "@web/core/dropdown/dropdown_item";
import {_t} from "@web/core/l10n/translation";
import {serializeDate} from "@web/core/l10n/dates";
import {useDateTimePicker} from "@web/core/datetime/datetime_picker_hook";

const {DateTime} = luxon;

export class SocialFilter extends Component {
    static template = "social_media_base.SocialFilter";
    static props = {
        objectId: {type: Number, optional: true},
        filter: {type: Function, required: true},
        filterGranularity: {type: Boolean, optional: true, default: false},
        granularities: {type: Array, optional: true},
    };
    static components = {
        Dropdown,
        DropdownItem,
    };

    setup() {
        super.setup();
        this.state = useState({
            // A social media with no granularity of its own hides the
            // selector, so there is nothing to pick.
            currentFilterType: this.filterTypes[0] || null,
            dateRange: [DateTime.now().minus({months: 1}), DateTime.now()],
        });
        // The range is delegated to the core hook: it owns the two inputs
        // marked "start-date" and "end-date", opens the picker as a popover
        // and reads the dates with the format of the user language. The
        // committed range is kept in the state so the hook compares against
        // it and reapplies a filter that goes back to the previous range.
        const getPickerProps = () => ({
            type: "date",
            range: true,
            value: this.state.dateRange,
        });
        useDateTimePicker({
            target: "root",
            get pickerProps() {
                return getPickerProps();
            },
            onApply: (value) => {
                this.state.dateRange = [...value];
                this.onFilter();
            },
        });
    }

    /** Granularities the social media supports, or all of them by default. */
    get filterTypes() {
        const labels = {day: _t("Day"), week: _t("Week"), month: _t("Month")};
        const granularities = this.props.granularities || Object.keys(labels);
        return granularities
            .map((granularity) => granularity.toLowerCase())
            .filter((granularity) => granularity in labels)
            .map((granularity) => ({id: granularity, name: labels[granularity]}));
    }

    async onSelectTypeRange(typeRange) {
        this.state.currentFilterType = typeRange;
        await this.onFilter();
    }

    async onFilter() {
        const [start, end] = this.state.dateRange;
        await this.props.filter({
            id: this.props.objectId,
            startDate: start ? serializeDate(start) : null,
            endDate: end ? serializeDate(end) : null,
            chartFilterType: this.state.currentFilterType
                ? this.state.currentFilterType.id
                : null,
        });
    }
}
