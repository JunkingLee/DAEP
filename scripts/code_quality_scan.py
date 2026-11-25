#!/usr/bin/env python3
"""Blocking structural quality checks for DAEP Python sources.

The scanner reports stable machine-readable findings and exits non-zero when
it detects duplicate top-level function names or duplicate FastAPI route keys.
This protects the now-converged RC9 baseline from regression.
"""
from __future__ import annotations
import ast, json
from pathlib import Path
from collections import defaultdict

ROOTS=(Path("app"),Path("daep_mcp"),Path("daep_agent_bridge"),Path("daep_worker"))
PY_SUFFIX=".py"

def main():
    functions=defaultdict(list)
    routes=defaultdict(list)
    files=[]
    for root in ROOTS:
        if not root.exists(): continue
        for path in sorted(root.rglob("*")):
            if path.suffix != PY_SUFFIX or any(part=="__pycache__" for part in path.parts): continue
            files.append(path)
            try: tree=ast.parse(path.read_text(encoding="utf-8"),filename=str(path))
            except SyntaxError as e:
                print(json.dumps({"kind":"syntax_error","file":str(path),"line":e.lineno,"message":e.msg})); continue
            for node in tree.body:
                if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)):
                    functions[node.name].append((str(path),node.lineno))
                for dec in getattr(node,"decorator_list",()):
                    if isinstance(dec,ast.Call) and isinstance(dec.func,ast.Attribute) and isinstance(dec.func.value,ast.Name) and dec.func.value.id=="app":
                        if dec.func.attr in {"get","post","put","patch","delete","options","head","websocket"} and dec.args:
                            arg=dec.args[0]
                            if isinstance(arg,ast.Constant) and isinstance(arg.value,str):
                                routes[(dec.func.attr.upper(),arg.value)].append((str(path),node.name,node.lineno))
    duplicate_functions={k:v for k,v in functions.items() if len(v)>1}
    duplicate_routes={f"{m} {p}":v for (m,p),v in routes.items() if len(v)>1}
    findings={
        "files_scanned":len(files),
        "duplicate_function_names":len(duplicate_functions),
        "duplicate_route_keys":len(duplicate_routes),
        "duplicates":duplicate_functions,
        "routes":duplicate_routes,
    }
    print(json.dumps(findings,ensure_ascii=False,indent=2))
    print(f"QUALITY_REPORT files={len(files)} duplicate_functions={len(duplicate_functions)} duplicate_routes={len(duplicate_routes)}")
    return 1 if duplicate_functions or duplicate_routes else 0

if __name__=="__main__":
    raise SystemExit(main())
