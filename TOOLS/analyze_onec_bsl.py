#!/usr/bin/env python3
# Heuristic 1C BSL/query topology analyzer.
# It is intentionally conservative: unresolved types are findings, not silently classified as safe.

from pathlib import Path
import re, json, argparse

DEF_RE = re.compile(r'(?im)^\s*(?:Асинх\s+)?(Функция|Процедура)\s+([A-Za-zА-Яа-я_][\wА-Яа-я]*)\s*\(([^)]*)\)([^\r\n]*)')
ROUTINE_HEADER_HINT_RE = re.compile(r'(?im)^\s*(?:Асинх\s+)?(?:Функция|Процедура)\b')
END_RE = re.compile(r'(?im)^\s*Конец(Функции|Процедуры)\b')
EXECUTION_DIRECTIVE_RE = re.compile(r'(?im)^\s*&(?P<directive>НаКлиентеНаСервереБезКонтекста|НаСервереБезКонтекста|НаСервере|НаКлиенте)\s*$')

def decode(path):
    b = Path(path).read_bytes()
    return b.decode("utf-8-sig", errors="replace")

def _formal_parameter_name(raw):
    value=raw.strip().split("=",1)[0].strip()
    return re.sub(r'(?i)^Знач\s+','',value).strip()

def blocks(text):
    defs = list(DEF_RE.finditer(text))
    out = []
    for i, m in enumerate(defs):
        start = m.start()
        prefix_start = defs[i-1].end() if i else 0
        directives = list(EXECUTION_DIRECTIVE_RE.finditer(text[prefix_start:start]))
        execution_context = directives[-1].group("directive") if directives else "UNRESOLVED"
        end = defs[i+1].start() if i+1 < len(defs) else len(text)
        tail = text[start:end]
        em = END_RE.search(tail)
        if em:
            end = start + em.end()
        out.append({
            "kind": m.group(1),
            "name": m.group(2),
            "params": [_formal_parameter_name(x) for x in m.group(3).split(",") if x.strip()],
            "export": "Экспорт" in m.group(4),
            "execution_context": execution_context,
            "text": text[start:end],
            "start_line": text.count("\n", 0, start) + 1,
        })
    return out

def query_segments(block_text):
    # Collect multiline 1C query strings including the first line (e.g. "ВЫБРАТЬ ПЕРВЫЕ 1").
    # Older logic collected only lines beginning with | and could miss semantics present on the first line.
    segs, cur = [], []
    for line in block_text.splitlines():
        stripped = line.strip()
        if not cur:
            starts_query = bool(re.search(r'["\']\s*(?:ВЫБРАТЬ|СОЗДАТЬ|УНИЧТОЖИТЬ)\b', stripped, re.I))
            pipe_line = bool(re.search(r'["\']\s*\|', line) or line.lstrip().startswith("|") or re.search(r'^\s*\|\s*', line))
            if starts_query or pipe_line:
                cur.append(line)
                if line.rstrip().endswith('";'):
                    segs.append("\n".join(cur))
                    cur = []
        else:
            cur.append(line)
            if line.rstrip().endswith('";'):
                segs.append("\n".join(cur))
                cur = []
    if cur:
        segs.append("\n".join(cur))
    return segs


_BSL_IDENT = r'[A-Za-zА-Яа-яЁё_][\wА-Яа-яЁё]*'
_ASSIGNMENT_START_RE = re.compile(
    rf'(?im)^[ \t]*(?P<lhs>{_BSL_IDENT}(?:[ \t]*\.[ \t]*{_BSL_IDENT})?)[ \t]*=[ \t]*'
)

def _statement_end(text, start):
    """Return the first semicolon outside BSL strings/comments."""
    i=start; in_string=False; line_comment=False
    while i < len(text):
        ch=text[i]
        if line_comment:
            if ch in "\r\n":line_comment=False
            i+=1; continue
        if in_string:
            if ch=='"':
                if i+1 < len(text) and text[i+1]=='"':
                    i+=2; continue
                in_string=False
            i+=1; continue
        if ch=='"':
            in_string=True; i+=1; continue
        if ch=='/' and i+1 < len(text) and text[i+1]=='/':
            line_comment=True; i+=2; continue
        if ch==';':return i
        i+=1
    return len(text)

def _simple_assignments(text):
    """Collect bounded assignment statements without interpreting string contents."""
    out=[]
    for match in _ASSIGNMENT_START_RE.finditer(text):
        probe_start=max(text.rfind(";",0,match.start())+1,0)
        state_end=_statement_end(text,probe_start)
        if state_end < match.start():probe_start=state_end+1
        prefix=text[probe_start:match.start()]
        in_string=False; line_comment=False; i=0
        while i < len(prefix):
            ch=prefix[i]
            if line_comment:
                if ch in "\r\n":line_comment=False
                i+=1; continue
            if in_string:
                if ch=='"':
                    if i+1 < len(prefix) and prefix[i+1]=='"':i+=2; continue
                    in_string=False
                i+=1; continue
            if ch=='"':in_string=True; i+=1; continue
            if ch=='/' and i+1 < len(prefix) and prefix[i+1]=='/':
                line_comment=True; i+=2; continue
            i+=1
        if in_string or line_comment:continue
        end=_statement_end(text,match.end())
        lhs=re.sub(r'\s+','',match.group('lhs')).lower()
        out.append({
            "lhs":lhs,"rhs":text[match.end():end],"rhs_start":match.end(),
            "start":match.start(),"end":end,
        })
    return out

def _bsl_string_literals(expr, expr_start):
    """Decode BSL string literals and retain source offsets for each value char."""
    out=[]; i=0
    while i < len(expr):
        if expr[i]!='"':i+=1; continue
        i+=1; value=[]; positions=[]
        while i < len(expr):
            ch=expr[i]
            if ch=='"':
                if i+1 < len(expr) and expr[i+1]=='"':
                    value.append('"');positions.append(expr_start+i);i+=2;continue
                i+=1;break
            if ch in "\r\n":
                newline_start=i
                if ch=='\r' and i+1 < len(expr) and expr[i+1]=='\n':i+=2
                else:i+=1
                value.append('\n');positions.append(expr_start+newline_start)
                j=i
                while j < len(expr) and expr[j] in " \t":j+=1
                if j < len(expr) and expr[j]=='|':i=j+1
                continue
            value.append(ch);positions.append(expr_start+i);i+=1
        out.append(("".join(value),positions))
    return out

def _query_escape_hits(value, positions):
    """Find literal backslash+t/r/n outside query quoted literals/comments."""
    hits=[];quote=None;line_comment=False;block_comment=False;i=0
    while i < len(value):
        ch=value[i]
        if line_comment:
            if ch=='\n':line_comment=False
            i+=1;continue
        if block_comment:
            if ch=='*' and i+1 < len(value) and value[i+1]=='/':
                block_comment=False;i+=2;continue
            i+=1;continue
        if quote is not None:
            if ch==quote:
                if i+1 < len(value) and value[i+1]==quote:i+=2;continue
                quote=None
            i+=1;continue
        if ch in {'"',"'"}:quote=ch;i+=1;continue
        if ch=='/' and i+1 < len(value):
            if value[i+1]=='/':line_comment=True;i+=2;continue
            if value[i+1]=='*':block_comment=True;i+=2;continue
        if ch=='\\' and i+1 < len(value) and value[i+1] in "trn":
            hits.append((positions[i],"\\"+value[i+1]));i+=2;continue
        i+=1
    return hits

def _safe_line_fragment(text, offset, limit=120):
    start=text.rfind("\n",0,offset)+1;end=text.find("\n",offset)
    if end < 0:end=len(text)
    fragment=text[start:end].strip().replace("\r","")
    return fragment if len(fragment)<=limit else fragment[:limit-1]+"…"

def _query_constructor_sinks(text):
    """Return bounded Новый Запрос(<expression>) argument spans."""
    out=[]
    for match in re.finditer(r'(?i)\bНовый\s+Запрос\s*\(',text):
        i=match.end();depth=1;in_string=False;line_comment=False
        arg_start=i
        while i < len(text) and depth:
            ch=text[i]
            if line_comment:
                if ch in "\r\n":line_comment=False
                i+=1;continue
            if in_string:
                if ch=='"':
                    if i+1 < len(text) and text[i+1]=='"':i+=2;continue
                    in_string=False
                i+=1;continue
            if ch=='"':in_string=True;i+=1;continue
            if ch=='/' and i+1 < len(text) and text[i+1]=='/':
                line_comment=True;i+=2;continue
            if ch=='(':depth+=1
            elif ch==')':
                depth-=1
                if depth==0:break
            i+=1
        if depth==0:
            out.append({"rhs":text[arg_start:i],"rhs_start":arg_start,"start":match.start(),"end":i})
    return out

def query_literal_escape_findings(block):
    """Detect literal escape corruption only in expressions proven to feed query text."""
    text=block["text"];assignments=_simple_assignments(text)
    query_receivers=set();aliases={}

    for row in assignments:
        lhs=row["lhs"];rhs=row["rhs"]
        if "." not in lhs and re.match(r'(?is)^\s*Новый\s+Запрос\b',rhs):
            query_receivers.add(lhs)
        if "." not in lhs:
            m=re.fullmatch(r'\s*('+_BSL_IDENT+r')\s*',rhs)
            if m:aliases[lhs]=m.group(1).lower()

    changed=True
    while changed:
        changed=False
        for alias,source in aliases.items():
            if source in query_receivers and alias not in query_receivers:
                query_receivers.add(alias);changed=True

    def is_assignment_sink(row):
        lhs=row["lhs"]
        if lhs=="текстзапроса":return True
        if "." not in lhs:return False
        receiver,member=lhs.split(".",1)
        return member=="текст" and receiver in query_receivers

    by_name={}
    for row in assignments:
        if "." not in row["lhs"]:by_name.setdefault(row["lhs"],[]).append(row)

    def latest_assignment(name,before):
        rows=[x for x in by_name.get(name,[]) if x["start"]<before]
        return rows[-1] if rows else None

    def resolve_strings(row,depth=0,seen=None):
        if row is None or depth>6:return []
        # Literal/concatenated expressions are evaluated as all BSL literal segments.
        literals=_bsl_string_literals(row["rhs"],row["rhs_start"])
        if literals:return literals
        m=re.fullmatch(r'\s*('+_BSL_IDENT+r')\s*',row["rhs"])
        if not m:return []
        name=m.group(1).lower();seen=set() if seen is None else set(seen)
        if name in seen:return []
        seen.add(name)
        return resolve_strings(latest_assignment(name,row["start"]),depth+1,seen)

    sinks=[row for row in assignments if is_assignment_sink(row)]
    # Constructor arguments are query sinks themselves, including direct literals,
    # concatenations and variable expressions.
    sinks.extend(_query_constructor_sinks(text))

    found=[];seen=set()
    for sink in sinks:
        for value,positions in resolve_strings(sink):
            for offset,sequence in _query_escape_hits(value,positions):
                key=(offset,sequence)
                if key in seen:continue
                seen.add(key)
                finding={
                    "severity":"HIGH","type":"QUERY_LITERAL_ESCAPE_CORRUPTION",
                    "line":block["start_line"]+text.count("\n",0,offset),
                    "sequence":sequence,"fragment":_safe_line_fragment(text,offset),
                    "note":"Literal backslash escape-like pair is in query-language token/whitespace position. BSL does not interpret it as query indentation or a line break; inspect exact final source bytes.",
                }
                finding["function" if str(block.get("kind","")).lower()=="функция" else "procedure"]=block["name"]
                found.append(finding)
    return found

def known_reference_vars(block):
    refs = set()
    # Strong type evidence only.
    for m in re.finditer(r'ТипЗнч\((\w+)\)\s*=\s*Тип\("([^"]*Ссылка[^"]*)"\)', block["text"], re.I):
        refs.add(m.group(1))
    for m in re.finditer(r'Тип\("([^"]*Ссылка[^"]*)"\)\s*=\s*ТипЗнч\((\w+)\)', block["text"], re.I):
        refs.add(m.group(2))
    return refs

def loop_execute_findings(block):
    stack = []
    findings = []
    for offset, line in enumerate(block["text"].splitlines(), 0):
        s = line.strip()
        if re.match(r'(?i)^(Для\s+Каждого|Для\s+\w+\s*=|Пока\b)', s):
            stack.append(block["start_line"] + offset)
        if (".Выполнить()" in s or ".ВыполнитьПакет()" in s) and stack:
            findings.append({"line": block["start_line"] + offset, "loop_start": stack[-1], "code": s})
        if re.match(r'(?i)^КонецЦикла\b', s) and stack:
            stack.pop()
    return findings

