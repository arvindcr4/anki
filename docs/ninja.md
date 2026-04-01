Brief notes for people used to the existing Bazel build system:

- Put the ninja binary on your path: https://github.com/ninja-build/ninja/releases/tag/v1.11.1
  (on Windows, if you have it installed in msys, make sure the native binary occurs earlier on the path)
- Ensure Rust is installed via rustup: https://rustup.rs/
- Remove the .bazel and node_modules folders from your existing checkout

- Run with ./run
- Run tests with './ninja check' (tools\ninja on Windows)
- Format files with './ninja format'
- Fix eslint/copyright issues with './ninja fix'
- Targets are hierarchical, so './ninja check:vitest' will run the Vitest
  suite, and './ninja check:svelte:editor' will run the Svelte checks for the
  editor.
