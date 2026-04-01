// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

export function optionalBigInt(value: unknown): bigint | null {
    try {
        return BigInt(value as string | number | bigint);
    } catch {
        return null;
    }
}
