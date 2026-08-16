/** @odoo-module **/

import {markup, onWillStart, useState, useSubEnv} from "@odoo/owl";
import {useBus, useService} from "@web/core/utils/hooks";
import {KanbanController} from "@web/views/kanban/kanban_controller";
import {SocialAccount} from "@social_media_base/components/social_account/social_account.esm";
import {_t} from "@web/core/l10n/translation";
import {session} from "@web/session";

export class SocialKanbanController extends KanbanController {
    /** @override */
    setup() {
        super.setup();
        this.actionService = useService("action");
        this.notificationService = useService("notification");
        this.socialState = useState({accounts: [], syncPosts: false});
        onWillStart(() => {
            // Not awaited on purpose: the kanban must paint its records without
            // waiting for the account bar data.
            this._loadSocialAccounts();
        });
        useSubEnv({
            model: this.model,
        });
        useBus(this.env.bus, "SOCIAL:RELOAD_ORGANIZATION", async ({detail: data}) => {
            await this._updatePostsAndStatistics(
                data?.account_id ?? null,
                data?.post_id ?? null
            );
        });
        useBus(this.env.bus, "SOCIAL:POSTS-UPDATED", async ({detail: payload}) => {
            await this._reloadPostsAndStatistics(payload);
        });
    }

    modelsNotShowAccount() {
        return ["social.post", "social.media"];
    }

    get isAccountPanelHidden() {
        const models = this.modelsNotShowAccount();
        return models.includes(this.model.config.resModel);
    }

    async _loadSocialAccounts() {
        if (this.isAccountPanelHidden) return;
        const accounts = await this.model._loadAccounts();
        this.socialState.accounts = accounts;
        this.socialState.syncPosts = accounts.some(
            (account) => account.pending_initial_sync
        );
    }

    _onAddAccount() {
        return this.actionService.doAction("social_media_base.social_media_action");
    }

    _onAddPost() {
        return this.actionService.doAction({
            name: _t("New Post"),
            type: "ir.actions.act_window",
            res_model: "social.post",
            views: [[false, "form"]],
        });
    }

    async _reloadPostsAndStatistics(payload = {}) {
        if (this.isAccountPanelHidden) return;
        this.socialState.accounts = await this.model._loadAccounts();
        await this.model.load();
        this.socialState.syncPosts = false;
        this.env.bus.trigger("SOCIAL:SYNCING", {syncing: false});
        this.notificationService.add(
            payload.message
                ? markup(payload.message)
                : _t("The posts of the account were updated."),
            {type: payload.message_type || "info"}
        );
    }

    async _updatePostsAndStatistics(accountId = null, postId = null) {
        const data = await this.model.onUpdatePostsAndStatistics(accountId, postId);
        this.socialState.accounts = JSON.parse(data);
        this.model.load();
    }

    async _onUpdatePostsAndStatistics() {
        this.socialState.syncPosts = true;
        await this._updatePostsAndStatistics();
        if (this.socialState.accounts.length > 0 && !session.social_error)
            this.notificationService.add(_t("The data was updated successfully."), {
                type: "info",
            });
        this.socialState.syncPosts = false;
        session.social_error = false;
        this.env.bus.trigger("SOCIAL:NEED-UPDATE", {
            needUpdate: false,
        });
    }
}

SocialKanbanController.components = {
    ...KanbanController.components,
    SocialAccount,
};
SocialKanbanController.template = "social_media_base.KanbanView";
