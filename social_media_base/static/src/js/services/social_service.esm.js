/** @odoo-module */

import {_t} from "@web/core/l10n/translation";
import {registry} from "@web/core/registry";

export const socialService = {
    dependencies: ["orm"],

    async start(env, {orm}) {
        return {
            async getComments(postAccountId = null) {
                if (!postAccountId) {
                    return [];
                }
                return await orm.call("social.post.account", "get_comments", [
                    postAccountId,
                ]);
            },
            async likeComment(postAccountId, commentId, actorUrn) {
                if (!postAccountId || !commentId || !actorUrn) {
                    return {
                        success: false,
                        message: _t("An error occurred while liking the comment"),
                    };
                }
                return await orm.call("social.post.account", "action_like_comment", [
                    [postAccountId],
                    commentId,
                    actorUrn,
                ]);
            },
        };
    },
};

registry.category("services").add("social_service", socialService);
