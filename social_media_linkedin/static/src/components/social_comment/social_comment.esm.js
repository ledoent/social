/** @odoo-module **/

import {SocialComment} from "@social_media_base/components/social_comment/social_comment.esm";
import {patch} from "@web/core/utils/patch";
import {useService} from "@web/core/utils/hooks";

patch(SocialComment.prototype, {
    /** @override */
    setup() {
        super.setup();
        this.socialLinkedinService = useService("social_linkedin_service");
    },
    /** @override */
    async _onDeleteComment() {
        return this.socialLinkedinService.deleteLinkedinComment(
            this.props.post.id.raw_value,
            this.props.socialComment.id,
            this.props.socialComment.actor
        );
    },

    /** @override */
    mediaNotLikeEnable() {
        const values = super.mediaNotLikeEnable();
        values.push("linkedin");
        return values;
    },
});
