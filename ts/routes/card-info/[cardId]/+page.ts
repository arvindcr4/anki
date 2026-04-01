// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
import { cardStats } from "@generated/backend";

import { optionalBigInt } from "../parse-optional-bigint";
import type { PageLoad } from "./$types";

export const load = (async ({ params }) => {
    const cid = optionalBigInt(params.cardId);
    const info = cid !== null ? await cardStats({ cid }) : null;
    return { info };
}) satisfies PageLoad;
