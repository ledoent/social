/** @odoo-module **/

import {
    Component,
    onMounted,
    onWillStart,
    onWillUnmount,
    useEffect,
    useState,
} from "@odoo/owl";
import {useBus, useService} from "@web/core/utils/hooks";
import {Composer} from "@mail/core/common/composer";
import {Dialog} from "@web/core/dialog/dialog";
import {SocialComment} from "../social_comment/social_comment.esm";
import {SocialImageDialog} from "../social_image_dialog/social_image_dialog.esm";
import {SocialMessage} from "../social_message/social_message.esm";
import {_t} from "@web/core/l10n/translation";

export class SocialCommentDialog extends Component {
    static template = "social_media_base.SocialCommentDialog";
    static components = {
        Dialog,
        Composer,
        SocialComment,
        // The dialog shares the block of the card with the kanban views, and
        // that block draws the message with this component. The dialog shows
        // the message whole, so the branch is never taken, but the template
        // is the same one and it is resolved against the components of
        // whoever calls it.
        SocialMessage,
    };
    static props = {
        title: {type: String, required: true},
        images: {type: Array, required: true},
        post: {type: Object, required: true},
        account: {type: Object, required: true},
        media_type: {type: Object, required: true},
        close: {type: Function},
    };

    setup() {
        super.setup();
        this.dialogService = useService("dialog");
        this.socialService = useService("social_service");
        this.threadService = useService("mail.thread");
        this.notificationService = useService("notification");
        this.busService = this.env.services.bus_service;
        this.record = this.props.post;
        this.state = useState({
            thread: undefined,
            comments: [],
            account_id: this.props.account.raw_value,
        });
        onWillStart(async () => {
            this.state.thread = this.threadService.getThread(
                "social.post.account",
                this.props.post.id.value
            );
            const result = await this.socialService.getComments(
                this.props.post.id.raw_value
            );
            if (result && result.success) {
                this.state.comments = result.data || [];
            } else {
                this.notificationService.add(
                    (result && result.message) || _t("Error retrieving comments"),
                    {
                        type: "danger",
                    }
                );
            }
        });

        useBus(this.env.bus, "SOCIAL:RELOAD_COMMENTS", async () => {
            await this.updateListComments();
        });

        onMounted(() => {
            this.intervalRefreshComment = setInterval(() => {
                this.updateListComments();
            }, 120000);
        });

        onWillUnmount(() => {
            clearInterval(this.intervalRefreshComment);
        });

        const handleNotification = ({detail: notifications}) => {
            if (notifications && notifications.length > 0) {
                notifications.forEach((notif) => {
                    const {payload, type} = notif;
                    if (type === "comments" && payload) {
                        const message =
                            payload === undefined || payload.message === undefined
                                ? _t("Comment created")
                                : payload.message;
                        const typeNotif =
                            payload.success === true ? "success" : "danger";
                        this.env.bus.trigger("SOCIAL:RELOAD_COMMENTS");
                        this.notificationService.add(message, {
                            type: typeNotif,
                        });
                        this.env.bus.trigger("SOCIAL:RELOAD_ORGANIZATION", {
                            account_id: this.props.account.raw_value,
                            post_id: this.props.post.remote_ref.raw_value,
                        });
                    }
                });
            }
        };
        useEffect(() => {
            this.busService.addEventListener("notification", handleNotification);
            return () => {
                this.busService.removeEventListener("notification", handleNotification);
            };
        });
    }

    get comments() {
        return this.state.comments;
    }

    onShowAllImages(ev) {
        ev.stopPropagation();
        this.dialogService.add(SocialImageDialog, {
            title: _t("All Images"),
            images: JSON.parse(this.props.post.image_urls.raw_value),
        });
    }

    async updateListComments() {
        const result = await this.socialService.getComments(
            this.props.post.id.raw_value
        );
        this.state.comments = result?.data ?? [];
    }

    _commentAllowUpload() {
        return true;
    }

    get commentAllowUpload() {
        return this._commentAllowUpload();
    }

    /** The comment is published on the social media, not logged as a note. */
    get composerPlaceholder() {
        const account = this.record.author?.value || this.props.account.value;
        return _t("Comment as %(account)s…", {account});
    }

    get renderingContext() {
        return {
            luxon,
            record: this.record,
            images: this.props.images,
            isDialog: true,
            onShowAllImages: this.onShowAllImages.bind(this),
        };
    }
}