def structure_property_out_param_boolean_findings(block):
    """Detect bounded Structure.Property out-param Boolean hazards.

    HIGH/blocking classification requires a bounded local proof that the receiver
    is Structure-like: either an exact local `Новый Структура` assignment or an
    active exact `ТипЗнч(receiver) = Тип("Структура")` guard. A syntactically
    generic `.Свойство(..., outVar)` method name alone is REVIEW-only and does
    not inherit the platform Structure absent-key contract.

    For a proven Structure receiver, a simple out identifier remains unsafe for
    bare Boolean consumption until an unconditional reassignment/normalization or
    while an exact Boolean type guard is active in the current reachable branch.
    Guard facts are cleared/replaced on Иначе/ИначеЕсли. Presence is not value-domain proof.
    """
    masked_lines=_mask_bsl_strings_and_comments(block["text"]).splitlines()
    raw_lines=block["text"].splitlines()
    tracked={}
    boolean_guard_stack=[]
    structure_guard_stack=[]
    structure_vars=set()

    ident=r'[A-Za-zА-Яа-яЁё_][\wА-Яа-яЁё]*'
    out_call_re=re.compile(
        rf'(?P<receiver>{ident})\s*\.\s*Свойство\s*\(\s*[^,\n]+,\s*(?P<out>{ident})\s*\)',
        re.I,
    )
    assignment_re=re.compile(rf'^\s*(?P<lhs>{ident})\s*=\s*(?P<rhs>.*?)\s*;?\s*$')
    bare_bool_re=re.compile(
        rf'^\s*(?:Если|ИначеЕсли)\s+(?:НЕ\s+)?\(?\s*(?P<var>{ident})\s*\)?\s+Тогда\b',
        re.I,
    )
    boolean_guard_re=re.compile(
        rf'(?:ТипЗнч\s*\(\s*(?P<a>{ident})\s*\)\s*=\s*Тип\s*\(\s*"Булево"\s*\)'
        rf'|Тип\s*\(\s*"Булево"\s*\)\s*=\s*ТипЗнч\s*\(\s*(?P<b>{ident})\s*\))',
        re.I,
    )
    structure_guard_re=re.compile(
        rf'(?:ТипЗнч\s*\(\s*(?P<a>{ident})\s*\)\s*=\s*Тип\s*\(\s*"Структура"\s*\)'
        rf'|Тип\s*\(\s*"Структура"\s*\)\s*=\s*ТипЗнч\s*\(\s*(?P<b>{ident})\s*\))',
        re.I,
    )
    simple_ident_re=re.compile(rf'^\s*(?P<var>{ident})\s*$')
    new_structure_re=re.compile(r'^\s*Новый\s+Структура\b',re.I)

    findings=[]
    seen=set()
    for offset, masked in enumerate(masked_lines):
        raw=raw_lines[offset] if offset<len(raw_lines) else masked
        stripped=masked.strip()
        raw_code=raw.split("//",1)[0]
        branch_text=raw_code.strip()
        is_if=bool(re.match(r'(?i)^\s*Если\b',branch_text))
        is_elseif=bool(re.match(r'(?i)^\s*ИначеЕсли\b',branch_text))
        is_else=bool(re.match(r'(?i)^\s*Иначе\b',branch_text))
        is_endif=bool(re.match(r'(?i)^\s*КонецЕсли\b',stripped))

        # Guard facts are branch-local. On Else/ElseIf the previous branch is
        # false and its exact type guards must not leak into the new branch.
        # This is deliberately a bounded If-branch stack, not a generic CFG.
        if is_endif or is_elseif or is_else:
            if boolean_guard_stack:
                boolean_guard_stack.pop()
            if structure_guard_stack:
                structure_guard_stack.pop()

        active_boolean_guards=set().union(*boolean_guard_stack) if boolean_guard_stack else set()
        active_structure_guards=set().union(*structure_guard_stack) if structure_guard_stack else set()

        current_structure_guards=set()
        if is_if or is_elseif:
            for gm in structure_guard_re.finditer(raw_code):
                gv=gm.group("a") or gm.group("b")
                if gv:
                    current_structure_guards.add(gv.lower())
        structure_proof_scope=active_structure_guards|current_structure_guards

        assign=assignment_re.match(masked)
        if assign and not re.match(r'(?i)^\s*(?:Если|ИначеЕсли)\b',stripped):
            lhs=assign.group("lhs")
            rhs=assign.group("rhs").strip()
            lhs_key=lhs.lower()
            if not boolean_guard_stack:
                if new_structure_re.match(rhs):
                    structure_vars.add(lhs_key)
                else:
                    structure_vars.discard(lhs_key)

        for call in out_call_re.finditer(masked):
            receiver=call.group("receiver")
            receiver_key=receiver.lower()
            var=call.group("out")
            receiver_proven=receiver_key in structure_vars or receiver_key in structure_proof_scope
            tracked[var.lower()]={
                "source_line":block["start_line"]+offset,
                "out_var":var,
                "receiver":receiver,
                "receiver_proven_structure":receiver_proven,
                "receiver_proof":(
                    "LOCAL_NEW_STRUCTURE"
                    if receiver_key in structure_vars
                    else ("ACTIVE_TYPE_GUARD" if receiver_key in structure_proof_scope else "UNRESOLVED")
                ),
            }

        if assign and not re.match(r'(?i)^\s*(?:Если|ИначеЕсли)\b',stripped):
            lhs=assign.group("lhs")
            rhs=assign.group("rhs").strip()
            lhs_key=lhs.lower()
            rhs_ident=simple_ident_re.match(rhs)
            if not boolean_guard_stack:
                if rhs_ident and rhs_ident.group("var").lower() in tracked:
                    tracked[lhs_key]=dict(tracked[rhs_ident.group("var").lower()])
                    tracked[lhs_key]["alias"]=lhs
                elif lhs_key in tracked:
                    # Any unconditional overwrite ends the exact out-param value flow.
                    tracked.pop(lhs_key,None)

        bare=bare_bool_re.match(masked)
        if bare:
            var=bare.group("var")
            key=var.lower()
            if key in tracked and key not in active_boolean_guards:
                src=tracked[key]
                identity=(block["start_line"]+offset,key,src["source_line"],src["receiver_proven_structure"])
                if identity not in seen:
                    seen.add(identity)
                    if src["receiver_proven_structure"]:
                        findings.append({
                            "severity":"HIGH",
                            "type":"STRUCTURE_PROPERTY_OUT_PARAM_UNSAFE_BOOLEAN",
                            "procedure":block["name"],
                            "line":block["start_line"]+offset,
                            "source_line":src["source_line"],
                            "out_var":var,
                            "receiver":src.get("receiver"),
                            "receiver_proof":src.get("receiver_proof"),
                            "code":raw.strip()[:220],
                            "note":"Proven Structure-like .Свойство(..., outVar) presence does not prove the out value is Boolean. Normalize the exact local value to Boolean, guard the consumption with a proven Boolean type contract, or resolve the exact machine-finding obligation with valid source/semantic proof of the Boolean value contract.",
                        })
                    else:
                        findings.append({
                            "severity":"REVIEW",
                            "type":"STRUCTURE_PROPERTY_RECEIVER_TYPE_REVIEW",
                            "procedure":block["name"],
                            "line":block["start_line"]+offset,
                            "source_line":src["source_line"],
                            "out_var":var,
                            "receiver":src.get("receiver"),
                            "receiver_proof":"UNRESOLVED",
                            "code":raw.strip()[:220],
                            "note":"A generic .Свойство(..., outVar) method name is followed by bare Boolean consumption, but this bounded analyzer has not proven the receiver is a platform Structure. Review the receiver/API contract; do not apply Structure absent-key semantics from the method name alone.",
                        })

        current_boolean_guards=set()
        if is_if or is_elseif:
            for gm in boolean_guard_re.finditer(raw_code):
                gv=gm.group("a") or gm.group("b")
                if gv and gv.lower() in tracked:
                    current_boolean_guards.add(gv.lower())
        if is_if or is_elseif or is_else:
            # Keep one frame for every active branch. Else gets an empty frame,
            # explicitly proving that the prior true-branch guards are absent.
            boolean_guard_stack.append(current_boolean_guards)
            structure_guard_stack.append(current_structure_guards)

    return findings

def value_table_tri_state_boolean_findings(block):
    """Bounded local ValueTable tri-state Boolean detector."""
    raw_lines=block["text"].splitlines()
    ident=r'[A-Za-zА-Яа-яЁё_][\wА-Яа-яЁё]*'
    table_new_re=re.compile(rf'^\s*(?P<table>{ident})\s*=\s*Новый\s+ТаблицаЗначений\b',re.I)
    column_re=re.compile(rf'(?P<table>{ident})\s*\.\s*Колонки\s*\.\s*Добавить\s*\(\s*"(?P<col>[^"]+)"(?P<tail>.*)$',re.I)
    add_re=re.compile(rf'^\s*(?P<row>{ident})\s*=\s*(?P<table>{ident})\s*\.\s*Добавить\s*\(\s*\)',re.I)
    row_assign_re=re.compile(rf'^\s*(?P<row>{ident})\s*\.\s*(?P<col>{ident})\s*=\s*(?P<rhs>.*?)\s*;?\s*$',re.I)
    loop_re=re.compile(rf'^\s*Для\s+Каждого\s+(?P<row>{ident})\s+Из\s+(?P<table>{ident})\s+Цикл\b',re.I)
    bare_re=re.compile(rf'^\s*(?:Если|ИначеЕсли)\s+(?:НЕ\s+)?(?P<row>{ident})\s*\.\s*(?P<col>{ident})\s+Тогда\b',re.I)
    bool_guard_re=re.compile(
        rf'(?:ТипЗнч\s*\(\s*(?P<r1>{ident})\s*\.\s*(?P<c1>{ident})\s*\)\s*=\s*Тип\s*\(\s*"Булево"\s*\)'
        rf'|Тип\s*\(\s*"Булево"\s*\)\s*=\s*ТипЗнч\s*\(\s*(?P<r2>{ident})\s*\.\s*(?P<c2>{ident})\s*\))',
        re.I,
    )

    tables={}
    row_events={}
    active_loop=None
    if_guard_stack=[]
    findings=[]

    def bool_rhs(rhs):
        value=str(rhs or "").strip().rstrip(";")
        return bool(
            re.fullmatch(r'(?i)(Истина|Ложь)',value)
            or (value.startswith("?(") and "Ложь" in value and ("Истина" in value or "Тип(\"Булево\")" in value))
            or re.match(r'(?i)^Булево\s*\(',value)
        )

    for offset,raw in enumerate(raw_lines):
        code=raw.split("//",1)[0].strip()
        if not code:
            continue
        m=table_new_re.match(code)
        if m:
            tables[m.group("table").lower()]={"name":m.group("table"),"columns":{},"events":[]}
            continue
        m=column_re.search(code)
        if m and m.group("table").lower() in tables:
            table=tables[m.group("table").lower()]
            table["columns"][m.group("col").lower()]={
                "name":m.group("col"),
                "boolean_typed":bool(re.search(r'(?i)\bБулево\b',m.group("tail") or "")),
                "line":block["start_line"]+offset,
            }
            continue
        m=add_re.match(code)
        if m and m.group("table").lower() in tables:
            event={"table":m.group("table").lower(),"initialized":set(),"line":block["start_line"]+offset}
            tables[event["table"]]["events"].append(event)
            row_events[m.group("row").lower()]=event
            continue
        m=row_assign_re.match(code)
        if m:
            row_key=m.group("row").lower()
            col_key=m.group("col").lower()
            if row_key in row_events and bool_rhs(m.group("rhs")):
                row_events[row_key]["initialized"].add(col_key)
            if active_loop and row_key==active_loop["row"] and bool_rhs(m.group("rhs")):
                active_loop["normalized"].add(col_key)

        if re.match(r'(?i)^КонецЦикла\b',code):
            active_loop=None
            if_guard_stack=[]
            continue
        lm=loop_re.match(code)
        if lm and lm.group("table").lower() in tables:
            active_loop={"row":lm.group("row").lower(),"table":lm.group("table").lower(),"normalized":set()}
            if_guard_stack=[]
            continue
        if active_loop is None:
            continue

        is_if=bool(re.match(r'(?i)^Если\b',code))
        is_elseif=bool(re.match(r'(?i)^ИначеЕсли\b',code))
        is_else=bool(re.match(r'(?i)^Иначе\b',code))
        is_endif=bool(re.match(r'(?i)^КонецЕсли\b',code))
        if is_endif or is_elseif or is_else:
            if if_guard_stack:
                if_guard_stack.pop()
        active_guards=set().union(*if_guard_stack) if if_guard_stack else set()
        current_guards=set()
        if is_if or is_elseif:
            for gm in bool_guard_re.finditer(code):
                row=(gm.group("r1") or gm.group("r2") or "").lower()
                col=(gm.group("c1") or gm.group("c2") or "").lower()
                if row==active_loop["row"] and col:
                    current_guards.add(col)

        bm=bare_re.match(code)
        if bm and bm.group("row").lower()==active_loop["row"]:
            col=bm.group("col").lower()
            table=tables[active_loop["table"]]
            schema=table["columns"].get(col)
            if schema is not None:
                all_initialized=bool(table["events"]) and all(col in event["initialized"] for event in table["events"])
                safe=(schema["boolean_typed"] and all_initialized) or col in active_loop["normalized"] or col in active_guards or col in current_guards
                if not safe:
                    findings.append({
                        "severity":"HIGH",
                        "type":"VALUE_TABLE_TRI_STATE_BOOLEAN",
                        "procedure":block["name"],
                        "line":block["start_line"]+offset,
                        "table":table["name"],
                        "row_variable":bm.group("row"),
                        "column":schema["name"],
                        "column_line":schema["line"],
                        "boolean_typed":schema["boolean_typed"],
                        "all_local_added_rows_initialized":all_initialized,
                        "code":raw.strip()[:220],
                        "note":"A locally proven ValueTable column reaches bare Boolean consumption without a bounded proof that Undefined is impossible.",
                    })
        if is_if or is_elseif or is_else:
            if_guard_stack.append(current_guards)
    return findings


