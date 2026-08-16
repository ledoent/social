/** @odoo-module **/

import {RelationalModel} from "@web/model/relational_model/relational_model";
import {_t} from "@web/core/l10n/translation";

export class SocialKanbanModel extends RelationalModel {
    _getDomainSocialAccount() {
        return [];
    }

    async _loadAccounts() {
        return await this.orm.searchRead(
            "social.account",
            this._getDomainSocialAccount(),
            [
                "id",
                "name",
                "company_id",
                "media_id",
                "account_url",
                "impression_count",
                "interactions_count",
                "engagement",
                "need_update",
                "pending_initial_sync",
            ]
        );
    }

    async onUpdatePostsAndStatistics(accountId = null, postId = null) {
        const account = accountId ? [accountId] : [];
        return await this.orm.silent.call("social.account", "update_posts_statistics", [
            account,
            postId,
            this._getDomainSocialAccount(),
        ]);
    }

    onLikePost(record) {
        if (!record) {
            return {success: false, message: ""};
        }
        return {
            success: false,
            message: _t("Likes are not available for this social media."),
        };
    }
}
