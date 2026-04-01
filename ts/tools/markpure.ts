// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import * as fs from "fs";
import * as path from "path";

function allFilesInDir(directory: string): string[] {
    const results: string[] = [];
    const list = fs.readdirSync(directory);

    for (const entry of list) {
        const file = path.join(directory, entry);
        const stat = fs.statSync(file);

        if (stat && stat.isDirectory()) {
            results.push(...allFilesInDir(file));
        } else {
            results.push(file);
        }
    }

    return results;
}

function adjustFiles(): void {
    const root = process.argv[2];
    if (!root) {
        throw new Error("markpure: expected a root directory argument");
    }
    const typeRe = /(make(Enum|MessageType))\(\n\s+".*",/g;

    const jsFiles = allFilesInDir(root).filter((f) => f.endsWith(".js"));
    for (const file of jsFiles) {
        const contents = fs.readFileSync(file, "utf8");

        // strip out typeName info, which appears to only be required for
        // certain JSON functionality (though this only saves a few hundred
        // bytes)
        const newContents = contents.replace(typeRe, "$1(\"\",");

        if (contents !== newContents) {
            fs.writeFileSync(file, newContents, "utf8");
        }
    }
}

adjustFiles();