def standard_fill_destructive_rewrite_findings(block):
    """Review-only lexical signal for standard fill followed by destructive rebuild."""
    raw_lines=block["text"].splitlines()
    ident=r'[A-Za-zА-Яа-яЁё_][\wА-Яа-яЁё]*'
    fill_re=re.compile(rf'(?P<owner>{ident}(?:\s*\.\s*{ident})*)\s*\.\s*(?P<method>{ident})\s*\(\s*(?P<table>{ident})\b',re.I)
    clear_re=re.compile(rf'^\s*(?P<table>{ident})\s*\.\s*Очистить\s*\(\s*\)',re.I)
    rebuild_re=re.compile(rf'^\s*(?P<table>{ident})\s*=\s*Новый\s+ТаблицаЗначений\b',re.I)
    filled={}
    findings=[]
    for offset,raw in enumerate(raw_lines):
        code=raw.split("//",1)[0].strip()
        for fm in fill_re.finditer(code):
            owner=re.sub(r'\s+','',fm.group("owner"))
            method=fm.group("method")
            if re.search(r'(?i)(Стандарт|Типов)',owner) and re.search(r'(?i)Заполн',method):
                filled[fm.group("table").lower()]={
                    "table":fm.group("table"),
                    "fill_line":block["start_line"]+offset,
                    "owner":owner,
                    "method":method,
                }
        cm=clear_re.match(code)
        rm=rebuild_re.match(code)
        match=cm or rm
        if match and match.group("table").lower() in filled:
            src=filled[match.group("table").lower()]
            findings.append({
                "severity":"REVIEW",
                "type":"STANDARD_FILL_DESTRUCTIVE_REWRITE_REVIEW",
                "procedure":block["name"],
                "line":block["start_line"]+offset,
                "fill_line":src["fill_line"],
                "table":src["table"],
                "fill_owner":src["owner"],
                "fill_method":src["method"],
                "rewrite_kind":"CLEAR" if cm else "REBUILD_NEW_VALUE_TABLE",
                "code":raw.strip()[:220],
                "note":"A same-routine standard/typical-named fill is followed by destructive row reset. Review under STANDARD_PIPELINE_SEMANTIC_PRESERVATION.",
            })
    return findings


def structure_constructor_findings(block):
    findings=[]
    # Safe heuristic for common pattern Новый Структура("A,B,C,D", value...).
    for m in re.finditer(r'Новый\s+Структура\s*\(\s*"([^"]+)"\s*,', block["text"], re.I):
        props=[x.strip() for x in m.group(1).replace("|","").split(",") if x.strip()]
        if len(props)>3:
            line=block["start_line"]+block["text"].count("\n",0,m.start())
            findings.append({"line":line,"properties":len(props),"code":m.group(0)[:180]})
    return findings

def known_binary_data_vars(block):
    """Return variables whose type is locally proven as BinaryData.

    BinaryData.Write(path) is file I/O, not a 1C database object write.  The
    WRITE_IN_LOOP rule must not attach transaction/database standards to that
    call merely because the platform uses the same `Записать` method name.
    We suppress only when the constructor is explicit in the same routine;
    unresolved receivers remain conservative findings.
    """
    return {
        match.group(1).lower()
        for match in re.finditer(
            r'(?im)^\s*([A-Za-zА-Яа-яЁё_][\wА-Яа-яЁё]*)\s*=\s*Новый\s+ДвоичныеДанные\s*\(',
            block["text"],
        )
    }

def write_in_loop_findings(block):
    stack=[]; out=[]
    binary_data_vars = known_binary_data_vars(block)
    for offset,line in enumerate(block["text"].splitlines()):
        s=line.strip()
        if re.match(r'(?i)^(Для\s+Каждого|Для\s+\w+\s*=|Пока\b)',s): stack.append(block["start_line"]+offset)
        write_call = re.search(r'\b([A-Za-zА-Яа-яЁё_][\wА-Яа-яЁё]*)\.Записать\s*\(', s, re.I)
        if stack and write_call and write_call.group(1).lower() not in binary_data_vars:
            out.append({"line":block["start_line"]+offset,"loop_start":stack[-1],"code":s})
        if re.match(r'(?i)^КонецЦикла\b',s) and stack: stack.pop()
    return out

def form_data_access_analysis(block):
    """Separate cheap direct form-data reads from unresolved nested paths.

    `Форма.Объект.Поле` / `Объект.Поле` is direct access to the form data
    attribute. A longer path is not automatically a defect: the first member
    can be a nested form-data structure. It does require type evidence because
    it can also be reference dereference and therefore a DB read/N+1 source.
    """
    direct=[]; nested=[]; client_collection_loops=[]; loop_stack=[]
    path_re=re.compile(r'\b(?:Форма\s*\.\s*)?Объект(?P<tail>(?:\s*\.\s*[A-Za-zА-Яа-я_][\wА-Яа-я]*)+)',re.I)
    loop_re=re.compile(r'(?i)^\s*Для\s+Каждого\s+\w+\s+Из\s+(?P<path>(?:Форма\s*\.\s*)?Объект\s*\.\s*[A-Za-zА-Яа-я_][\wА-Яа-я]*)\s+Цикл\b')
    for offset,line in enumerate(block["text"].splitlines()):
        line_no=block["start_line"]+offset
        stripped=line.strip()
        loop_match=loop_re.match(stripped)
        if loop_match:
            loop_stack.append(line_no)
            if block.get("execution_context") in {"НаКлиенте","НаКлиентеНаСервереБезКонтекста"}:
                client_collection_loops.append({"line":line_no,"code":stripped,"path":loop_match.group("path")})
        elif re.match(r'(?i)^\s*(?:Для\s+Каждого|Для\s+\w+\s*=|Пока\b)',stripped):
            loop_stack.append(line_no)
        for match in path_re.finditer(line):
            members=re.findall(r'[A-Za-zА-Яа-я_][\wА-Яа-я]*',match.group("tail"))
            # A final member immediately followed by '(' is a method, not a
            # second data-path segment (e.g. Объект.Товары.НайтиСтроки()).
            after=line[match.end():]
            if members and re.match(r'\s*\(',after):members=members[:-1]
            if not members:continue
            item={"line":line_no,"code":match.group(0),"members":members,"execution_context":block.get("execution_context"),"in_loop":bool(loop_stack)}
            if len(members)==1:direct.append(item)
            else:nested.append(item)
        if re.match(r'(?i)^\s*КонецЦикла\b',stripped) and loop_stack:loop_stack.pop()
    return {"direct":direct,"nested":nested,"client_collection_loops":client_collection_loops}


QUERY_BOUNDARY_RE = re.compile(
    r'(?i)\b(?:ВЫБРАТЬ|ИЗ|СОЕДИНЕНИЕ|ОБЪЕДИНИТЬ|ПОМЕСТИТЬ|СГРУППИРОВАТЬ\s+ПО|УПОРЯДОЧИТЬ\s+ПО|ГДЕ|ИМЕЮЩИЕ)\b'
)
IDENT_NAME_RE = re.compile(r'^[A-Za-zА-Яа-яЁё_][\wА-Яа-яЁё]*$')


def _expr_vars(expr):
    return {
        token.lower()
        for token in re.findall(r'[A-Za-zА-Яа-яЁё_][\wА-Яа-яЁё]*', expr or '')
        if IDENT_NAME_RE.match(token)
    }


