#!/usr/bin/env python3
"""Bounded physical inventory + analyzable corpus for 1C/Cleverence artifacts.

The inventory intentionally sees more than the analyzers consume. Artifact scope
must be discovered before filtering by source-code suffix. Nested ZIP traversal is
bounded to avoid silent skips and unbounded decompression.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path, PurePosixPath
from collections import Counter
import argparse
import hashlib
import io
import json
import re
import zipfile

ANALYZABLE_SUFFIXES={".bsl",".os",".xml",".mslx"}
ANALYZABLE_FILENAMES={"package.bin"}
DEFAULT_LIMITS={
    "max_depth":3,
    "max_entries":20000,
    "max_entry_uncompressed":64*1024*1024,
    "max_total_uncompressed":512*1024*1024,
    "max_nested_zip_bytes":128*1024*1024,
}
RUNTIME_NAMES={"cells.sqlite","messages.xml"}
RUNTIME_ROOTS={"devicestorage","useraddedproducts","connections","logs","server","xlscsv","data","backup"}
LEGACY_EXPORT_ROOT_NAMES={
    "1cconfigs.xml","appdescription.xml","customsettings.xml","default_customsettings.xml",
    "documents.zip","onremoteinstall.xml","onupdate.xml","settings.xml"
}

@dataclass
class CorpusEntry:
    entry_id:str
    physical_path:str
    semantic_path:str
    routing_aliases:list[str]
    origin:str
    container_chain:list[str]
    depth:int
    size:int
    compressed_size:int|None
    sha256:str|None
    is_container:bool
    analyzable:bool
    bytes_loaded:bool
    suffix:str


def _norm(name:str)->str:return name.replace("\\","/").lstrip("/")
def _is_analyzable(name:str)->bool:
    p=PurePosixPath(_norm(name))
    return p.suffix.lower() in ANALYZABLE_SUFFIXES or p.name.lower() in ANALYZABLE_FILENAMES

def _semantic_path(physical_path:str)->str:
    """Normalize known delivery wrappers without making representation the identity."""
    leaf=_norm(physical_path).split("!/")[-1]
    if leaf.startswith("Configuration/"):return leaf[len("Configuration/"):]
    if leaf.startswith("WinClient/Configuration/"):return leaf[len("WinClient/Configuration/"):]
    return leaf

def _routing_aliases(physical_path:str,semantic_path:str)->list[str]:
    """Expose stable routing names without changing physical provenance.

    Existing registry path rules historically use Configuration/... . Legacy exports
    and unpacked Documents subsets are normalized into the same configuration
    namespace here instead of duplicating artifact-layout logic in the registry.
    """
    aliases=[semantic_path]
    if semantic_path.startswith(("Operations/","Metadata/","DocumentTypes/")):
        aliases.append(f"Configuration/{semantic_path}")
    leaf=_norm(physical_path).split("!/")[-1]
    if leaf not in aliases:aliases.append(leaf)
    return list(dict.fromkeys(aliases))

def _decode(data:bytes)->str:
    for enc in ("utf-8-sig","utf-8","cp1251"):
        try:return data.decode(enc)
        except UnicodeDecodeError:pass
    return data.decode("utf-8",errors="replace")

def _entry_family(row:CorpusEntry,data:bytes)->tuple[bool,bool]:
    semantic=_norm(row.semantic_path); suffix=PurePosixPath(semantic).suffix.lower(); basename=PurePosixPath(semantic).name.lower(); text=_decode(data)
    onec=suffix in {".bsl",".os"} or basename=="package.bin" or bool(re.search(r"https?://v8\.1c\.ru/|<MetaDataObject\b|<Form\b[^>]*xcf/logform|<package\b[^>]*targetNamespace",text,re.I))
    cleverence=semantic.startswith(("Operations/","Metadata/","DocumentTypes/")) or semantic.lower()=="environment.mslx" or bool(re.search(r"<(?:\w+:)?(?:Operation|\w+Action|ContainerTypesBook|CommonFieldInfoCollection|DocumentType)\b",text,re.I))
    return onec,cleverence

class _Budget:
    def __init__(self,limits):
        self.limits=dict(DEFAULT_LIMITS); self.limits.update(limits or {})
        self.entries=0; self.total_uncompressed=0; self.warnings=[]
    def accept(self,size:int,physical_path:str)->bool:
        self.entries+=1; self.total_uncompressed+=max(size,0)
        if self.entries>self.limits["max_entries"]:
            self.warnings.append({"type":"ENTRY_BUDGET_EXCEEDED","path":physical_path,"limit":self.limits["max_entries"]}); return False
        if size>self.limits["max_entry_uncompressed"]:
            self.warnings.append({"type":"ENTRY_SIZE_LIMIT","path":physical_path,"size":size,"limit":self.limits["max_entry_uncompressed"]}); return False
        if self.total_uncompressed>self.limits["max_total_uncompressed"]:
            self.warnings.append({"type":"TOTAL_SIZE_BUDGET_EXCEEDED","path":physical_path,"total":self.total_uncompressed,"limit":self.limits["max_total_uncompressed"]}); return False
        return True


def _append_entry(rows,name,origin,chain,depth,size,compressed,is_container,data=None):
    normalized=_norm(name); semantic=_semantic_path(normalized); analyzable=_is_analyzable(normalized)
    entry=CorpusEntry(
        entry_id=f"entry-{len(rows)+1:08d}",
        physical_path=normalized,semantic_path=semantic,routing_aliases=_routing_aliases(normalized,semantic),origin=origin,
        container_chain=list(chain),depth=depth,size=size,compressed_size=compressed,
        sha256=hashlib.sha256(data).hexdigest() if data is not None else None,
        is_container=is_container,analyzable=analyzable,bytes_loaded=data is not None,
        suffix=PurePosixPath(normalized).suffix.lower()
    )
    rows.append(entry)
    return entry


def _walk_zip_bytes(blob:bytes,label:str,origin:str,rows:list[CorpusEntry],payloads:dict[str,bytes],budget:_Budget,depth:int,chain:list[str]):
    if depth>budget.limits["max_depth"]:
        budget.warnings.append({"type":"CONTAINER_DEPTH_LIMIT","path":label,"depth":depth,"limit":budget.limits["max_depth"]}); return
    try:archive=zipfile.ZipFile(io.BytesIO(blob))
    except zipfile.BadZipFile:
        budget.warnings.append({"type":"BAD_ZIP","path":label}); return
    with archive:
        for info in archive.infolist():
            if info.is_dir():continue
            physical=f"{label}!/{_norm(info.filename)}"
            if not budget.accept(info.file_size,physical):continue
            nested=info.filename.lower().endswith(".zip")
            need_bytes=_is_analyzable(info.filename) or nested
            data=None
            if need_bytes:
                if nested and info.file_size>budget.limits["max_nested_zip_bytes"]:
                    budget.warnings.append({"type":"NESTED_ZIP_SIZE_LIMIT","path":physical,"size":info.file_size,"limit":budget.limits["max_nested_zip_bytes"]})
                else:
                    try:data=archive.read(info)
                    except (RuntimeError,zipfile.BadZipFile,OSError):budget.warnings.append({"type":"ZIP_ENTRY_READ_FAILED","path":physical})
            entry=_append_entry(rows,physical,f"{origin}!/{info.filename}",chain,depth,info.file_size,info.compress_size,nested,data)
            if data is not None and _is_analyzable(info.filename):payloads[entry.entry_id]=data
            if nested and data is not None:
                _walk_zip_bytes(data,physical,f"{origin}!/{info.filename}",rows,payloads,budget,depth+1,[*chain,physical])


def inventory_paths(paths,limits=None):
    rows:list[CorpusEntry]=[]; payloads:dict[str,bytes]={}; budget=_Budget(limits)
    for source in [Path(x) for x in paths]:
        if not source.exists():raise FileNotFoundError(source)
        if source.is_dir():
            for item in sorted(x for x in source.rglob("*") if x.is_file()):
                rel=item.relative_to(source).as_posix(); size=item.stat().st_size
                if not budget.accept(size,rel):continue
                is_zip=zipfile.is_zipfile(item)
                data=item.read_bytes() if (_is_analyzable(rel) or is_zip) else None
                entry=_append_entry(rows,rel,str(item),[],0,size,None,is_zip,data)
                if data is not None and _is_analyzable(rel):payloads[entry.entry_id]=data
                if is_zip and data is not None:_walk_zip_bytes(data,rel,str(item),rows,payloads,budget,1,[rel])
        elif zipfile.is_zipfile(source):
            blob=source.read_bytes(); label=source.name
            _append_entry(rows,label,str(source),[],0,len(blob),None,True,None)
            _walk_zip_bytes(blob,label,str(source),rows,payloads,budget,1,[label])
        else:
            size=source.stat().st_size
            if budget.accept(size,source.name):
                data=source.read_bytes() if _is_analyzable(source.name) else None
                entry=_append_entry(rows,source.name,str(source),[],0,size,None,False,data)
                if data is not None:payloads[entry.entry_id]=data
    model=_classify(rows,payloads,budget.warnings)
    return {"entries":rows,"payloads":payloads,"warnings":budget.warnings,"artifact_model":model}


def _classify(rows,payloads,warnings):
    paths=[_norm(r.physical_path) for r in rows]; semantic=[_norm(r.semantic_path) for r in rows]
    names={PurePosixPath(p.split("!/")[-1]).name.lower() for p in paths}
    roots={p.split("!/")[-1].split("/",1)[0].lower() for p in paths if p}
    has_legacy_docs=any(re.search(r"(?:^|!/)documents\.zip(?:!/|$)",p,re.I) for p in paths)
    legacy_root_hits=sorted(names & LEGACY_EXPORT_ROOT_NAMES)
    has_modern_cfg=any(s.startswith(("Operations/","Metadata/","DocumentTypes/")) and ("/Configuration/" in f"/{p}" or "/WinClient/Configuration/" in f"/{p}") for p,s in zip(paths,semantic))
    has_cleverence_semantic=any(s.startswith(("Operations/","Metadata/","DocumentTypes/")) or s.lower()=="environment.mslx" for s in semantic)
    runtime_hits=sorted((names & RUNTIME_NAMES) | (roots & RUNTIME_ROOTS))

    by={r.entry_id:r for r in rows}
    family_flags=[_entry_family(by[entry_id],data) for entry_id,data in payloads.items()]
    has_onec=any(onec for onec,_ in family_flags)
    has_cleverence_content=any(cleverence for _,cleverence in family_flags)
    has_cleverence=has_cleverence_semantic or has_cleverence_content

    family="UNKNOWN"; role="UNKNOWN"; layout="UNKNOWN"; confidence="UNRESOLVED"
    if has_cleverence:
        family="CLEVERENCE"; confidence="PROVEN_BY_STRUCTURE"
        if has_legacy_docs and len(legacy_root_hits)>=3:role="CONFIGURATION_EXPORT"; layout="DOCUMENTS_ARCHIVE"
        elif has_modern_cfg:role="CONFIGURATION_SOURCE_TREE"; layout="CONFIGURATION_ROOT"
        else:role="CONFIGURATION_SUBSET"; layout="SUBSET_ROOT"
        if runtime_hits:role="MIXED_ARTIFACT"
        if has_onec:role="MIXED_ARTIFACT"
    elif runtime_hits:
        family="CLEVERENCE"; role="RUNTIME_DATABASE"; layout="RUNTIME_TREE"; confidence="PROVEN_BY_STRUCTURE"
        if has_onec:role="MIXED_ARTIFACT"
    elif has_onec:
        family="ONEC"; role="SOURCE_DUMP_OR_PATCH"; layout="SOURCE_TREE"; confidence="PROVEN_BY_STRUCTURE"

    authoritative=[]
    if family=="CLEVERENCE" and role in {"CONFIGURATION_EXPORT","MIXED_ARTIFACT"} and has_legacy_docs:authoritative.append("Documents.zip!/")
    if family=="CLEVERENCE" and has_modern_cfg:authoritative.append("Configuration/")
    if family=="CLEVERENCE" and role=="CONFIGURATION_SUBSET":authoritative.append("./")
    return {
        "family":family,"role":role,"layout":layout,"confidence":confidence,
        "authoritative_roots":authoritative,"legacy_export_root_hits":legacy_root_hits,
        "runtime_signals":runtime_hits,"contains_onec_source":has_onec,
        "warnings":list(warnings),
        "rule":"Classification is structural evidence for intake/delivery routing, not proof of runtime behavior. UNKNOWN/MIXED must not be silently treated as an exact configuration delivery baseline."
    }


def analyzable_entries(corpus):
    by={r.entry_id:r for r in corpus["entries"]}
    for entry_id,data in corpus["payloads"].items():
        row=by[entry_id]
        yield row.semantic_path,data,row.origin,row


def summarize(corpus):
    rows=corpus["entries"]
    suffixes=Counter((r.suffix or "<none>") for r in rows)
    roots=Counter(r.physical_path.split("!/")[-1].split("/",1)[0] for r in rows if r.physical_path)
    by={r.entry_id:r for r in rows}; kinds=Counter()
    for entry_id,data in corpus["payloads"].items():
        onec,cleverence=_entry_family(by[entry_id],data)
        if onec:kinds["onec"]+=1
        if cleverence:kinds["cleverence"]+=1
        if not onec and not cleverence:kinds["other"]+=1
    return {
        "files":len(corpus["payloads"]),"kinds":{"onec":kinds["onec"],"cleverence":kinds["cleverence"],"other":kinds["other"]},
        "physical_entries":len(rows),"analyzable_entries":len(corpus["payloads"]),
        "containers":sum(1 for r in rows if r.is_container),"max_depth":max((r.depth for r in rows),default=0),
        "suffixes":dict(sorted(suffixes.items())),"top_roots":dict(roots.most_common(25)),
        "artifact_model":corpus["artifact_model"],"warnings":corpus["warnings"]
    }


def main():
    ap=argparse.ArgumentParser(); ap.add_argument("paths",nargs="+"); ap.add_argument("--output"); ap.add_argument("--entries",action="store_true")
    ap.add_argument("--max-depth",type=int); ap.add_argument("--max-entries",type=int); ap.add_argument("--max-entry-uncompressed",type=int); ap.add_argument("--max-total-uncompressed",type=int); ap.add_argument("--max-nested-zip-bytes",type=int)
    a=ap.parse_args(); limits={}
    for key in DEFAULT_LIMITS:
        value=getattr(a,key,None)
        if value is not None:limits[key]=value
    corpus=inventory_paths(a.paths,limits); result=summarize(corpus)
    if a.entries:result["entries"]=[asdict(x) for x in corpus["entries"]]
    out=json.dumps(result,ensure_ascii=False,indent=2)+"\n"
    if a.output:Path(a.output).write_text(out,encoding="utf-8")
    print(out,end="")

if __name__=="__main__":main()
