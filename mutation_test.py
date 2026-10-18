"""Lightweight AST mutation testing for fraud_detector/engine.py.

Mutates comparison operators, boolean operators, augmented assignments,
`not` and numeric literals INSIDE function bodies, runs the full pytest suite
against every mutant, and reports the mutation score (killed / total).
"""
import ast, copy, json, os, shutil, subprocess, sys, tempfile
from concurrent.futures import ThreadPoolExecutor

SRC = "fraud_detector/engine.py"
CMP = {ast.GtE: [ast.Gt, ast.Lt], ast.Gt: [ast.GtE, ast.LtE],
       ast.LtE: [ast.Lt, ast.GtE], ast.Lt: [ast.LtE, ast.Gt]}


def sites(tree):
    out = []
    for fn in [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]:
        doc = ast.get_docstring(fn, clean=False)
        for node in ast.walk(fn):
            if isinstance(node, ast.Compare):
                for i, op in enumerate(node.ops):
                    for new in CMP.get(type(op), []):
                        out.append((node, "cmp", i, new, fn.name))
            elif isinstance(node, ast.BoolOp):
                out.append((node, "bool", None, ast.Or if isinstance(node.op, ast.And) else ast.And, fn.name))
            elif isinstance(node, ast.AugAssign) and isinstance(node.op, ast.Add):
                out.append((node, "aug", None, ast.Sub, fn.name))
            elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
                out.append((node, "not", None, None, fn.name))
            elif (isinstance(node, ast.Constant) and isinstance(node.value, (int, float))
                  and not isinstance(node.value, bool)):
                out.append((node, "const", None, None, fn.name))
    return out


def build(idx):
    tree = ast.parse(open(SRC).read())
    all_sites = sites(tree)
    node, kind, i, new, fname = all_sites[idx]
    desc = f"{fname}: line {node.lineno} {kind}"
    if kind == "cmp":
        desc += f" {type(node.ops[i]).__name__}->{new.__name__}"
        node.ops[i] = new()
    elif kind == "bool":
        desc += f" {type(node.op).__name__}->{new.__name__}"
        node.op = new()
    elif kind == "aug":
        desc += " += -> -="
        node.op = new()
    elif kind == "not":
        desc += " remove 'not'"
        # replace UnaryOp(Not, x) by x  (mutate in place)
        node.op = ast.UAdd()
    else:
        old = node.value
        node.value = old + 1 if isinstance(old, int) else (old * 1.01 if old else 1.0)
        desc += f" const {old}->{node.value}"
    ast.fix_missing_locations(tree)
    return ast.unparse(tree), desc, len(all_sites)


def run(idx):
    code, desc, _ = build(idx)
    tmp = tempfile.mkdtemp()
    try:
        for d in ("fraud_detector", "tests", "templates"):
            shutil.copytree(d, os.path.join(tmp, d), ignore=shutil.ignore_patterns("__pycache__"))
        open(os.path.join(tmp, SRC), "w").write(code)
        r = subprocess.run([sys.executable, "-m", "pytest", "-x", "-q", "-p", "no:cacheprovider"],
                           cwd=tmp, capture_output=True, text=True, timeout=120)
        return idx, desc, r.returncode != 0
    except subprocess.TimeoutExpired:
        return idx, desc, True
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    n = build(0)[2]
    with ThreadPoolExecutor(4) as ex:
        res = sorted(ex.map(run, range(n)))
    killed = sum(1 for _, _, k in res if k)
    survivors = [d for _, d, k in res if not k]
    json.dump({"total": n, "killed": killed, "survived": n - killed,
               "score": round(100 * killed / n, 1), "survivors": survivors},
              open("results/mutation.json", "w"), indent=2)
    print(f"mutants={n} killed={killed} survived={n-killed} score={100*killed/n:.1f}%")
    for s in survivors:
        print("SURVIVED:", s)
