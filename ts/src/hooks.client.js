/** @type {import('@sveltejs/kit').HandleClientError} */
export async function handleError({ error }) {
    return {
        message: error instanceof Error ? error.message : String(error),
    };
}