def query_text_surgery_findings(block):
    """Detect query-grammar boundary search -> positional slice -> query-text sink.

    The detector is deliberately dataflow-oriented.  It follows query-object
    aliases, recognizes a direct positional slice inside a sink/constructor, and
    treats an unresolved parameter/factory receiver conservatively instead of
    silently declaring it safe.
    """
    lines=block["text"].splitlines()
    assignments=[]
    boundary_literals=set()
    boundary_positions={}
    nested_boundaries=[]
    tainted_text=set()
    slice_vars=set()
    evidence=[]
    query_objects=set()
    query_aliases={}
    unresolved_receivers=set()
    ident=r'[A-Za-zА-Яа-яЁё_][\wА-Яа-яЁё]*'
    assign_re=re.compile(
        rf'^\s*({ident}(?:\s*\.\s*{ident})?)\s*=\s*(.*?)\s*;?\s*$',
        re.I,
    )

    def normalized(value):
        return re.sub(r'\s+','',value or '').lower()

    def nested_boundary_search(expr):
        search=re.search(r'(?i)\bСтрНайти\s*\(\s*([^,]+)\s*,\s*([^)]+)\)',expr or '')
        if not search:
            return None
        haystack=search.group(1).strip()
        needle=search.group(2).strip()
        needle_text=' '.join(re.findall(r'"([^"]*)"',needle))
        if not (QUERY_BOUNDARY_RE.search(needle_text) or (_expr_vars(needle) & boundary_literals)):
            return None
        haystack_vars=_expr_vars(haystack)
        if not haystack_vars:
            return None
        return {"haystack_vars":haystack_vars,"needle":needle[:120],"haystack":haystack[:120]}

    def positional_slice(expr):
        match=re.search(r'(?i)\b(Сред|Лев|Прав)\s*\((.*)\)',expr or '')
        if not match:
            return None
        vars_in_args=_expr_vars(match.group(2))
        assigned_boundary=bool(vars_in_args & tainted_text and vars_in_args & set(boundary_positions))
        nested_boundary=nested_boundary_search(match.group(2))
        if not assigned_boundary and not nested_boundary:
            return None
        return {"operation":match.group(1),"vars":vars_in_args,"nested_boundary":nested_boundary}

    for offset,line in enumerate(lines):
        match=assign_re.match(line)
        if not match:
            continue
        lhs=re.sub(r'\s+','',match.group(1))
        rhs=match.group(2).strip()
        assignments.append((offset,lhs,rhs))
        literal_words=' '.join(re.findall(r'"([^"]*)"',rhs))
        if QUERY_BOUNDARY_RE.search(literal_words):
            boundary_literals.add(lhs.lower())

        # Direct construction proves a query-object receiver.  Construction with
        # an argument is additionally handled below as a possible query-text sink.
        if re.search(r'(?i)^Новый\s+Запрос\b',rhs):
            query_objects.add(lhs.lower())
            continue

        # Plain variable aliases are propagated after all direct constructors are
        # known.  Calls/factories remain unresolved rather than being guessed safe.
        if re.match(rf'(?i)^{ident}$',rhs):
            query_aliases[lhs.lower()]=rhs.lower()
        elif re.match(rf'(?i)^{ident}\s*\(',rhs):
            if "." not in lhs:
                unresolved_receivers.add(lhs.lower())

    # Fixed-point query-object alias propagation.
    changed=True
    while changed:
        changed=False
        for alias,source in query_aliases.items():
            if source in query_objects and alias not in query_objects:
                query_objects.add(alias);changed=True

    # Query text copied out of a proven query object is a grammar-bearing source.
    for _offset,lhs,rhs in assignments:
        source=re.match(rf'(?i)^({ident})\s*\.\s*Текст\b',rhs)
        if source and source.group(1).lower() in query_objects:
            tainted_text.add(lhs.lower())

    # Boundary searches establish both a grammar-bearing text value and an exact
    # position identity.  Evidence must refer to the current offset, never a stale
    # loop variable.
    for offset,lhs,rhs in assignments:
        search=re.search(r'(?i)\bСтрНайти\s*\(\s*([^,]+)\s*,\s*([^)]+)\)',rhs)
        if not search:
            continue
        if lhs.lower().endswith(".текст") or re.search(r'(?i)^Новый\s+Запрос\b',rhs):
            continue
        haystack=search.group(1).strip()
        needle=search.group(2).strip()
        needle_text=' '.join(re.findall(r'"([^"]*)"',needle))
        if not (QUERY_BOUNDARY_RE.search(needle_text) or (_expr_vars(needle) & boundary_literals)):
            continue
        haystack_vars=_expr_vars(haystack)
        if not haystack_vars:
            continue
        tainted_text.update(haystack_vars)
        boundary_positions[lhs.lower()]={
            "line":block["start_line"]+offset,
            "needle":needle[:120],
            "haystack":haystack[:120],
        }
        evidence.append({
            "stage":"BOUNDARY_SEARCH",
            "line":block["start_line"]+offset,
            "code":lines[offset].strip()[:220],
        })

    # Propagate text provenance through ordinary aliases/transformations.
    changed=True
    while changed:
        changed=False
        for _offset,lhs,rhs in assignments:
            lhs_lower=lhs.lower()
            if lhs_lower.endswith(".текст"):
                continue
            if (_expr_vars(rhs) & tainted_text) and lhs_lower not in tainted_text:
                tainted_text.add(lhs_lower);changed=True

    fragments={}
    # Positional slice may be assigned to an intermediate variable.
    for offset,lhs,rhs in assignments:
        lhs_lower=lhs.lower()
        if lhs_lower in query_objects and re.search(r'(?i)^Новый\s+Запрос\b',rhs):
            continue
        fragment=positional_slice(rhs)
        if not fragment:
            continue
        if not lhs_lower.endswith(".текст"):
            slice_vars.add(lhs_lower)
            fragments[lhs_lower]={
                "line":block["start_line"]+offset,
                "operation":fragment["operation"],
                "code":lines[offset].strip()[:220],
            }
            evidence.append({
                "stage":"POSITIONAL_SLICE",
                "line":block["start_line"]+offset,
                "code":lines[offset].strip()[:220],
            })

    # Preserve slice provenance through aliases without requiring a specifically
    # named "fragment" variable.
    changed=True
    while changed:
        changed=False
        for _offset,lhs,rhs in assignments:
            lhs_lower=lhs.lower()
            if lhs_lower.endswith(".текст"):
                continue
            if (_expr_vars(rhs) & slice_vars) and lhs_lower not in slice_vars:
                slice_vars.add(lhs_lower);changed=True

    sinks=[]
    for offset,lhs,rhs in assignments:
        lhs_norm=normalized(lhs)

        # q.Text = <slice or slice-derived expression>
        sink=re.match(rf'(?i)^({ident})\.текст$',lhs_norm)
        if sink:
            receiver=sink.group(1).lower()
            direct_slice=positional_slice(rhs)
            derived=bool(_expr_vars(rhs) & slice_vars)
            if direct_slice or derived:
                receiver_state=(
                    "PROVEN_QUERY_OBJECT" if receiver in query_objects
                    else "UNRESOLVED_QUERY_RECEIVER"
                )
                if receiver not in query_objects:
                    unresolved_receivers.add(receiver)
                row={
                    "line":block["start_line"]+offset,
                    "code":lines[offset].strip()[:220],
                    "query_object":sink.group(1),
                    "receiver_state":receiver_state,
                    "sink_kind":"QUERY_TEXT_ASSIGNMENT",
                }
                sinks.append(row)
                if direct_slice and direct_slice.get("nested_boundary"):
                    nested=direct_slice["nested_boundary"]
                    nested_boundaries.append({
                        "line":block["start_line"]+offset,
                        "needle":nested["needle"],
                        "haystack":nested["haystack"],
                    })
                    evidence.append({
                        "stage":"BOUNDARY_SEARCH",
                        "line":block["start_line"]+offset,
                        "code":lines[offset].strip()[:220],
                    })
                if direct_slice:
                    evidence.append({
                        "stage":"POSITIONAL_SLICE",
                        "line":block["start_line"]+offset,
                        "code":lines[offset].strip()[:220],
                    })
                evidence.append({
                    "stage":"QUERY_TEXT_SINK",
                    "line":block["start_line"]+offset,
                    "code":lines[offset].strip()[:220],
                })
                continue

        # q = Новый Запрос(<slice or slice-derived expression>)
        constructor=re.search(r'(?i)^Новый\s+Запрос\s*\((.*)\)\s*;?$',rhs)
        if constructor:
            arg=constructor.group(1).strip()
            direct_slice=positional_slice(arg)
            derived=bool(_expr_vars(arg) & slice_vars)
            if direct_slice or derived:
                row={
                    "line":block["start_line"]+offset,
                    "code":lines[offset].strip()[:220],
                    "query_object":lhs,
                    "receiver_state":"PROVEN_QUERY_OBJECT",
                    "sink_kind":"QUERY_CONSTRUCTOR_ARGUMENT",
                }
                sinks.append(row)
                if direct_slice and direct_slice.get("nested_boundary"):
                    nested=direct_slice["nested_boundary"]
                    nested_boundaries.append({
                        "line":block["start_line"]+offset,
                        "needle":nested["needle"],
                        "haystack":nested["haystack"],
                    })
                    evidence.append({
                        "stage":"BOUNDARY_SEARCH",
                        "line":block["start_line"]+offset,
                        "code":lines[offset].strip()[:220],
                    })
                if direct_slice:
                    evidence.append({
                        "stage":"POSITIONAL_SLICE",
                        "line":block["start_line"]+offset,
                        "code":lines[offset].strip()[:220],
                    })
                evidence.append({
                    "stage":"QUERY_CONSTRUCTOR_SINK",
                    "line":block["start_line"]+offset,
                    "code":lines[offset].strip()[:220],
                })

    if not sinks:
        return []
    return [{
        "severity":"HIGH",
        "type":"HOMEGROWN_QUERY_STRUCTURE_PARSER",
        "failure_class":"FR_PRP02_INTERNAL_PIPELINE_AND_QUERY_SURGERY",
        "procedure":block["name"],
        "chain":{
            "boundary_searches":[*boundary_positions.values(),*nested_boundaries],
            "fragments":list(fragments.values()),
            "sinks":sinks,
            "unresolved_receivers":sorted(unresolved_receivers),
        },
        "items":evidence,
        "note":"Query text is structurally searched and positionally sliced before reaching Query.Text or the Query constructor. Unknown parameter/factory receivers remain REVIEW/finding rather than being assumed safe. Exact-source/content-bound exception evidence is required; generic semantic prose is insufficient.",
    }]

