"""Summarise Trivy / Bandit / pip-audit JSON reports for the vulnerability report.

Usage (after the Jenkins pipeline has run, or after running the tools by hand):
    python scripts/vuln_summary.py reports
It reads reports/trivy-image.json, trivy-fs.json, bandit.json, pip-audit.json
(any that exist) and prints Markdown tables you can copy into the report.
"""
import json
import sys
from collections import Counter
from pathlib import Path

ORDER = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "UNKNOWN"]


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def counts_line(counter: Counter) -> str:
    return ", ".join(f"{s}: {counter.get(s, 0)}" for s in ORDER)


def trivy_section(path: Path, title: str, limit: int = 15) -> None:
    data = load(path)
    if data is None:
        print(f"\n## {title}\n(file {path.name} not found)")
        return
    vulns, misconf, secrets = [], [], []
    for res in data.get("Results") or []:
        target = res.get("Target", "")
        for v in res.get("Vulnerabilities") or []:
            vulns.append((v.get("Severity", "UNKNOWN"), v.get("VulnerabilityID", ""), v.get("PkgName", ""),
                          v.get("InstalledVersion", ""), v.get("FixedVersion") or "no fix yet",
                          (v.get("Title") or "")[:60], target))
        for m in res.get("Misconfigurations") or []:
            misconf.append((m.get("Severity", "UNKNOWN"), m.get("ID", ""), (m.get("Title") or "")[:60], target))
        secrets.extend(res.get("Secrets") or [])
    print(f"\n## {title}")
    print(f"Artifact: {data.get('ArtifactName', '?')}")
    print(f"Vulnerabilities: {len(vulns)}  ({counts_line(Counter(v[0] for v in vulns))})")
    print(f"Misconfigurations: {len(misconf)}  ({counts_line(Counter(m[0] for m in misconf))})")
    print(f"Secrets found: {len(secrets)}")
    vulns.sort(key=lambda r: ORDER.index(r[0]) if r[0] in ORDER else 9)
    if vulns:
        print("\n| Severity | ID | Package | Installed | Fixed in | Title |\n|---|---|---|---|---|---|")
        for v in vulns[:limit]:
            print(f"| {v[0]} | {v[1]} | {v[2]} | {v[3]} | {v[4]} | {v[5]} |")
        if len(vulns) > limit:
            print(f"\n(showing {limit} of {len(vulns)}; the rest are in {path.name})")
    if misconf:
        print("\n| Severity | ID | Issue | File |\n|---|---|---|---|")
        for m in misconf[:limit]:
            print(f"| {m[0]} | {m[1]} | {m[2]} | {m[3]} |")


def bandit_section(path: Path) -> None:
    data = load(path)
    print("\n## Bandit (Python SAST)")
    if data is None:
        print(f"(file {path.name} not found)")
        return
    results = data.get("results", [])
    loc = data.get("metrics", {}).get("_totals", {}).get("loc", "?")
    print(f"Lines scanned: {loc}   Issues: {len(results)}")
    for r in results:
        print(f"- {r['issue_severity']} / {r['issue_confidence']}: {r['issue_text']} ({r['filename']}:{r['line_number']})")


def pip_audit_section(path: Path) -> None:
    data = load(path)
    print("\n## pip-audit (Python dependencies)")
    if data is None:
        print(f"(file {path.name} not found)")
        return
    deps = data.get("dependencies", data) if isinstance(data, dict) else data
    found = [(d.get("name"), d.get("version"), v.get("id"), ", ".join(v.get("fix_versions", [])))
             for d in deps for v in d.get("vulns", [])]
    print(f"Packages checked: {len(deps)}   Vulnerabilities: {len(found)}")
    for name, ver, vid, fix in found:
        print(f"- {name} {ver}: {vid} (fixed in {fix or 'n/a'})")


if __name__ == "__main__":
    folder = Path(sys.argv[1] if len(sys.argv) > 1 else "reports")
    trivy_section(folder / "trivy-fs.json", "Trivy: source, dependencies, secrets and config")
    trivy_section(folder / "trivy-image.json", "Trivy: Docker image")
    bandit_section(folder / "bandit.json")
    pip_audit_section(folder / "pip-audit.json")
