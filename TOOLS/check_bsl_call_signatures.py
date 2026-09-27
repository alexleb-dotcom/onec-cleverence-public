#!/usr/bin/env python3
"""Cross-module BSL call-signature verifier.

The checker builds exported procedure/function signatures from exact source snapshots
(compare archives and BSP/common-module archives) and validates qualified calls of the
form Module.Method(...). It is intentionally conservative: only modules for which the
actual declaration is available are checked; unknown modules are reported separately,
never guessed from memory.
"""
from __future__ import annotations
from pathlib import Path
import argparse, json, re, zipfile

NAME = r"[A-Za-zА-Яа-яЁё_][A-Za-zА-Яа-яЁё0-9_]*"


def decode_bytes(data: bytes) -> str:
    for enc in ("utf-8-sig", "utf-8", "cp1251"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            pass
    return data.decode("utf-8", errors="replace")


def split_args(text: str) -> list[str]:
    if not text.strip():
        return []
    out, cur = [], []
    depth = 0
    in_string = False
    i = 0
    while i < len(text):
        c = text[i]
        if c == '"':
            cur.append(c)
            if in_string and i + 1 < len(text) and text[i + 1] == '"':
                cur.append('"'); i += 2; continue
            in_string = not in_string
        elif not in_string:
            if c in "([{" : depth += 1
            elif c in ")]}": depth = max(0, depth - 1)
            elif c == ',' and depth == 0:
                out.append(''.join(cur).strip()); cur = []
            else:
                cur.append(c)
        else:
            cur.append(c)
        i += 1
    out.append(''.join(cur).strip())
    return [x for x in out if x]


def find_matching_paren(text: str, open_pos: int) -> int | None:
    depth = 0
    in_string = False
    i = open_pos
    while i < len(text):
        c = text[i]
        if c == '"':
            if in_string and i + 1 < len(text) and text[i + 1] == '"':
                i += 2; continue
            in_string = not in_string
        elif not in_string:
            if c == '(':
                depth += 1
            elif c == ')':
                depth -= 1
                if depth == 0:
                    return i
        i += 1
    return None


def strip_comment_strings(text: str) -> str:
    """Mask strings and // comments while preserving positions/newlines."""
    chars = list(text)
    in_string = False
    i = 0
    while i < len(chars):
        if not in_string and chars[i] == '/' and i + 1 < len(chars) and chars[i + 1] == '/':
            while i < len(chars) and chars[i] not in '\r\n':
                chars[i] = ' '; i += 1
            continue
        if chars[i] == '"':
            if in_string and i + 1 < len(chars) and chars[i + 1] == '"':
                chars[i] = chars[i + 1] = ' '; i += 2; continue
            in_string = not in_string
            chars[i] = ' '; i += 1; continue
        if in_string and chars[i] not in '\r\n':
            chars[i] = ' '
        i += 1
    return ''.join(chars)


def declaration_is_exported(text: str, close_pos: int) -> bool:
    """Accept only the Export token that belongs to the declaration suffix.

    Searching an arbitrary tail after ')' is unsafe: a private routine can contain the
    word 'Экспорт' in its body/comment and be accidentally promoted to public API.
    In BSL the export modifier belongs to the declaration line after the closing ')'.
    """
    line_end = len(text)
    for sep in ('\r', '\n'):
        pos = text.find(sep, close_pos + 1)
        if pos >= 0:
            line_end = min(line_end, pos)
    suffix = text[close_pos + 1:line_end]
    suffix = suffix.split('//', 1)[0]
    return bool(re.match(r"^[ \t]*Экспорт\b", suffix, re.IGNORECASE))


def extract_interface_comment(text: str, declaration_start: int) -> str:
    """Return the contiguous // comment block immediately above a declaration.

    The value is exact-source evidence captured into the ephemeral local index. It is
    intentionally not summarized or promoted into a reusable public reference catalog.
    """
    before = text[:declaration_start]
    lines = before.splitlines()
    collected = []
    for line in reversed(lines):
        stripped = line.strip()
        if not stripped.startswith('//'):
            break
        value = stripped[2:]
        if value.startswith(' '):
            value = value[1:]
        collected.append(value)
    collected.reverse()
    return '\n'.join(collected).strip()


def parse_signatures(text: str, module: str, source: str) -> dict[tuple[str, str], dict]:
    out = {}
    rx = re.compile(rf"(?im)^\s*(Процедура|Функция)\s+({NAME})\s*\(")
    for m in rx.finditer(text):
        open_pos = text.find('(', m.start())
        close_pos = find_matching_paren(text, open_pos)
        if close_pos is None:
            continue
        # Cross-module calls are only valid for exports, so index exported signatures only.
        if not declaration_is_exported(text, close_pos):
            continue
        raw_params = text[open_pos + 1:close_pos]
        params = split_args(raw_params)
        required = 0
        parsed = []
        for p in params:
            name_part = p.split('=', 1)[0].strip()
            optional = '=' in p
            if not optional:
                required += 1
            parsed.append({"text": p, "name": name_part, "optional": optional})
        out[(module.casefold(), m.group(2).casefold())] = {
            "module": module,
            "name": m.group(2),
            "kind": m.group(1),
            "required": required,
            "total": len(params),
            "params": parsed,
            "interface_comment": extract_interface_comment(text, m.start()),
            "source": source,
            "line": text.count('\n', 0, m.start()) + 1,
        }
    return out


def module_from_path(path: str) -> str | None:
    p = path.replace('\\', '/')
    m = re.search(r"(?:^|/)CommonModules/([^/]+)/Ext/Module\.bsl$", p, re.I)
    if m:
        return m.group(1)
    name = Path(p).name
    if name.endswith('_Module.bsl'):
        return name[:-len('_Module.bsl')]
    return None


def load_definitions(zips: list[Path], files: list[Path]) -> dict:
    sigs = {}
    for zp in zips:
        with zipfile.ZipFile(zp, 'r') as z:
            for n in z.namelist():
                module = module_from_path(n)
                if not module or not n.lower().endswith('.bsl'):
                    continue
                try:
                    text = decode_bytes(z.read(n))
                except Exception:
                    continue
                sigs.update(parse_signatures(text, module, f"{zp}:{n}"))
    for fp in files:
        module = module_from_path(str(fp))
        if module:
            sigs.update(parse_signatures(decode_bytes(fp.read_bytes()), module, str(fp)))
    return sigs


def parse_calls(text: str, known_modules: set[str], source: str) -> list[dict]:
    masked = strip_comment_strings(text)
    out = []
    rx = re.compile(rf"\b({NAME})\.({NAME})\s*\(")
    for m in rx.finditer(masked):
        module, method = m.group(1), m.group(2)
        if module.casefold() not in known_modules:
            continue
        open_pos = masked.find('(', m.start())
        close_pos = find_matching_paren(masked, open_pos)
        if close_pos is None:
            continue
        # Use original text for argument splitting, because masked strings may contain commas.
        args = split_args(text[open_pos + 1:close_pos])
        out.append({
            "module": module,
            "method": method,
            "arg_count": len(args),
            "args": args,
            "source": source,
            "line": text.count('\n', 0, m.start()) + 1,
        })
    return out


def check_signatures(zips: list[Path], def_files: list[Path], focus: list[Path]) -> dict:
    sigs = load_definitions(zips, def_files)
    known_modules = {key[0] for key in sigs}
    findings = []
    checked = []
    unresolved = []
    for fp in focus:
        text = decode_bytes(fp.read_bytes())
        for call in parse_calls(text, known_modules, str(fp)):
            key = (call['module'].casefold(), call['method'].casefold())
            sig = sigs.get(key)
            if sig is None:
                unresolved.append(call)
                continue
            checked.append({"call": call, "signature": sig})
            if not (sig['required'] <= call['arg_count'] <= sig['total']):
                findings.append({
                    "severity": "HIGH",
                    "type": "CALL_SIGNATURE_MISMATCH",
                    "call": call,
                    "signature": sig,
                    "expected": f"{sig['required']}..{sig['total']}",
                    "actual": call['arg_count'],
                })
    return {
        "result": "PASS" if not findings else "FAIL",
        "definitions": len(sigs),
        "checked_calls": len(checked),
        "unresolved_known_module_calls": unresolved,
        "findings": findings,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--definitions-zip', action='append', default=[])
    ap.add_argument('--definitions-file', action='append', default=[])
    ap.add_argument('--focus', action='append', required=True)
    ap.add_argument('--output')
    args = ap.parse_args()

    zips = [Path(x) for x in args.definitions_zip]
    def_files = [Path(x) for x in args.definitions_file]
    focus = [Path(x) for x in args.focus]
    result = check_signatures(zips, def_files, focus)
    out = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(out + '\n', encoding='utf-8')
    print(out)
    return 0 if result["result"] == "PASS" else 2


if __name__ == '__main__':
    raise SystemExit(main())