def query_execute_side_effect_analysis(block):
    """Classify every code Execute token with bounded statement/control-flow proof.

    Coverage is fail-closed: every ``.Выполнить``/``.ВыполнитьПакет`` token that
    occurs outside BSL strings/comments becomes exactly one event. A token that
    cannot be bound safely to a supported direct receiver/statement remains a
    canonical QUERY_EXECUTE_SIDE_EFFECT_TRACE finding with
    ``UNCLASSIFIED_OR_AMBIGUOUS_EXECUTE`` status instead of disappearing.

    The control model is deliberately bounded and procedure-local. It tracks
    structured branches/loops plus abrupt-flow barriers; it is not a full BSL
    parser or CFG/SSA implementation.
    """
    ident=r'[A-Za-zА-Яа-яЁё_][\wА-Яа-яЁё]*'
    source=block['text']

    def mask_noncode(text):
        out=[]
        in_string=False
        line_comment=False
        index=0
        while index<len(text):
            ch=text[index]
            if line_comment:
                if ch in '\r\n':
                    line_comment=False
                    out.append(ch)
                else:
                    out.append(' ')
                index+=1
                continue
            if in_string:
                if ch=='"':
                    if index+1<len(text) and text[index+1]=='"':
                        out.extend((' ',' '))
                        index+=2
                        continue
                    in_string=False
                out.append(ch if ch in '\r\n' else ' ')
                index+=1
                continue
            if ch=='"':
                in_string=True
                out.append(' ')
                index+=1
                continue
            if ch=='/' and index+1<len(text) and text[index+1]=='/':
                line_comment=True
                out.extend((' ',' '))
                index+=2
                continue
            out.append(ch)
            index+=1
        return ''.join(out)

    def header_incomplete(masked):
        normalized=' '.join(masked.split())
        if re.match(r'(?i)^#?(?:Если|ИначеЕсли)\b',normalized):
            return not bool(re.search(r'(?i)\bТогда\b',normalized))
        if re.match(r'(?i)^(?:Для(?:\s+Каждого)?|Пока)\b',normalized):
            return not bool(re.search(r'(?i)\bЦикл\b',normalized))
        return False

    def obvious_continuation(masked):
        stripped=masked.rstrip()
        if not stripped:
            return False
        if re.search(r'(?i)(?:[+\-*/=,<>&.]|\b(?:И|ИЛИ|НЕ)\b)\s*$',stripped):
            return True
        return False

    def lex_statements(text):
        """Return ordered bounded BSL statements with exact source spans.

        Semicolons split only outside strings/comments and at balanced ()/[].
        Newlines retain a statement while delimiters are open, a structured
        control header still waits for Тогда/Цикл, or an obvious expression
        continuation is present.
        """
        result=[]
        in_string=False
        line_comment=False
        paren_depth=0
        bracket_depth=0
        start=0
        index=0

        def emit(end):
            nonlocal start
            raw=text[start:end]
            masked=mask_noncode(raw)
            if masked.strip():
                result.append({
                    'id':len(result),
                    'text':raw,
                    'mask':masked,
                    'start_offset':start,
                    'end_offset':end,
                })

        while index<len(text):
            ch=text[index]
            if line_comment:
                if ch in '\r\n':
                    line_comment=False
                    current=mask_noncode(text[start:index])
                    keep=(paren_depth>0 or bracket_depth>0 or header_incomplete(current) or obvious_continuation(current))
                    if not keep:
                        emit(index)
                        start=index+1
                index+=1
                continue
            if in_string:
                if ch=='"':
                    if index+1<len(text) and text[index+1]=='"':
                        index+=2
                        continue
                    in_string=False
                index+=1
                continue
            if ch=='"':
                in_string=True
                index+=1
                continue
            if ch=='/' and index+1<len(text) and text[index+1]=='/':
                line_comment=True
                index+=2
                continue
            if ch=='(':
                paren_depth+=1
            elif ch==')':
                paren_depth=max(0,paren_depth-1)
            elif ch=='[':
                bracket_depth+=1
            elif ch==']':
                bracket_depth=max(0,bracket_depth-1)
            elif ch==';' and paren_depth==0 and bracket_depth==0:
                emit(index)
                start=index+1
            elif ch=='\n' and paren_depth==0 and bracket_depth==0:
                current=mask_noncode(text[start:index])
                keep=header_incomplete(current) or obvious_continuation(current)
                if not keep:
                    emit(index)
                    start=index+1
            index+=1
        emit(len(text))
        return result

    def expand_inline_controls(base_statements):
        """Split a leading structured-control header from inline body code.

        The split is lexical/bounded: it operates on the already masked statement
        so strings/comments cannot manufacture control markers. Source offsets stay
        exact, allowing raw Execute tokens in both the header and inline body to bind
        to one terminal statement event.
        """
        expanded=[]

        def add_segment(parent,start_rel,end_rel,control_kind=None):
            raw=parent['text'][start_rel:end_rel]
            masked=parent['mask'][start_rel:end_rel]
            if not masked.strip():
                return
            expanded.append({
                'id':len(expanded),
                'text':raw,
                'mask':masked,
                'start_offset':parent['start_offset']+start_rel,
                'end_offset':parent['start_offset']+end_rel,
                'control_kind':control_kind,
            })

        for parent in base_statements:
            mask=parent['mask']
            control_kind=None
            marker_end=None
            patterns=(
                (r'(?is)^\s*#ИначеЕсли\b.*?\bТогда\b','compile_elseif'),
                (r'(?is)^\s*#Если\b.*?\bТогда\b','compile_if'),
                (r'(?is)^\s*ИначеЕсли\b.*?\bТогда\b','elseif'),
                (r'(?is)^\s*Если\b.*?\bТогда\b','if'),
                (r'(?is)^\s*(?:Для(?:\s+Каждого)?|Пока)\b.*?\bЦикл\b','loop'),
                (r'(?is)^\s*#Иначе\b','compile_else'),
                (r'(?is)^\s*Иначе\b','else'),
                (r'(?is)^\s*Исключение\b','except'),
                (r'(?is)^\s*Попытка\b','try'),
            )
            for pattern,kind in patterns:
                match=re.match(pattern,mask)
                if match:
                    control_kind=kind
                    marker_end=match.end()
                    break
            if marker_end is None:
                add_segment(parent,0,len(mask),None)
                continue
            add_segment(parent,0,marker_end,control_kind)
            add_segment(parent,marker_end,len(mask),None)
        return expanded

    full_mask=mask_noncode(source)
    raw_tokens=[]
    method_re=re.compile(r'(?is)\.\s*(?P<method>ВыполнитьПакет|Выполнить)\b')
    for match in method_re.finditer(full_mask):
        dot_offset=match.start()
        method_offset=match.start('method')
        method=match.group('method')
        prefix=full_mask[:dot_offset]
        receiver_match=re.search(rf'(?is)({ident})\s*$',prefix)
        receiver=None
        receiver_start=None
        if receiver_match:
            candidate=receiver_match.group(1)
            candidate_start=receiver_match.start(1)
            before=prefix[:candidate_start].rstrip()
            # Property/chained receivers are outside this bounded identity model.
            if not before or before[-1] not in '.)]':
                receiver=candidate
                receiver_start=candidate_start
        tail=full_mask[match.end('method'):]
        call_match=re.match(r'(?s)\s*\(\s*\)',tail)
        call_end=(match.end('method')+call_match.end()) if call_match else match.end('method')
        raw_tokens.append({
            'token_id':len(raw_tokens),
            'token_offset':method_offset,
            'source_span':[receiver_start if receiver_start is not None else dot_offset,call_end],
            'physical_line':block['start_line']+source.count('\n',0,method_offset),
            'receiver_spelling':receiver,
            'method':method,
            'call_complete':bool(call_match),
            'dot_offset':dot_offset,
            'call_end':call_end,
        })

    statements=expand_inline_controls(lex_statements(source))
    for token in raw_tokens:
        matches=[stmt for stmt in statements if stmt['start_offset']<=token['token_offset']<stmt['end_offset']]
        token['statement_id']=matches[0]['id'] if len(matches)==1 else None
        token['statement_binding_count']=len(matches)

    state={
        'query_bindings':{},
        'manager_bindings':{},
        'manager_state':{},
        'text_state':{},
    }
    execute_calls=[]
    control_stack=[]
    path=()
    query_version=0
    manager_version=0
    control_version=0
    flow_version=0
    flow={'reachable':True,'generation':0}

    def clone_state(source_state=None):
        source_state=state if source_state is None else source_state
        return {key:dict(value) for key,value in source_state.items()}

    def clone_flow(source_flow=None):
        source_flow=flow if source_flow is None else source_flow
        return dict(source_flow)

    def fresh_flow_generation():
        nonlocal flow_version
        flow_version+=1
        return flow_version

    def merge_map(states,key):
        missing=object()
        keys=set()
        for source_state in states:
            keys.update(source_state[key])
        merged={}
        for name in keys:
            values=[source_state[key].get(name,missing) for source_state in states]
            first=values[0]
            if first is not missing and all(value==first for value in values[1:]):
                merged[name]=first
            else:
                merged[name]=None
        return merged

    def merge_states(states):
        if not states:
            return clone_state()
        return {key:merge_map(states,key) for key in state}

    def fresh_query_identity(name):
        nonlocal query_version
        query_version+=1
        return f"query:{name.lower()}:{query_version}"

    def fresh_manager_identity(name):
        nonlocal manager_version
        manager_version+=1
        return f"manager:{name.lower()}:{manager_version}"

    def current_query_identity(name):
        return state['query_bindings'].get(name.lower())

    def resolve_manager_identity(name):
        key=name.lower()
        if key in state['manager_bindings']:
            return state['manager_bindings'][key]
        if current_query_identity(key) is not None:
            return None
        identity=f"manager:external:{key}"
        state['manager_bindings'][key]=identity
        return identity

    def query_text_sets(text):
        produced=set(
            item.lower() for item in re.findall(
                r'(?i)\bПОМЕСТИТЬ\s+([A-Za-zА-Яа-яЁё_][\wА-Яа-яЁё]*)',
                text or '',
            )
        )
        read=set(
            item.lower() for item in re.findall(
                r'(?i)\b(?:ИЗ|СОЕДИНЕНИЕ)\s+([A-Za-zА-Яа-яЁё_][\wА-Яа-яЁё]*)',
                text or '',
            )
        )
        return produced,read

    def path_guarantees_consumer(producer_path,consumer_path):
        producer=dict(producer_path)
        for frame_id,label in consumer_path:
            if producer.get(frame_id)!=label:
                return False
        return True

    def open_frame(kind,label):
        nonlocal control_version,path
        control_version+=1
        frame={
            'kind':kind,
            'id':control_version,
            'base_state':clone_state(),
            'base_flow':clone_flow(),
            'branches':[],
            'path_prefix':tuple(path),
            'label':label,
            'has_total_alternative':False,
        }
        control_stack.append(frame)
        path=frame['path_prefix']+((frame['id'],label),)

    def switch_branch(label,total_alternative=False):
        nonlocal state,flow,path
        if not control_stack:
            return False
        frame=control_stack[-1]
        frame['branches'].append((clone_state(),clone_flow()))
        state=clone_state(frame['base_state'])
        flow=clone_flow(frame['base_flow'])
        frame['label']=label
        frame['has_total_alternative']=frame['has_total_alternative'] or total_alternative
        path=frame['path_prefix']+((frame['id'],label),)
        return True

    def close_branching_frame(include_implicit_base):
        nonlocal state,flow,path
        if not control_stack:
            return False
        frame=control_stack.pop()
        frame['branches'].append((clone_state(),clone_flow()))
        outcomes=list(frame['branches'])
        if include_implicit_base and not frame['has_total_alternative']:
            outcomes.append((clone_state(frame['base_state']),clone_flow(frame['base_flow'])))
        active=[item for item in outcomes if item[1].get('reachable')]
        if active:
            state=merge_states([item[0] for item in active])
            all_guaranteed=(len(active)==len(outcomes) and all(
                item[1].get('generation')==frame['base_flow'].get('generation') for item in outcomes
            ))
            flow={'reachable':True,'generation':frame['base_flow']['generation'] if all_guaranteed else fresh_flow_generation()}
        else:
            state=clone_state(frame['base_state'])
            flow={'reachable':False,'generation':fresh_flow_generation()}
        path=frame['path_prefix']
        return True

    def close_loop_frame():
        nonlocal state,flow,path
        if not control_stack or control_stack[-1]['kind']!='loop':
            return False
        frame=control_stack.pop()
        body_state=clone_state()
        body_flow=clone_flow()
        active_states=[clone_state(frame['base_state'])]
        if body_flow.get('reachable'):
            active_states.append(body_state)
        state=merge_states(active_states)
        # Zero iterations and abrupt loop exits make cross-loop proof conditional.
        flow={'reachable':True,'generation':fresh_flow_generation()}
        path=frame['path_prefix']
        return True

    tokens_by_statement={stmt['id']:[] for stmt in statements}
    orphan_tokens=[]
    for token in raw_tokens:
        if token['statement_id'] in tokens_by_statement:
            tokens_by_statement[token['statement_id']].append(token)
        else:
            orphan_tokens.append(token)

    def positive_consumption_status(statement,token):
        """Return a terminal classification using only supported positive use.

        Surrounding text is not evidence by itself. A complete direct call is
        consumed only when the bounded syntax proves assignment/return/chaining,
        nested argument/expression use, or use inside a recognized control header.
        Unknown contexts fail closed as AMBIGUOUS_OR_UNPARSED.
        """
        receiver=token['receiver_spelling']
        if not receiver or not token['call_complete'] or token['statement_binding_count']!=1:
            return 'AMBIGUOUS_OR_UNPARSED'
        mask=statement['mask']
        local_start=token['source_span'][0]-statement['start_offset']
        local_end=token['source_span'][1]-statement['start_offset']
        if local_start<0 or local_end>len(mask) or local_start>=local_end:
            return 'AMBIGUOUS_OR_UNPARSED'
        before=mask[:local_start]
        after=mask[local_end:]
        if not before.strip() and not after.strip():
            return 'CLASSIFIED_UNREAD'
        if statement.get('control_kind') in {
            'if','elseif','loop','compile_if','compile_elseif'
        }:
            return 'CLASSIFIED_CONSUMED'
        if re.match(r'(?is)^\s*[.[]',after):
            return 'CLASSIFIED_CONSUMED'
        if re.match(r'(?is)^\s*Возврат\b',before):
            return 'CLASSIFIED_CONSUMED'
        assignment=re.match(
            rf'(?is)^\s*{ident}(?:\s*\.\s*{ident})*\s*=\s*',mask
        )
        if assignment and assignment.end()<=local_start:
            return 'CLASSIFIED_CONSUMED'
        # A call nested in an already-open ()/[] is a supported argument/expression
        # use. The Execute call's own parentheses start after local_start and are not
        # part of this depth calculation.
        if before.count('(')>before.count(')') or before.count('[')>before.count(']'):
            return 'CLASSIFIED_CONSUMED'
        return 'AMBIGUOUS_OR_UNPARSED'

    def classify_statement_tokens(statement):
        for token in tokens_by_statement.get(statement['id'],[]):
            receiver=token['receiver_spelling']
            status=positive_consumption_status(statement,token)
            query_identity=current_query_identity(receiver) if receiver else None
            query_text=state['text_state'].get(query_identity) if query_identity is not None else None
            produced,read=query_text_sets(query_text)
            event={
                **token,
                'classification_status':status,
                'statement_identity':statement['id'],
                'statement_text':statement['text'].strip(),
                'query':receiver.lower() if receiver else None,
                'query_identity':query_identity,
                'manager':state['manager_state'].get(query_identity) if query_identity is not None else None,
                'text_known':query_text is not None,
                'produced_temp_tables':sorted(produced),
                'read_temp_tables':sorted(read),
                'control_path':tuple(path),
                'control_path_status':'SUPPORTED' if flow.get('reachable') else 'UNREACHABLE',
                'flow_generation':flow['generation'],
                'reachable':bool(flow['reachable']),
                'order':(statement['id'],token['token_offset']),
            }
            execute_calls.append(event)

    for statement in statements:
        text=statement['text']
        code_mask=statement['mask']
        normalized=' '.join(code_mask.split())

        # Runtime structured branches. Header Execute tokens are classified on
        # every path through this dispatcher; inline body code was split into its
        # own statement event by expand_inline_controls().
        if re.match(r'(?i)^ИначеЕсли\b.*\bТогда$',normalized):
            switch_branch(f"if{len(control_stack[-1]['branches'])+1}" if control_stack else 'if1')
            classify_statement_tokens(statement)
            continue
        if re.fullmatch(r'(?i)Иначе',normalized):
            classify_statement_tokens(statement)
            switch_branch('else',total_alternative=True)
            continue
        if re.fullmatch(r'(?i)КонецЕсли',normalized):
            classify_statement_tokens(statement)
            close_branching_frame(include_implicit_base=True)
            continue
        if re.match(r'(?i)^Если\b.*\bТогда$',normalized):
            classify_statement_tokens(statement)
            open_frame('if','if0')
            continue

        # Compile-time mutually exclusive branches.
        if re.match(r'(?i)^#ИначеЕсли\b.*\bТогда$',normalized):
            switch_branch(f"compile{len(control_stack[-1]['branches'])+1}" if control_stack else 'compile1')
            classify_statement_tokens(statement)
            continue
        if re.fullmatch(r'(?i)#Иначе',normalized):
            classify_statement_tokens(statement)
            switch_branch('compile_else',total_alternative=True)
            continue
        if re.fullmatch(r'(?i)#КонецЕсли',normalized):
            classify_statement_tokens(statement)
            close_branching_frame(include_implicit_base=True)
            continue
        if re.match(r'(?i)^#Если\b.*\bТогда$',normalized):
            classify_statement_tokens(statement)
            open_frame('compile_if','compile0')
            continue

        if re.fullmatch(r'(?i)Исключение',normalized):
            classify_statement_tokens(statement)
            switch_branch('except',total_alternative=True)
            continue
        if re.fullmatch(r'(?i)КонецПопытки',normalized):
            classify_statement_tokens(statement)
            close_branching_frame(include_implicit_base=True)
            continue
        if re.fullmatch(r'(?i)Попытка',normalized):
            classify_statement_tokens(statement)
            open_frame('try','try')
            continue

        if re.fullmatch(r'(?i)КонецЦикла',normalized):
            classify_statement_tokens(statement)
            close_loop_frame()
            continue
        if re.match(r'(?i)^(?:Для(?:\s+Каждого)?|Пока)\b.*\bЦикл$',normalized):
            classify_statement_tokens(statement)
            open_frame('loop','body')
            continue

        # Coverage is independent of reachability/state support: every raw token
        # bound to this statement becomes exactly one classification event.
        classify_statement_tokens(statement)

        # Unreachable statements cannot contribute proof-bearing state.
        if not flow.get('reachable'):
            continue

        binding_handled=False
        constructor=re.match(rf'(?i)^({ident})\s*=\s*Новый\s+Запрос\b',code_mask.strip())
        if constructor:
            name=constructor.group(1).lower()
            state['query_bindings'][name]=fresh_query_identity(name)
            state['manager_bindings'].pop(name,None)
            binding_handled=True

        manager_constructor=re.match(
            rf'(?i)^({ident})\s*=\s*Новый\s+МенеджерВременныхТаблиц\b',code_mask.strip(),
        )
        if manager_constructor:
            name=manager_constructor.group(1).lower()
            state['manager_bindings'][name]=fresh_manager_identity(name)
            state['query_bindings'].pop(name,None)
            binding_handled=True

        if not binding_handled:
            alias_match=re.fullmatch(rf'(?i)\s*({ident})\s*=\s*({ident})\s*',code_mask)
            if alias_match:
                alias=alias_match.group(1).lower()
                source_name=alias_match.group(2).lower()
                source_query=current_query_identity(source_name)
                if source_query is not None:
                    state['query_bindings'][alias]=source_query
                    state['manager_bindings'].pop(alias,None)
                else:
                    source_manager=resolve_manager_identity(source_name)
                    state['query_bindings'].pop(alias,None)
                    state['manager_bindings'][alias]=source_manager
                binding_handled=True

        manager_match=re.fullmatch(
            rf'(?i)\s*({ident})\.МенеджерВременныхТаблиц\s*=\s*(.*?)\s*',code_mask,
        )
        if manager_match:
            receiver=current_query_identity(manager_match.group(1))
            if receiver is not None:
                rhs=manager_match.group(2).strip()
                rhs_name=re.fullmatch(rf'(?i){ident}',rhs)
                inline_constructor=re.fullmatch(
                    r'(?i)Новый\s+МенеджерВременныхТаблиц(?:\s*\(\s*\))?',rhs,
                )
                if rhs_name:
                    state['manager_state'][receiver]=resolve_manager_identity(rhs_name.group(0))
                elif inline_constructor:
                    state['manager_state'][receiver]=fresh_manager_identity(
                        f"{manager_match.group(1).lower()}.property"
                    )
                else:
                    state['manager_state'][receiver]=None

        text_match=re.match(rf'(?is)^\s*({ident})\.Текст\s*=\s*(.*)$',text)
        if text_match:
            receiver=current_query_identity(text_match.group(1))
            if receiver is not None:
                state['text_state'][receiver]=text_match.group(2)

        if not binding_handled:
            assignment=re.match(rf'(?is)^\s*({ident})\s*=\s*(.+)$',code_mask)
            if assignment:
                name=assignment.group(1).lower()
                state['query_bindings'][name]=None
                state['manager_bindings'][name]=None

        # Abrupt-flow barriers: later statements on this exact path are not
        # reachable. Conditional barriers become a new flow generation at merge,
        # preventing a later consumer from post-dominating an earlier producer.
        if re.match(r'(?i)^Возврат\b',normalized):
            flow={'reachable':False,'generation':flow['generation']}
        elif re.match(r'(?i)^ВызватьИсключение\b',normalized):
            flow={'reachable':False,'generation':flow['generation']}
        elif re.fullmatch(r'(?i)Прервать',normalized):
            flow={'reachable':False,'generation':flow['generation']}
        elif re.fullmatch(r'(?i)Продолжить',normalized):
            flow={'reachable':False,'generation':flow['generation']}
        elif re.match(r'(?i)^Перейти\b',normalized):
            flow={'reachable':False,'generation':flow['generation']}

    # Final production reconciliation is independent of every dispatcher path.
    # Every raw token must have exactly one terminal event. A missing or conflicting
    # binding is collapsed to one canonical ambiguous event so coverage defects can
    # never become silent PASS.
    statement_by_id={statement['id']:statement for statement in statements}
    events_by_token={token['token_id']:[] for token in raw_tokens}
    for event in execute_calls:
        events_by_token.setdefault(event['token_id'],[]).append(event)

    def ambiguous_terminal_event(token,coverage_issue):
        statement=statement_by_id.get(token.get('statement_id'))
        return {
            **token,
            'classification_status':'AMBIGUOUS_OR_UNPARSED',
            'coverage_issue':coverage_issue,
            'statement_identity':statement['id'] if statement else None,
            'statement_text':statement['text'].strip() if statement else '',
            'query':token['receiver_spelling'].lower() if token['receiver_spelling'] else None,
            'query_identity':None,
            'manager':None,
            'text_known':False,
            'produced_temp_tables':[],
            'read_temp_tables':[],
            'control_path':(),
            'control_path_status':'UNKNOWN',
            'flow_generation':None,
            'reachable':False,
            'order':(statement['id'] if statement else 10**9,token['token_offset']),
        }

    terminal_events=[]
    reconciliation_issues=[]
    for token in raw_tokens:
        bound=events_by_token.get(token['token_id']) or []
        if len(bound)==1:
            terminal_events.append(bound[0])
            continue
        issue='MISSING_TERMINAL_EVENT' if not bound else 'CONFLICTING_TERMINAL_EVENTS'
        reconciliation_issues.append({'token_id':token['token_id'],'token_offset':token['token_offset'],'type':issue,'count':len(bound)})
        terminal_events.append(ambiguous_terminal_event(token,issue))
    execute_calls=sorted(terminal_events,key=lambda item:item['token_offset'])

    token_offsets=[token['token_offset'] for token in raw_tokens]
    event_offsets=[event['token_offset'] for event in execute_calls]
    token_ids=[token['token_id'] for token in raw_tokens]
    event_token_ids=[event['token_id'] for event in execute_calls]
    coverage={
        'raw_token_count':len(raw_tokens),
        'classified_event_count':len(execute_calls),
        'unclassified_count':sum(1 for event in execute_calls if event['classification_status']=='AMBIGUOUS_OR_UNPARSED'),
        'source_offset_unique':len(token_offsets)==len(set(token_offsets)),
        'event_offset_unique':len(event_offsets)==len(set(event_offsets)),
        'binding_unique':(
            len(event_token_ids)==len(set(event_token_ids))
            and sorted(token_ids)==sorted(event_token_ids)
            and sorted(token_offsets)==sorted(event_offsets)
        ),
        'reconciliation_issue_count':len(reconciliation_issues),
        'reconciliation_issues':reconciliation_issues,
        'tokens':raw_tokens,
        'events':execute_calls,
    }

    findings=[]
    for call in execute_calls:
        if call['classification_status']=='AMBIGUOUS_OR_UNPARSED':
            findings.append({
                'severity':'REVIEW',
                'type':'QUERY_EXECUTE_SIDE_EFFECT_TRACE',
                'procedure':block['name'],
                'line':call['physical_line'],
                'code':call.get('statement_text') or call.get('method'),
                'query_object':call.get('query'),
                'query_identity':call.get('query_identity'),
                'manager_identity':call.get('manager'),
                'control_path':call.get('control_path'),
                'source_offset':call['token_offset'],
                'source_span':call['source_span'],
                'classification_status':call['classification_status'],
                'trace_status':'UNCLASSIFIED_OR_AMBIGUOUS_EXECUTE',
                'note':'Execute/ExecuteBatch token is present in code bytes but cannot be safely classified by the bounded statement/identity model. Coverage is fail-closed; the token may not disappear silently.',
            })
            continue
        if call['classification_status']=='CLASSIFIED_CONSUMED':
            continue
        produced=set(call['produced_temp_tables'])
        manager=call['manager']
        chain=None
        if call.get('reachable') and produced and manager:
            for consumer in execute_calls:
                if consumer['order']<=call['order']:
                    continue
                if consumer['classification_status']!='CLASSIFIED_CONSUMED' or not consumer.get('reachable'):
                    continue
                if consumer.get('flow_generation')!=call.get('flow_generation'):
                    continue
                if not path_guarantees_consumer(call['control_path'],consumer['control_path']):
                    continue
                if not consumer['manager'] or consumer['manager']!=manager:
                    continue
                shared=sorted(produced & set(consumer['read_temp_tables']))
                if not shared:
                    continue
                chain={
                    'producer_query':call['query'],
                    'producer_query_identity':call['query_identity'],
                    'producer_manager':manager,
                    'temporary_tables':shared,
                    'producer_execute_line':call['physical_line'],
                    'producer_control_path':call['control_path'],
                    'consumer_query':consumer['query'],
                    'consumer_query_identity':consumer['query_identity'],
                    'consumer_execute_line':consumer['physical_line'],
                    'consumer_control_path':consumer['control_path'],
                    'consumer_method':consumer['method'],
                }
                break
        if chain:
            continue
        findings.append({
            'severity':'REVIEW',
            'type':'QUERY_EXECUTE_SIDE_EFFECT_TRACE',
            'procedure':block['name'],
            'line':call['physical_line'],
            'code':call.get('statement_text') or call.get('method'),
            'query_object':call.get('query'),
            'query_identity':call.get('query_identity'),
            'manager_identity':manager,
            'control_path':call.get('control_path'),
            'source_offset':call['token_offset'],
            'source_span':call['source_span'],
            'classification_status':call['classification_status'],
            'produced_temp_tables':call.get('produced_temp_tables') or [],
            'trace_status':'UNRESOLVED_NO_BOUND_CONSUMER',
            'note':'Unread Execute/ExecuteBatch is classified from an independent raw-token inventory and bounded statement/control-flow model. Suppression requires a post-dominating supported path with exact manager/temp-table identity; abrupt or ambiguous flow fails closed.',
        })

    return {'findings':findings,'coverage':coverage}


