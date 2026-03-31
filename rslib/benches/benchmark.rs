// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

use anki::card_rendering::anki_directive_benchmark;
use anki::cloze::cloze_numbers_benchmark;
use anki::cloze::cloze_reveal_benchmark;
use anki::template::template_parse_benchmark;
use anki::template::template_render_benchmark;
use anki::text::html_to_text_line_benchmark;
use anki::text::strip_html_benchmark;
use criterion::criterion_group;
use criterion::criterion_main;
use criterion::Criterion;

pub fn criterion_benchmark(c: &mut Criterion) {
    c.bench_function("anki_tag_parse", |b| b.iter(|| anki_directive_benchmark()));
    c.bench_function("template_parse", |b| b.iter(|| template_parse_benchmark()));
    c.bench_function("template_render", |b| {
        b.iter(|| template_render_benchmark())
    });
    c.bench_function("cloze_reveal", |b| b.iter(|| cloze_reveal_benchmark()));
    c.bench_function("cloze_numbers", |b| b.iter(|| cloze_numbers_benchmark()));
    c.bench_function("strip_html", |b| b.iter(|| strip_html_benchmark()));
    c.bench_function("html_to_text_line", |b| {
        b.iter(|| html_to_text_line_benchmark())
    });
}

criterion_group!(benches, criterion_benchmark);
criterion_main!(benches);
