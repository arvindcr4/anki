# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

from __future__ import annotations

import html
import os
import re
from dataclasses import dataclass

import anki
import anki.collection
from anki import card_rendering_pb2, hooks
from anki.config import Config
from anki.models import NotetypeDict
from anki.template import TemplateRenderContext, TemplateRenderOutput
from anki.utils import call, is_mac, namedtmp, tmpdir

# TikZ support — adds tikz/pgfplots when a card uses [tikz]...[/tikz] or
# embeds \begin{tikzpicture}…\end{tikzpicture} inside a [latex] block.
_TIKZ_TAG_RE = re.compile(r"\[tikz\](.+?)\[/tikz\]", re.DOTALL | re.IGNORECASE)
_TIKZ_PREAMBLE = (
    r"\usepackage{tikz}"
    "\n"
    r"\usepackage{pgfplots}"
    "\n"
    r"\pgfplotsset{compat=1.18}"
    "\n"
    r"\usetikzlibrary{"
    r"arrows.meta,positioning,calc,shapes,shapes.geometric,"
    r"decorations.pathreplacing,decorations.pathmorphing,"
    r"intersections,patterns,fit,backgrounds,matrix"
    r"}"
    "\n"
)


def _wrap_tikz_block(match: re.Match[str]) -> str:
    body = match.group(1).strip()
    if r"\begin{tikzpicture}" not in body:
        body = "\\begin{tikzpicture}\n" + body + "\n\\end{tikzpicture}"
    return f"[latex]{body}[/latex]"


def _normalize_tikz(text: str) -> str:
    """Rewrite [tikz]…[/tikz] into [latex]\\begin{tikzpicture}…\\end{tikzpicture}[/latex]."""
    return _TIKZ_TAG_RE.sub(_wrap_tikz_block, text)


def _needs_tikz(latex_body: str) -> bool:
    return r"\begin{tikzpicture}" in latex_body or r"\tikz" in latex_body


def _inject_tikz_preamble(header: str) -> str:
    """Insert tikz/pgfplots preamble before \\begin{document} if not already loaded."""
    if "\\usepackage{tikz}" in header:
        return header
    marker = "\\begin{document}"
    if marker in header:
        return header.replace(marker, _TIKZ_PREAMBLE + marker)
    return header + "\n" + _TIKZ_PREAMBLE

pngCommands = [
    ["latex", "-interaction=nonstopmode", "tmp.tex"],
    [
        "dvipng",
        "-bg",
        "Transparent",
        "-D",
        "200",
        "-T",
        "tight",
        "tmp.dvi",
        "-o",
        "tmp.png",
    ],
]

svgCommands = [
    ["latex", "-interaction=nonstopmode", "tmp.tex"],
    ["dvisvgm", "--no-fonts", "--exact", "-Z", "2", "tmp.dvi", "-o", "tmp.svg"],
]

# add standard tex install location to osx
if is_mac:
    os.environ["PATH"] += ":/usr/texbin:/Library/TeX/texbin"


@dataclass
class ExtractedLatex:
    filename: str
    latex_body: str


@dataclass
class ExtractedLatexOutput:
    html: str
    latex: list[ExtractedLatex]

    @staticmethod
    def from_proto(
        proto: card_rendering_pb2.ExtractLatexResponse,
    ) -> ExtractedLatexOutput:
        return ExtractedLatexOutput(
            html=proto.text,
            latex=[
                ExtractedLatex(filename=l.filename, latex_body=l.latex_body)
                for l in proto.latex
            ],
        )


def on_card_did_render(
    output: TemplateRenderOutput, ctx: TemplateRenderContext
) -> None:
    # Note: [tikz]…[/tikz] tags are NOT rewritten here — they're handled at
    # display time by aqt/diagrams.py via gui_hooks.card_will_show, which
    # renders them with TikZJax in the reviewer webview (no LaTeX install
    # required). The tikz preamble injection in _save_latex_image still kicks
    # in if a user explicitly uses [latex]\begin{tikzpicture}…[/latex] AND has
    # a working LaTeX install.
    output.question_text = render_latex(
        output.question_text, ctx.note_type(), ctx.col()
    )
    output.answer_text = render_latex(output.answer_text, ctx.note_type(), ctx.col())


def render_latex(
    html: str, model: NotetypeDict, col: anki.collection.Collection
) -> str:
    "Convert embedded latex tags in text to image links."
    html, err = render_latex_returning_errors(html, model, col)
    if err:
        html += "\n".join(err)
    return html


def render_latex_returning_errors(
    html: str,
    model: NotetypeDict,
    col: anki.collection.Collection,
    expand_clozes: bool = False,
) -> tuple[str, list[str]]:
    """Returns (text, errors).

    errors will be non-empty if LaTeX failed to render."""
    svg = model.get("latexsvg", False)
    header = model["latexPre"]
    footer = model["latexPost"]

    proto = col._backend.extract_latex(text=html, svg=svg, expand_clozes=expand_clozes)
    out = ExtractedLatexOutput.from_proto(proto)
    errors = []
    html = out.html
    render_latex = col.get_config_bool(Config.Bool.RENDER_LATEX)

    for latex in out.latex:
        # don't need to render?
        if col.media.have(latex.filename):
            continue
        if not render_latex:
            errors.append(col.tr.preferences_latex_generation_disabled())
            return html, errors

        err = _save_latex_image(col, latex, header, footer, svg)
        if err is not None:
            errors.append(err)

    return html, errors


def _save_latex_image(
    col: anki.collection.Collection,
    extracted: ExtractedLatex,
    header: str,
    footer: str,
    svg: bool,
) -> str | None:
    # Inject tikz preamble on demand so existing note types render TikZ
    # without requiring a manual edit to latexPre.
    if _needs_tikz(extracted.latex_body):
        header = _inject_tikz_preamble(header)
    # add header/footer
    latex = f"{header}\n{extracted.latex_body}\n{footer}"

    # commands to use
    if svg:
        latex_cmds = svgCommands
        ext = "svg"
    else:
        latex_cmds = pngCommands
        ext = "png"

    # write into a temp file
    log = open(namedtmp("latex_log.txt"), "w", encoding="utf8")
    texpath = namedtmp("tmp.tex")
    texfile = open(texpath, "w", encoding="utf8")
    texfile.write(latex)
    texfile.close()
    oldcwd = os.getcwd()
    png_or_svg = namedtmp(f"tmp.{ext}")
    try:
        # generate png/svg
        os.chdir(tmpdir())
        for latex_cmd in latex_cmds:
            if call(latex_cmd, stdout=log, stderr=log):
                return _err_msg(col, latex_cmd[0], texpath)
        # add to media
        with open(png_or_svg, "rb") as file:
            data = file.read()
        col.media.write_data(extracted.filename, data)
        os.unlink(png_or_svg)
        return None
    finally:
        os.chdir(oldcwd)
        log.close()


def _err_msg(col: anki.collection.Collection, type: str, texpath: str) -> str:
    msg = f"{col.tr.media_error_executing(val=type)}<br>"
    msg += f"{col.tr.media_generated_file(val=texpath)}<br>"
    try:
        with open(namedtmp("latex_log.txt", remove=False), encoding="utf8") as file:
            log = file.read()
        if not log:
            raise Exception()
        msg += f"<small><pre>{html.escape(log)}</pre></small>"
    except Exception:
        msg += col.tr.media_have_you_installed_latex_and_dvipngdvisvgm()
    return msg


def setup_hook() -> None:
    hooks.card_did_render.append(on_card_did_render)