def query_execute_side_effect_findings(block):
    return query_execute_side_effect_analysis(block)['findings']

_BARE_SYMBOL_IDENT_RE=re.compile(r'[A-Za-zА-Яа-яЁё_][\wА-Яа-яЁё]*')
_BARE_SYMBOL_KEYWORDS={x.lower() for x in ("Если Тогда Иначе ИначеЕсли КонецЕсли Для Каждого Из Цикл КонецЦикла Пока По Возврат Продолжить Прервать Перем Экспорт Процедура Функция КонецПроцедуры КонецФункции Новый И Или Не Истина Ложь Неопределено Null Попытка Исключение КонецПопытки ВызватьИсключение Перейти Асинх Ждать Знач").split()}

def _mask_bsl_strings_and_comments(text):
    chars=list(text);i=0;in_string=False
    while i<len(chars):
        ch=chars[i]
        if in_string:
            if ch=='"':
                if i+1<len(chars) and chars[i+1]=='"':chars[i]=chars[i+1]=' ';i+=2;continue
                chars[i]=' ';in_string=False;i+=1;continue
            if ch not in '\r\n':chars[i]=' '
            i+=1;continue
        if ch=='"':chars[i]=' ';in_string=True;i+=1;continue
        if ch=='/' and i+1<len(chars) and chars[i+1]=='/':
            while i<len(chars) and chars[i] not in '\r\n':chars[i]=' ';i+=1
            continue
        i+=1
    return ''.join(chars)

def bare_symbol_read_analysis(block_rows,known_symbols=None,scope_complete=False,routine_headers_complete=True):
    if not scope_complete:
        return {"status":"NOT_CHECKED","finding_count":0,"findings":[],"reason":"Exact unqualified-symbol scope is incomplete; missing context is not PASS.","known_symbols":sorted(set(str(x) for x in (known_symbols or []) if str(x).strip()))}
    if not routine_headers_complete:
        return {"status":"NOT_CHECKED","finding_count":0,"findings":[],"reason":"Recognizable BSL routine header syntax was not fully parsed; unchecked routine context is not PASS.","known_symbols":sorted(set(str(x) for x in (known_symbols or []) if str(x).strip()))}
    external={str(x).lower() for x in (known_symbols or []) if str(x).strip()};findings=[]
    for block in block_rows:
        defined=set(external)|{str(x).lower() for x in block.get("params") or []}
        masked_lines=_mask_bsl_strings_and_comments(block["text"]).splitlines();raw_lines=block["text"].splitlines()
        for offset,line in enumerate(masked_lines):
            raw=raw_lines[offset] if offset<len(raw_lines) else line;stripped=line.strip()
            if not stripped or offset==0 or re.match(r'(?i)^Конец(?:Процедуры|Функции)\b',stripped):continue
            decl=re.match(r'(?i)^Перем\s+(.+?);?\s*$',stripped)
            if decl:
                defined.update(x.lower() for x in _BARE_SYMBOL_IDENT_RE.findall(decl.group(1)));continue
            segments=[];define_after=[]
            each=re.match(r'(?i)^Для\s+Каждого\s+([A-Za-zА-Яа-яЁё_][\wА-Яа-яЁё]*)\s+Из\s+(.+?)\s+Цикл\b',stripped)
            if each:
                expr=each.group(2);segments=[(expr,line.find(expr))];define_after=[each.group(1)]
            else:
                loop=re.match(r'(?i)^Для\s+([A-Za-zА-Яа-яЁё_][\wА-Яа-яЁё]*)\s*=\s*(.+?)\s+По\s+(.+?)\s+Цикл\b',stripped)
                if loop:
                    expr=loop.group(2)+" "+loop.group(3);segments=[(expr,line.find(loop.group(2)))];define_after=[loop.group(1)]
                else:
                    assign=re.match(r'^\s*([A-Za-zА-Яа-яЁё_][\wА-Яа-яЁё]*)\s*=\s*(.*)$',line)
                    if assign:segments=[(assign.group(2),assign.start(2))];define_after=[assign.group(1)]
                    else:segments=[(line,0)]
            for expr,shift in segments:
                for match in _BARE_SYMBOL_IDENT_RE.finditer(expr):
                    symbol=match.group(0);key=symbol.lower();pos=shift+match.start();before=line[:pos].rstrip();after=line[shift+match.end():].lstrip()
                    if key in _BARE_SYMBOL_KEYWORDS or key in defined or before.endswith('.') or after.startswith('(') or after.startswith(':'):continue
                    findings.append({"severity":"HIGH","type":"UNRESOLVED_BARE_IDENTIFIER_READ","symbol":symbol,"line":block["start_line"]+offset,"code":raw.strip()[:180],"procedure":block["name"],"note":"Exact complete unqualified-symbol scope does not establish this bare read."})
            defined.update(x.lower() for x in define_after)
    return {"status":"FAIL" if findings else "PASS","finding_count":len(findings),"findings":findings,"reason":"Exact unqualified-symbol scope was declared complete for this analyzer run.","known_symbols":sorted(set(str(x) for x in (known_symbols or []) if str(x).strip()))}


