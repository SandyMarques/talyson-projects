"""Checagens do portfólio estático (`site/`), conforme o AGENTS.md.

1. HTML bem formado: toda tag aberta é fechada, na ordem certa.
2. JavaScript embutido válido (`node --check` em cada <script> inline).
3. Links e arquivos internos (href/src relativos) existem.
4. Bibliotecas de unpkg/jsdelivr com versão fixa e `integrity` (SRI).

Uso: python scripts/check_site.py [pasta]   (padrão: site)
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlparse

VOID_TAGS = {
    "area", "base", "br", "col", "embed", "hr", "img", "input", "link",
    "meta", "param", "source", "track", "wbr",
}
# Tags cujo fechamento o HTML permite omitir.
OPTIONAL_CLOSE = {"li", "p", "option", "tr", "td", "th", "dt", "dd", "thead", "tbody"}
VERSIONED_CDNS = ("unpkg.com", "cdn.jsdelivr.net")
NON_JS_TYPES = {"application/ld+json", "application/json", "text/template", "text/markdown"}


class SiteParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[tuple[str, int]] = []
        self.errors: list[str] = []
        self.refs: list[tuple[str, int]] = []
        self.cdn_scripts: list[tuple[dict, int]] = []
        self.inline_scripts: list[tuple[str, int]] = []
        self._in_js: int | None = None
        self._js_buf: list[str] = []

    def handle_starttag(self, tag, attrs):
        line = self.getpos()[0]
        a = {k: (v or "") for k, v in attrs}
        for attr in ("href", "src"):
            if a.get(attr):
                self.refs.append((a[attr], line))
        if tag == "script":
            if a.get("src"):
                self.cdn_scripts.append((a, line))
            elif a.get("type", "").lower() not in NON_JS_TYPES:
                self._in_js = line
                self._js_buf = []
        if tag not in VOID_TAGS:
            self.stack.append((tag, line))

    def handle_startendtag(self, tag, attrs):
        # <tag/> — registra referências sem empilhar.
        line = self.getpos()[0]
        for k, v in attrs:
            if k in ("href", "src") and v:
                self.refs.append((v, line))

    def handle_data(self, data):
        if self._in_js is not None:
            self._js_buf.append(data)

    def handle_endtag(self, tag):
        line = self.getpos()[0]
        if tag == "script" and self._in_js is not None:
            self.inline_scripts.append(("".join(self._js_buf), self._in_js))
            self._in_js = None
        if tag in VOID_TAGS:
            return
        while self.stack and self.stack[-1][0] != tag and self.stack[-1][0] in OPTIONAL_CLOSE:
            self.stack.pop()
        if self.stack and self.stack[-1][0] == tag:
            self.stack.pop()
        else:
            aberta = f"<{self.stack[-1][0]}> da linha {self.stack[-1][1]}" if self.stack else "nada"
            self.errors.append(f"linha {line}: </{tag}> fecha {aberta}")


def check_file(path: Path, root: Path, node: str | None) -> list[str]:
    parser = SiteParser()
    parser.feed(path.read_text(encoding="utf-8"))
    parser.close()
    errors = list(parser.errors)
    errors += [
        f"linha {line}: <{tag}> nunca foi fechada"
        for tag, line in parser.stack
        if tag not in OPTIONAL_CLOSE
    ]

    for ref, line in parser.refs:
        parsed = urlparse(ref)
        if parsed.scheme or ref.startswith(("#", "//", "mailto:", "tel:", "data:", "javascript:")):
            continue
        target_path = unquote(parsed.path)
        if not target_path:
            continue
        target = (path.parent / target_path).resolve()
        if not target.exists() or root.resolve() not in [target, *target.parents]:
            errors.append(f"linha {line}: referência interna inexistente: {ref}")

    for attrs, line in parser.cdn_scripts:
        src = attrs["src"]
        host = urlparse(src).netloc
        if host in VERSIONED_CDNS:
            if not re.search(r"@\d+\.\d+\.\d+", src):
                errors.append(f"linha {line}: biblioteca sem versão fixa: {src}")
            if not attrs.get("integrity"):
                errors.append(f"linha {line}: biblioteca sem integrity (SRI): {src}")

    if node:
        with tempfile.TemporaryDirectory() as tmp:
            for i, (code, line) in enumerate(parser.inline_scripts):
                js = Path(tmp) / f"script_{i}.js"
                js.write_text(code, encoding="utf-8")
                result = subprocess.run([node, "--check", str(js)], capture_output=True, text=True)
                if result.returncode != 0:
                    linhas = result.stderr.strip().splitlines()
                    detalhe = next((l for l in linhas if "Error" in l), "erro de sintaxe")
                    errors.append(f"linha {line}: JavaScript inválido: {detalhe}")
    return errors


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else "site")
    node = shutil.which("node")
    if not node:
        print("aviso: node não encontrado; checagem de JavaScript ignorada")
    total = 0
    for html in sorted(root.rglob("*.html")):
        errors = check_file(html, root, node)
        status = "OK" if not errors else f"{len(errors)} problema(s)"
        print(f"{html}: {status}")
        for e in errors:
            print(f"  - {e}")
        total += len(errors)
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())
