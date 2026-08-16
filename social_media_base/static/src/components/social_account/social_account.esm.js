/** @odoo-module **/

import {Component, onWillStart, onWillUpdateProps, useState} from "@odoo/owl";
import {formatFloat} from "@web/views/fields/formatters";
import {useBus} from "@web/core/utils/hooks";

export class SocialAccount extends Component {
    static template = "social_media_base.SocialAccount";
    static props = {
        socialAccounts: {type: Array},
    };

    setup() {
        super.setup();
        this.state = useState({
            needUpdate: false,
            syncing: false,
        });
        onWillStart(() => this._updateStateFromAccounts(this.props.socialAccounts));
        // The accounts are loaded after the first paint, so the state has to be
        // refreshed when they finally reach the component.
        onWillUpdateProps((nextProps) =>
            this._updateStateFromAccounts(nextProps.socialAccounts)
        );
        useBus(this.env.bus, "SOCIAL:NEED-UPDATE", async ({detail: data}) => {
            this.state.needUpdate = data.needUpdate;
        });
        useBus(this.env.bus, "SOCIAL:SYNCING", async ({detail: data}) => {
            this.state.syncing = data.syncing;
        });
    }

    _updateStateFromAccounts(socialAccounts) {
        this.state.needUpdate = socialAccounts.some((item) => item.need_update);
        this.state.syncing = socialAccounts.some((item) => item.pending_initial_sync);
    }

    formatEngagement(value) {
        return formatFloat(value || 0, {digits: [16, 2]});
    }
}