BSL_STANDARD_MAX_LINE_LENGTH=120

def _normalize_changed_line_ranges(changed_line_ranges):
    if changed_line_ranges is None:
        return None
    normalized=[]
    for item in changed_line_ranges:
        if not isinstance(item,(list,tuple)) or len(item)!=2:
            raise ValueError("changed line range must be a (start,end) pair")
        start,end=int(item[0]),int(item[1])
        if start<1 or end<start:
            raise ValueError("changed line range must satisfy 1 <= start <= end")
        normalized.append((start,end))
    return sorted(set(normalized))

def _line_is_changed(line_no,changed_line_ranges):
    return changed_line_ranges is not None and any(start<=line_no<=end for start,end in changed_line_ranges)

def source_layout_analysis(text,changed_line_ranges=None):
    """Deterministic floor with explicit attribution authority.

    Without exact changed-line scope, whole-file findings are REVIEW-only because
    legacy untouched layout debt must not be attributed to the current task.
    """
    changed_line_ranges=_normalize_changed_line_ranges(changed_line_ranges)
    authoritative=changed_line_ranges is not None
    findings=[];blank_run=0;blank_run_start=None
    for line_no,line in enumerate(text.splitlines(),1):
        stripped=line.strip()
        if not stripped:
            if blank_run==0:
                blank_run_start=line_no
            blank_run+=1
            run_intersects_change=(
                authoritative
                and any(
                    _line_is_changed(run_line,changed_line_ranges)
                    for run_line in range(blank_run_start,line_no+1)
                )
            )
            if blank_run>1 and (not authoritative or run_intersects_change):
                findings.append({
                    "severity":"HIGH" if authoritative else "REVIEW",
                    "type":"MULTIPLE_CONSECUTIVE_EMPTY_LINES","line":line_no,
                    "blank_run_start":blank_run_start,"blank_run_end":line_no,
                    "change_attribution":"EXACT_CHANGED_RUN" if authoritative else "WHOLE_FILE_UNATTRIBUTED",
                    "note":"Changed/new BSL may contain at most one consecutive blank line. Exact attribution applies when any line participating in the violating blank run intersects changed scope; whole-file scan without exact scope is diagnostic only.",
                })
            continue
        blank_run=0;blank_run_start=None
        left=line.lstrip()
        # std444 has documented cases where a long source line cannot/should not be
        # mechanically wrapped (notably user-visible/string content). Do not guess there.
        if len(line)>BSL_STANDARD_MAX_LINE_LENGTH and not left.startswith("//") and not left.startswith("|") and '"' not in line:
            if not authoritative or _line_is_changed(line_no,changed_line_ranges):
                findings.append({
                    "severity":"HIGH" if authoritative else "REVIEW",
                    "type":"BSL_LINE_LENGTH_STD444","line":line_no,
                    "length":len(line),"limit":BSL_STANDARD_MAX_LINE_LENGTH,
                    "change_attribution":"EXACT_CHANGED_LINE" if authoritative else "WHOLE_FILE_UNATTRIBUTED",
                    "note":"Official 1C std444 requires wrapping over 120 characters unless its documented exception applies. Whole-file scan without exact changed-line scope is diagnostic only.",
                })
    return {
        "status":("FAIL" if findings else "PASS") if authoritative else ("EVIDENCE_REQUIRED" if findings else "PASS"),
        "finding_count":len(findings),"findings":findings,
        "scope":"EXACT_CHANGED_LINES" if authoritative else "WHOLE_FILE_NON_AUTHORITATIVE",
        "authoritative_for_change_attribution":authoritative,
        "changed_line_ranges":[list(x) for x in changed_line_ranges] if authoritative else [],
        "standard":"std444",
    }

