/** @odoo-module **/

import {Component} from "@odoo/owl";
import {ConfirmationDialog} from "@web/core/confirmation_dialog/confirmation_dialog";
import {Dropdown} from "@web/core/dropdown/dropdown";
import {DropdownItem} from "@web/core/dropdown/dropdown_item";
import {_t} from "@web/core/l10n/translation";
import {useService} from "@web/core/utils/hooks";

export class SocialComment extends Component {
    static template = "social_media_base.SocialComment";
    static components = {
        Dropdown,
        DropdownItem,
    };
    static props = {
        socialComment: {type: Object, required: true},
        post: {type: Object, required: true},
    };

    setup() {
        super.setup();
        this.socialService = useService("social_service");
        this.notificationService = useService("notification");
        this.effectService = useService("effect");
        this.dialog = useService("dialog");
    }

    async _onDeleteComment() {
        return {};
    }

    async onDeleteComment() {
        this.dialog.add(ConfirmationDialog, {
            title: _t("Delete comment"),
            body: _t("Are you sure you want to delete this comment?"),
            confirm: () => this.deleteComment(),
            confirmLabel: _t("Delete"),
            cancel: () => undefined,
            cancelLabel: _t("Cancel"),
        });
    }

    async deleteComment() {
        const result = await this._onDeleteComment();
        const message =
            result.message === undefined ? _t("Comment deleted") : result.message;
        const typeNotif = result.success === true ? "success" : "danger";
        this.notificationService.add(message, {
            type: typeNotif,
            sticky: typeNotif === "danger",
        });
        this.env.bus.trigger("SOCIAL:RELOAD_COMMENTS");
        if (result.success === true) {
            this.env.bus.trigger("SOCIAL:RELOAD_ORGANIZATION", {
                account_id: this.props.post.account_id.raw_value,
                post_id: this.props.post.remote_ref.raw_value,
            });
        }
    }

    mediaNotLikeEnable() {
        return [];
    }

    async onLikeComment() {
        const response = await this.socialService.likeComment(
            this.props.post.id.raw_value,
            this.props.socialComment.id,
            this.props.post.account_remote_ref.raw_value
        );
        if (response.success) {
            this.effectService.add({
                type: "rainbow_man",
                message: _t("You have liked the post."),
                imgUrl: "/social_media_base/static/src/img/like.png",
                fadeout: "fast",
            });
        } else {
            // The message comes from the social media, it is not a literal
            // the translation extractor can collect.
            this.notificationService.add(response.message, {type: "info"});
        }
    }

    _onReplyComment() {
        return {};
    }

    onReplyComment() {
        this.env.bus.trigger("SOCIAL:RELOAD_COMMENTS");
    }
}
