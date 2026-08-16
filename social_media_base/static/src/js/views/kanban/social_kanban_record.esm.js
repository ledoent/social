/** @odoo-module **/
import {KanbanRecord} from "@web/views/kanban/kanban_record";
import {SocialCommentDialog} from "@social_media_base/components/social_comment_dialog/social_comment_dialog.esm";
import {SocialMessage} from "@social_media_base/components/social_message/social_message.esm";
import {SocialPostAccountMixin} from "@social_media_base/js/app/social_media_base_mixins.esm";
import {_t} from "@web/core/l10n/translation";
import {useEffect} from "@odoo/owl";
import {useService} from "@web/core/utils/hooks";

export class SocialKanbanRecord extends SocialPostAccountMixin(KanbanRecord) {
    /** @override */
    setup() {
        super.setup();
        this.record.countShowImage = 2;
        this.dialogService = useService("dialog");
        this.effectService = useService("effect");
        this.orm = useService("orm");
        this.messageNotExistPost = _t("The post does not exist or has been deleted.");
        this.record.notAvailableLike = [];

        useEffect(
            (value) => {
                if (value) {
                    const listener = this.onLikePost.bind(this);
                    value.addEventListener("click", listener);
                    return () => {
                        value.removeEventListener("click", listener);
                    };
                }
            },
            () => [this.rootRef.el.querySelector(".social-like-post")]
        );

        useEffect(
            (value) => {
                if (value) {
                    const listener = this.onShowAllImages.bind(this);
                    value.addEventListener("click", listener);
                    return () => {
                        value.removeEventListener("click", listener);
                    };
                }
            },
            () => [this.rootRef.el.querySelector(".social-all-images")]
        );

        useEffect(
            (value) => {
                if (value) {
                    const listener = this.onPostComment.bind(this);
                    value.addEventListener("click", listener);
                    return () => {
                        value.removeEventListener("click", listener);
                    };
                }
            },
            () => [this.rootRef.el.querySelector(".social-post-comment")]
        );
    }

    onPostComment(ev) {
        ev.stopPropagation();
        this.dialogService.add(SocialCommentDialog, {
            title: _t("Post Comment"),
            account: this.record.account_id,
            post: this.record,
            media_type: this.record.media_type,
            images: JSON.parse(this.record.image_urls.raw_value),
        });
    }

    /**
     * Ask the server whether the publication is still on the social media.
     * The check lives in Python so this card and the form button answer the
     * same thing.
     *
     * @returns {Promise<Boolean>}
     */
    async validPostExist() {
        const postAccountId = this.record.id.raw_value;
        if (!postAccountId) {
            return false;
        }
        return await this.orm.call("social.post.account", "check_post_exists", [
            postAccountId,
        ]);
    }

    messagePostNotExist() {
        this.notification.add(this.messageNotExistPost, {
            type: "info",
        });
    }

    /** @override */
    async onGlobalClick(ev) {
        const kanbanSocial = ev.target.closest("div.oe_kanban_social_dashboard");
        if (kanbanSocial !== null && !this.record.post_account_url.value) {
            this.messagePostNotExist();
            this.env.model.load();
        } else if (kanbanSocial !== null && this.record.post_account_url.raw_value) {
            const postExist = await this.validPostExist();
            if (postExist) {
                window.open(this.record.post_account_url.value, "_blank");
            } else {
                this.messagePostNotExist();
                this.env.model.load();
            }
        }
        return super.onGlobalClick(ev);
    }
}

SocialKanbanRecord.components = {
    ...KanbanRecord.components,
    SocialMessage,
};