def analyze(path,bare_symbol_scope_complete=False,known_symbols=None,changed_line_ranges=None):
    text = decode(path)
    bs = blocks(text)
    names = {b["name"] for b in bs}
    result = {
        "file": str(path),
        "sha256": __import__("hashlib").sha256(Path(path).read_bytes()).hexdigest(),
        "procedures": [],
        "summary": {},
        "findings": [],
        "standards": set(),
    }
    layout=source_layout_analysis(text,changed_line_ranges=changed_line_ranges)
    result["layout_validation"]={k:v for k,v in layout.items() if k!="findings"}
    result["findings"].extend(layout["findings"])
    if any(x.get("type")=="BSL_LINE_LENGTH_STD444" for x in layout["findings"]):
        result["standards"].add("std444")
    bare=bare_symbol_read_analysis(
        bs,known_symbols=known_symbols,scope_complete=bare_symbol_scope_complete,
        routine_headers_complete=len(list(ROUTINE_HEADER_HINT_RE.finditer(text)))==len(bs),
    )
    result["bare_symbol_validation"]={k:v for k,v in bare.items() if k!="findings"}
    result["findings"].extend(bare["findings"])

    for b in bs:
        refs = known_reference_vars(b)
        bt = b["text"]
        escape_findings=query_literal_escape_findings(b)
        if escape_findings:
            result["findings"].extend(escape_findings)
            result["standards"].add("std437")
        proc = {
            "name": b["name"], "export": b["export"],
            "execution_context": b["execution_context"],
            "execute": bt.count(".Выполнить()"),
            "execute_batch": bt.count(".ВыполнитьПакет()"),
            "get_object": len(re.findall(r'\.ПолучитьОбъект\s*\(', bt)),
            "bulk_reads": len(re.findall(r'Значени[ея]РеквизитовОбъект', bt)),
            "calls": sorted({n for n in names if n != b["name"] and re.search(rf'\b{re.escape(n)}\s*\(', bt)}),
        }
        form_access=form_data_access_analysis(b)
        proc["direct_form_data_accesses"]=len(form_access["direct"])
        proc["nested_form_data_paths"]=len(form_access["nested"])
        for item in form_access["nested"]:
            result["findings"].append({"severity":"REVIEW","type":"FORM_REFERENCE_DEREFERENCE_REVIEW","procedure":b["name"],**item,"note":"Direct form data access ends at the first member. Prove the runtime type of the remaining path; if the first member is a reference, this may read DB data and becomes an N+1 risk inside a loop."})
            result["standards"].add("std496")
        if form_access["client_collection_loops"]:
            result["findings"].append({"severity":"REVIEW","type":"FORM_COLLECTION_CLIENT_TRAVERSAL_REVIEW","procedure":b["name"],"items":form_access["client_collection_loops"],"note":"If this form attribute is DataFormCollection and can exceed a small row count, client traversal can trigger implicit server reads; std628 requires material traversal/search on server."})
            result["standards"].add("std628")
        proc["execute_in_loop"] = loop_execute_findings(b)
        if proc["execute_in_loop"]:
            result["standards"].update(["std436", "std729"])
            result["findings"].append({"severity":"HIGH","type":"QUERY_IN_LOOP","procedure":b["name"],"items":proc["execute_in_loop"]})

        structure_property_bool_hits = structure_property_out_param_boolean_findings(b)
        if structure_property_bool_hits:
            result["findings"].extend(structure_property_bool_hits)

        value_table_bool_hits = value_table_tri_state_boolean_findings(b)
        if value_table_bool_hits:
            result["findings"].extend(value_table_bool_hits)

        standard_rewrite_hits = standard_fill_destructive_rewrite_findings(b)
        if standard_rewrite_hits:
            result["findings"].extend(standard_rewrite_hits)

        structure_hits = structure_constructor_findings(b)
        if structure_hits:
            result["standards"].update(["std693","std641"])
            result["findings"].append({"severity":"MEDIUM","type":"STRUCTURE_CONSTRUCTOR_MANY_VALUES","procedure":b["name"],"items":structure_hits})

        write_hits = write_in_loop_findings(b)
        if write_hits:
            result["standards"].update(["std792","std783"])
            result["findings"].append({"severity":"HIGH","type":"WRITE_IN_LOOP","procedure":b["name"],"items":write_hits})

        if "НачатьТранзакцию" in bt:
            result["standards"].add("std783")
            required = ["ЗафиксироватьТранзакцию", "ОтменитьТранзакцию", "Попытка", "Исключение"]
            missing=[x for x in required if x not in bt]
            if missing:
                result["findings"].append({"severity":"HIGH","type":"TRANSACTION_PATTERN_INCOMPLETE","procedure":b["name"],"missing":missing})

        if "Исключение" in bt:
            result["standards"].add("std499")
            for m in re.finditer(r'(?ms)^\s*Исключение\s*(.*?)^\s*КонецПопытки',bt):
                body=m.group(1).strip()
                if not body:
                    result["findings"].append({"severity":"HIGH","type":"EMPTY_EXCEPTION_HANDLER","procedure":b["name"]})

        # Known reference dereference in BSL.
        for var in refs:
            for m in re.finditer(rf'\b{re.escape(var)}\.([A-Za-zА-Яа-я_][\wА-Яа-я]*)', bt):
                line = b["start_line"] + bt.count("\n", 0, m.start())
                result["findings"].append({"severity":"HIGH","type":"BSL_REFERENCE_DOT","procedure":b["name"],"line":line,"code":m.group(0)})
                result["standards"].add("std496")
            for m in re.finditer(rf'\bСтрока\s*\(\s*{re.escape(var)}\s*\)', bt):
                line = b["start_line"] + bt.count("\n", 0, m.start())
                result["findings"].append({"severity":"MEDIUM","type":"REFERENCE_REPRESENTATION","procedure":b["name"],"line":line,"code":m.group(0)})
                result["standards"].add("std496")

        if proc["get_object"]:
            result["findings"].append({"severity":"HIGH","type":"GET_OBJECT","procedure":b["name"],"count":proc["get_object"]})
            result["standards"].add("std496")

        # Query text assembled by splicing a variable fragment with `+`.
        # This is especially fragile for UNION/WHERE/package boundaries; std437 prefers
        # a complete readable template with explicit replacement anchors when practical.
        lines_bt = bt.splitlines()
        for li, line in enumerate(lines_bt):
            if "+" not in line:
                continue
            window = "\n".join(lines_bt[max(0, li-25):li+2])
            direct_query_concat = re.search(
                r'(?:Запрос\.Текст|ТекстЗапроса)\s*=\s*(?:Запрос\.Текст|ТекстЗапроса)\s*\+\s*[A-Za-zА-Яа-я_][\wА-Яа-я]*',
                line)
            string_fragment_concat = re.search(r'"\s*\+\s*[A-Za-zА-Яа-я_][\wА-Яа-я]*', line)
            if ("Запрос.Текст" in window or "ТекстЗапроса" in window) and (direct_query_concat or string_fragment_concat):
                result["findings"].append({"severity":"HIGH","type":"QUERY_TEXT_FRAGMENT_CONCATENATION","procedure":b["name"],"line":b["start_line"]+li,"code":line.strip(),"note":"std437/project gate: prefer complete query template + unique marker + СтрЗаменить for dynamic UNION/WHERE/package fragments; validate every final variant."})
                result["standards"].update(["std437","std758"])

        # Project hard gate: a query/template must remain readable by the 1C query constructor.
        # Custom #Name placeholders inside query-related string literals are not valid query-language
        # constructs at the position where they are used and historically produced non-openable
        # templates. This is intentionally stricter than treating every std437 example as a universal
        # ban: the gate applies when the stored/intermediate query text itself is expected to be a
        # valid, constructor-readable query/template.
        if ("ТекстЗапроса" in bt or "Запрос.Текст" in bt or "ДинамическийСписок" in bt):
            hash_markers = []
            for sm in re.finditer(r'"(?:[^"\n]|"")*#([A-Za-zА-Яа-яЁё_][A-Za-zА-Яа-яЁё0-9_]*)[^"\n]*"', bt):
                marker = "#" + sm.group(1)
                line = b["start_line"] + bt.count("\n", 0, sm.start())
                hash_markers.append({"line": line, "marker": marker, "code": sm.group(0)[:220]})
            if hash_markers:
                result["findings"].append({
                    "severity":"HIGH",
                    "type":"QUERY_TEMPLATE_CUSTOM_MARKER",
                    "procedure":b["name"],
                    "items":hash_markers,
                    "note":"Project constructor-readability gate: do not place custom # placeholders into query-language text. Prefer an exact typical/BSP analog and a complete constructor-readable query/variant; mutate only proven valid fragments."
                })
                result["standards"].update(["std437"])

        surgery_hits=query_text_surgery_findings(b)
        if surgery_hits:
            result["findings"].extend(surgery_hits)
            result["standards"].update(["std437"])
        else:
            # Preserve the older high-confidence parser-only signal while the
            # dataflow detector closes the short-operation FR-PRP-02 bypass.
            parser_tokens = sum(bt.count(x) for x in ("СтрНайти(", "Сред(", "Лев(", "Прав("))
            query_grammar_tokens = sum(bt.upper().count(x) for x in ("ВЫБРАТЬ", "ОБЪЕДИНИТЬ", "СГРУППИРОВАТЬ ПО", "ПОМЕСТИТЬ", " КАК ", "ИЗ"))
            if parser_tokens >= 4 and query_grammar_tokens >= 3 and ("ТекстЗапроса" in bt or "ТекстПоследнегоЗапроса" in bt):
                result["findings"].append({
                    "severity":"HIGH",
                    "type":"HOMEGROWN_QUERY_STRUCTURE_PARSER",
                    "procedure":b["name"],
                    "note":"High-confidence legacy grammar-parser signal. Exact supported analog/exception evidence is required."
                })
                result["standards"].update(["std437"])

        execute_side_effect_hits=query_execute_side_effect_findings(b)
        if execute_side_effect_hits:
            result["findings"].extend(execute_side_effect_hits)
            result["standards"].update(["std436","std777"])

        # Empty-domain sentinel heuristic: using empty document refs as fake array members
        # must be manually proven outside the data domain.
        sentinel_hits = re.findall(r'\.Добавить\(Документы\.[A-Za-zА-Яа-я0-9_]+\.ПустаяСсылка\(\)\)', bt)
        if sentinel_hits:
            result["findings"].append({"severity":"MEDIUM","type":"EMPTY_REFERENCE_SENTINEL_REVIEW","procedure":b["name"],"count":len(sentinel_hits)})
            result["standards"].add("std729")

        # Query analysis.
        qinfo = {"order_by":0,"distinct":0,"group_by":0,"union":0,"union_all":0,"temp_tables":0,"multi_hop":[],"sentinel_broadening":[],"top_without_order":0,"order_alias_contract":[]}
        for q in query_segments(bt):
            aliases = set(re.findall(r'(?i)(?:ИЗ|СОЕДИНЕНИЕ)\s+[A-Za-zА-Яа-я0-9_.]+\s+КАК\s+([A-Za-zА-Яа-я_][\wА-Яа-я]*)', q))
            qinfo["order_by"] += len(re.findall(r'(?i)УПОРЯДОЧИТЬ\s+ПО', q))
            qinfo["distinct"] += len(re.findall(r'(?i)ВЫБРАТЬ\s+РАЗЛИЧНЫЕ', q))
            qinfo["group_by"] += len(re.findall(r'(?i)СГРУППИРОВАТЬ\s+ПО', q))
            qinfo["union_all"] += len(re.findall(r'(?i)ОБЪЕДИНИТЬ\s+ВСЕ', q))
            q_without_all = re.sub(r'(?i)ОБЪЕДИНИТЬ\s+ВСЕ', '', q)
            qinfo["union"] += len(re.findall(r'(?i)ОБЪЕДИНИТЬ\b', q_without_all))
            qinfo["temp_tables"] += len(re.findall(r'(?i)\bПОМЕСТИТЬ\b', q))
            if re.search(r'(?i)ВЫБРАТЬ\s+ПЕРВЫЕ\s+\d+', q) and not re.search(r'(?i)УПОРЯДОЧИТЬ\s+ПО', q):
                qinfo["top_without_order"] += 1

            # Alias-contract review. A bare ORDER BY identifier that is not one of the
            # explicit SELECT aliases may be legitimate (e.g. a source field), therefore
            # this is a review finding rather than a syntax verdict. It pins the historical
            # false-negative class where a selected alias was renamed but ORDER BY was not.
            select_aliases = set(re.findall(r'(?i)\bКАК\s+([A-Za-zА-Яа-я_][\wА-Яа-я]*)', q))
            om = re.search(r'(?is)УПОРЯДОЧИТЬ\s+ПО\s+(.+?)(?:\|?\s*(?:ИТОГИ|АВТОУПОРЯДОЧИВАНИЕ)|["\']\s*;|$)', q)
            if om and select_aliases:
                order_part = om.group(1)
                for token in re.findall(r'(?i)(?<![.])\b([A-Za-zА-Яа-я_][\wА-Яа-я]*)\b', order_part):
                    if token.upper() in {"ВОЗР", "УБЫВ"}:
                        continue
                    if token not in select_aliases:
                        qinfo["order_alias_contract"].append({"identifier": token, "select_aliases": sorted(select_aliases)})
            for a in aliases:
                for m in re.finditer(rf'\b{re.escape(a)}\.([A-Za-zА-Яа-я_][\wА-Яа-я]*)\.([A-Za-zА-Яа-я_][\wА-Яа-я]*)', q):
                    qinfo["multi_hop"].append(m.group(0))
            sentinel_or_patterns = [
                r'(?is)\bИЛИ\s+&([A-Za-zА-Яа-я_][\wА-Яа-я]*)\s*=\s*ЗНАЧЕНИЕ\s*\([^)]*ПустаяСсылка[^)]*\)',
                r'(?is)\bИЛИ\s+ЗНАЧЕНИЕ\s*\([^)]*ПустаяСсылка[^)]*\)\s*=\s*&([A-Za-zА-Яа-я_][\wА-Яа-я]*)',
                r'(?is)\bИЛИ\s+&([A-Za-zА-Яа-я_][\wА-Яа-я]*)\s*(?:ЕСТЬ\s+NULL|=\s*НЕОПРЕДЕЛЕНО)',
            ]
            for pattern in sentinel_or_patterns:
                qinfo["sentinel_broadening"].extend(re.findall(pattern, q))
        proc["query"] = qinfo
        if qinfo["multi_hop"]:
            result["findings"].append({"severity":"HIGH","type":"QUERY_REFERENCE_DEREFERENCE","procedure":b["name"],"items":sorted(set(qinfo["multi_hop"]))})
            result["standards"].update(["std654","std728"])
        if qinfo["sentinel_broadening"]:
            result["findings"].append({
                "severity":"HIGH",
                "type":"QUERY_PARAMETER_SENTINEL_BROADENING_REVIEW",
                "procedure":b["name"],
                "parameters":sorted(set(qinfo["sentinel_broadening"])),
                "note":"An OR branch tied to EmptyRef/Undefined can disable a point filter. Prove caller authorization and expected cardinality for normal, empty, nonexistent and other-context values; prefer an explicit bulk-mode API/query branch when broadening is intentional."
            })
            result["standards"].add("std729")
        if qinfo["union"]:
            result["findings"].append({"severity":"MEDIUM","type":"UNION_DISTINCT_REVIEW","procedure":b["name"],"count":qinfo["union"]})
            result["standards"].update(["std436","std729"])
        if qinfo["order_by"]:
            result["findings"].append({"severity":"MEDIUM","type":"ORDER_BY_REVIEW","procedure":b["name"],"count":qinfo["order_by"]})
            result["standards"].add("std729")
        if qinfo["order_alias_contract"]:
            unique=[]
            seen=set()
            for item in qinfo["order_alias_contract"]:
                key=(item["identifier"],tuple(item["select_aliases"]))
                if key not in seen:
                    seen.add(key); unique.append(item)
            result["findings"].append({"severity":"MEDIUM","type":"ORDER_BY_ALIAS_CONTRACT_REVIEW","procedure":b["name"],"items":unique,"note":"Review whether each bare ORDER BY identifier is a valid source field or a stale result alias. Alias changes must be reviewed together with ORDER BY/GROUP BY/consumers."})
            result["standards"].update(["std437"])
        if qinfo["top_without_order"]:
            result["findings"].append({"severity":"MEDIUM","type":"TOP_WITHOUT_ORDER_REVIEW","procedure":b["name"],"count":qinfo["top_without_order"]})
            result["standards"].update(["std438","std729"])
        if qinfo["temp_tables"]:
            result["standards"].add("std777")
        if re.search(r'ДинамическийСписок\.ТекстЗапроса\s*=', bt):
            result["standards"].update(["std768","std437"])
            result["findings"].append({"severity":"MEDIUM","type":"DYNAMIC_LIST_DIRECT_QUERY_OVERRIDE","procedure":b["name"],"note":"Review BSP УстановитьСвойстваДинамическогоСписка and settings/parameter ordering."})
            if re.search(r'ДинамическийСписок\.ТекстЗапроса\s*=\s*СхемаЗапроса\.ПолучитьТекстЗапроса\s*\(', bt):
                result["findings"].append({"severity":"HIGH","type":"DYNAMIC_QUERY_TEXT_MUTATION_NOT_STRREPLACE","procedure":b["name"],"note":"Project/std437 gate: programmatic dynamic-list query text mutation should use a complete template + СтрЗаменить(); QuerySchema mutation requires explicit exception justification."})
        result["procedures"].append(proc)

    # Transitive I/O topology for exports.
    by_name = {p["name"]: p for p in result["procedures"]}
    def transitive(name, seen=None):
        seen = set() if seen is None else set(seen)
        if name in seen or name not in by_name:
            return {"execute":0,"execute_batch":0,"bulk_reads":0}
        seen.add(name)
        p = by_name[name]
        total = {"execute":p["execute"],"execute_batch":p["execute_batch"],"bulk_reads":p["bulk_reads"]}
        for c in p["calls"]:
            x = transitive(c, seen)
            for k in total: total[k] += x[k]
        return total
    exported = {}
    for p in result["procedures"]:
        if p["export"]:
            exported[p["name"]] = transitive(p["name"])
            if exported[p["name"]]["execute"] + exported[p["name"]]["execute_batch"] > 1:
                result["standards"].update(["std436","std729"])
                result["findings"].append({"severity":"MEDIUM","type":"MULTIPLE_TRANSITIVE_DB_CALLS","procedure":p["name"],"topology":exported[p["name"]]})
    result["exported_io_topology"] = exported
    result["summary"] = {
        "procedures": len(result["procedures"]),
        "execute": sum(p["execute"] for p in result["procedures"]),
        "execute_batch": sum(p["execute_batch"] for p in result["procedures"]),
        "bulk_reads": sum(p["bulk_reads"] for p in result["procedures"]),
        "high_findings": sum(1 for x in result["findings"] if x["severity"]=="HIGH"),
        "medium_findings": sum(1 for x in result["findings"] if x["severity"]=="MEDIUM"),
        "review_findings": sum(1 for x in result["findings"] if x["severity"]=="REVIEW"),
        "direct_form_data_accesses": sum(p.get("direct_form_data_accesses",0) for p in result["procedures"]),
        "nested_form_data_paths": sum(p.get("nested_form_data_paths",0) for p in result["procedures"]),
    }
    result["standards"] = sorted(result["standards"])
    return result

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--output")
    ap.add_argument("--known-symbol",action="append",default=[])
    ap.add_argument("--bare-symbol-scope-complete",action="store_true")
    ap.add_argument("--require-bare-symbol-proof",action="store_true")
    ap.add_argument("--changed-line-range",action="append",default=[],metavar="START:END")
    args = ap.parse_args()
    changed_ranges=[]
    for raw in args.changed_line_range:
        parts=raw.split(":",1)
        if len(parts)!=2:
            ap.error("--changed-line-range must be START:END")
        try:
            changed_ranges.append((int(parts[0]),int(parts[1])))
        except ValueError:
            ap.error("--changed-line-range must contain integers")
    r = analyze(
        args.path,
        bare_symbol_scope_complete=args.bare_symbol_scope_complete,
        known_symbols=args.known_symbol,
        changed_line_ranges=changed_ranges if args.changed_line_range else None,
    )
    out = json.dumps(r, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(out, encoding="utf-8")
    print(out)
    if args.require_bare_symbol_proof and (r.get("bare_symbol_validation") or {}).get("status")!="PASS":
        raise SystemExit(2)