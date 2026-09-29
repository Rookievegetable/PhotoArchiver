"""Stage 1 architecture audit diagnostic — build the ACTUAL import dependency graph.

Read-only AST scan of src/photo_archiver (no project code modified/loaded).
Outputs:
  1. layer -> layer edge counts (with file:line evidence)
  2. module-level circular imports (Tarjan SCC, file granularity)
  3. deferred (function-level) imports — potential hidden cycles / lazy coupling
  4. third-party imports per layer (for approval-list cross-check)
  5. size hotspots: top files by lines, largest functions, class counts

Usage: .venv/Scripts/python.exe docs/health-check/evidence/arch_dependency_scan.py
"""

from __future__ import annotations

import ast
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src" / "photo_archiver"

LAYERS = ["app", "presentation", "application", "domain", "infrastructure", "workers", "ai", "plugins", "common"]


def layer_of(rel: str) -> str:
    parts = rel.split("/")
    return parts[1] if parts[0] == "photo_archiver" and len(parts) > 1 else "unknown"


def module_name(rel: str) -> str:
    return rel[:-3].replace("/", ".")


files: dict[str, Path] = {}  # module_name -> path
for p in sorted(SRC.rglob("*.py")):
    rel = p.relative_to(SRC.parent).as_posix()
    files[module_name(rel)] = p

layer_edges: dict[tuple[str, str], list[str]] = defaultdict(list)
module_edges: dict[str, set[str]] = defaultdict(set)
deferred_imports: list[dict] = []
third_party: dict[str, set[str]] = defaultdict(set)
stats: list[dict] = []

for mod, path in files.items():
    lay = layer_of(mod.replace(".", "/"))
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    n_lines = len(path.read_text(encoding="utf-8").splitlines())
    n_class = sum(isinstance(n, ast.ClassDef) for n in tree.body)
    funcs = [(n.name, (n.end_lineno or n.lineno) - n.lineno + 1) for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    biggest = max(funcs, key=lambda f: f[1]) if funcs else ("-", 0)
    stats.append({"module": mod, "lines": n_lines, "classes": n_class, "functions": len(funcs), "biggest_fn": biggest[0], "biggest_fn_lines": biggest[1]})

    for node in ast.walk(tree):
        names: list[str] = []
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level > 0:
                names = ["<relative-import>"]
            elif node.module:
                names = [node.module]
        else:
            continue
        for name in names:
            if name.startswith("photo_archiver"):
                target_mod = name
                # resolve package import to its __init__
                if target_mod in files or target_mod + ".__init__" in files:
                    resolved = target_mod if target_mod in files else target_mod + ".__init__"
                else:
                    # from pkg.mod import X — target module itself
                    resolved = target_mod
                    while resolved not in files and "." in resolved:
                        resolved = resolved.rsplit(".", 1)[0]
                if resolved not in files:
                    continue
                t_lay = layer_of(resolved.replace(".", "/"))
                module_edges[mod].add(resolved)
                if t_lay != lay:
                    layer_edges[(lay, t_lay)].append(f"{mod} -> {resolved}")
            elif name == "<relative-import>":
                layer_edges[(lay, "<relative>")].append(f"{mod} (relative import)")
            else:
                third_party[lay].add(name.split(".")[0])

        # deferred import detection (import inside function/method body)
        for anc in ast.walk(tree):
            if isinstance(anc, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for sub in ast.walk(anc):
                    if isinstance(sub, (ast.Import, ast.ImportFrom)):
                        mods = [a.name for a in sub.names] if isinstance(sub, ast.Import) else ([sub.module] if sub.module else [])
                        if any(m.startswith("photo_archiver") for m in mods):
                            deferred_imports.append({"module": mod, "in_fn": anc.name, "line": sub.lineno, "imports": mods})

# Tarjan SCC over module graph
index_counter = [0]
stack, lowlink, index, on_stack = [], {}, {}, {}
result_sccs = []


def strongconnect(v):
    index[v] = lowlink[v] = index_counter[0]
    index_counter[0] += 1
    stack.append(v)
    on_stack[v] = True
    for w in module_edges.get(v, ()):
        if w not in index:
            strongconnect(w)
            lowlink[v] = min(lowlink[v], lowlink[w])
        elif on_stack.get(w):
            lowlink[v] = min(lowlink[v], index[w])
    if lowlink[v] == index[v]:
        scc = []
        while True:
            w = stack.pop()
            on_stack[w] = False
            scc.append(w)
            if w == v:
                break
        if len(scc) > 1:
            result_sccs.append(sorted(scc))


sys.setrecursionlimit(10000)
for v in files:
    if v not in index:
        strongconnect(v)

print("=== LAYER EDGES (cross-layer, count) ===")
for (a, b), ev in sorted(layer_edges.items()):
    print(f"{a:15s} -> {b:15s} {len(ev):4d}")

print("\n=== SCC (module-level cycles, size>=2) ===")
print(json.dumps(result_sccs, indent=1) if result_sccs else "none")

print(f"\n=== DEFERRED (function-level) photo_archiver imports: {len(deferred_imports)} ===")
for d in deferred_imports:
    print(f"{d['module']} :: {d['in_fn']}:{d['line']} -> {d['imports']}")

print("\n=== THIRD-PARTY PER LAYER (top-level) ===")
for lay in LAYERS:
    print(f"{lay:15s}: {sorted(third_party.get(lay, []))}")

print("\n=== TOP 25 FILES BY LINES ===")
for s in sorted(stats, key=lambda x: -x["lines"])[:25]:
    print(f"{s['lines']:6d}  cls={s['classes']:3d} fn={s['functions']:4d} biggest={s['biggest_fn']}({s['biggest_fn_lines']})  {s['module']}")

print("\n=== FUNCTIONS > 120 LINES ===")
for s in sorted(stats, key=lambda x: -x["biggest_fn_lines"]):
    if s["biggest_fn_lines"] > 120:
        print(f"{s['biggest_fn_lines']:5d}  {s['module']}::{s['biggest_fn']}")

Path(__file__).with_name("arch_scan_result.json").write_text(
    json.dumps(
        {
            "layer_edges": {f"{a}->{b}": v for (a, b), v in layer_edges.items()},
            "sccs": result_sccs,
            "deferred_imports": deferred_imports,
            "third_party": {k: sorted(v) for k, v in third_party.items()},
            "stats": sorted(stats, key=lambda x: -x["lines"]),
        },
        ensure_ascii=False,
        indent=1,
    ),
    encoding="utf-8",
)
print("\nsaved arch_scan_result.json")
