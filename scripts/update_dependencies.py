#!/usr/bin/env python3
"""Update dependency versions in pyproject.toml based on pip list --outdated and pip-audit."""

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


def get_vulnerable_packages() -> list[dict[str, Any]]:
    """Get list of packages with known vulnerabilities from pip-audit.

    Returns:
        List of dicts with 'name', 'version', 'fix_versions', and 'vulns' keys
    """
    result = subprocess.run(
        [sys.executable, "-m", "pip_audit", "--format=json", "--progress-spinner=off"],
        capture_output=True,
        text=True,
    )

    # pip-audit returns non-zero if vulnerabilities found, but still outputs JSON
    if not result.stdout:
        if "No module named pip_audit" in result.stderr:
            print("Warning: pip-audit not installed. Run: pip install pip-audit", file=sys.stderr)
        return []

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return []

    # Group vulnerabilities by package
    vulnerable: dict[str, dict[str, str | list[str]]] = {}
    for dep in data.get("dependencies", []):
        vulns = dep.get("vulns", [])
        if vulns:
            name = dep["name"]
            version = dep["version"]
            # Get the highest fix version from all vulnerabilities
            fix_versions = set()
            vuln_ids = []
            for vuln in vulns:
                vuln_ids.append(vuln.get("id", "unknown"))
                for fix in vuln.get("fix_versions", []):
                    fix_versions.add(fix)

            vulnerable[name] = {
                "name": name,
                "version": version,
                "fix_versions": sorted(fix_versions, reverse=True),
                "vulns": vuln_ids,
            }

    return list(vulnerable.values())


def get_outdated_packages() -> list[dict[str, str]]:
    """Get list of outdated packages from pip.

    Returns:
        List of dicts with 'name', 'version' (current), and 'latest_version' keys
    """
    result = subprocess.run(
        [sys.executable, "-m", "pip", "list", "--outdated", "--format=json"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"Error running pip list: {result.stderr}", file=sys.stderr)
        return []

    packages: list[dict[str, str]] = json.loads(result.stdout)
    return packages


def normalize_name(name: str) -> str:
    """Normalize package name for comparison (PEP 503)."""
    return re.sub(r"[-_.]+", "-", name).lower()


def update_pyproject(
    pyproject_path: Path, outdated: list[dict[str, str]], dry_run: bool = False
) -> int:
    """Update version constraints in pyproject.toml.

    Args:
        pyproject_path: Path to pyproject.toml
        outdated: List of outdated packages from pip
        dry_run: If True, only print what would be changed

    Returns:
        Number of packages updated
    """
    content = pyproject_path.read_text()
    original_content = content
    updated_count = 0

    # Create lookup dict with normalized names
    outdated_lookup = {normalize_name(pkg["name"]): pkg for pkg in outdated}

    # Pattern to match dependency lines like: "package>=1.0.0" or "package[extra]>=1.0.0"
    # Captures: package name, optional extras, operator, version
    dep_pattern = re.compile(
        r'"([a-zA-Z0-9_-]+)(\[[^\]]+\])?(>=|<=|==|~=|>|<)([0-9]+\.[0-9]+\.?[0-9]*)"'
    )

    def replace_version(match: re.Match[str]) -> str:
        pkg_name = match.group(1)
        extras = match.group(2) or ""
        operator = match.group(3)
        old_version = match.group(4)

        normalized = normalize_name(pkg_name)
        if normalized in outdated_lookup:
            new_version = outdated_lookup[normalized]["latest_version"]
            if old_version != new_version:
                nonlocal updated_count
                updated_count += 1
                action = "Would update" if dry_run else "Updating"
                print(f"  {action}: {pkg_name} {operator}{old_version} -> {operator}{new_version}")
                return f'"{pkg_name}{extras}{operator}{new_version}"'

        return match.group(0)

    content = dep_pattern.sub(replace_version, content)

    if not dry_run and content != original_content:
        pyproject_path.write_text(content)
        print(f"\nUpdated {pyproject_path}")

    return updated_count


def main() -> None:
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Update dependency versions in pyproject.toml")
    parser.add_argument(
        "--dry-run",
        "-n",
        action="store_true",
        help="Show what would be updated without making changes",
    )
    parser.add_argument(
        "--pyproject",
        type=Path,
        default=Path("pyproject.toml"),
        help="Path to pyproject.toml (default: ./pyproject.toml)",
    )
    parser.add_argument(
        "--security-only",
        "-s",
        action="store_true",
        help="Only check for security vulnerabilities (skip outdated check)",
    )
    args = parser.parse_args()

    if not args.pyproject.exists():
        print(f"Error: {args.pyproject} not found", file=sys.stderr)
        sys.exit(1)

    # Check for vulnerabilities first
    print("Checking for security vulnerabilities (pip-audit)...")
    vulnerable = get_vulnerable_packages()

    if vulnerable:
        print(f"\n⚠️  Found {len(vulnerable)} package(s) with known vulnerabilities:")
        for pkg in vulnerable:
            fix = pkg["fix_versions"][0] if pkg["fix_versions"] else "unknown"
            vuln_count = len(pkg["vulns"])
            print(f"  {pkg['name']}: {pkg['version']} -> {fix} ({vuln_count} CVE(s))")
            # Show first 3 CVE IDs
            for vuln_id in pkg["vulns"][:3]:
                print(f"    - {vuln_id}")
            if len(pkg["vulns"]) > 3:
                print(f"    - ... and {len(pkg['vulns']) - 3} more")
    else:
        print("✓ No known vulnerabilities found")

    if args.security_only:
        if vulnerable:
            print("\nTo fix vulnerabilities in transitive dependencies, run:")
            print("  pip install --upgrade " + " ".join(pkg["name"] for pkg in vulnerable))
        return

    print("\nChecking for outdated packages...")
    outdated = get_outdated_packages()

    if not outdated:
        print("✓ All packages are up to date!")
        if not vulnerable:
            return
    else:
        print(f"\nFound {len(outdated)} outdated package(s):")
        for pkg in outdated:
            # Mark vulnerable packages
            is_vuln = any(
                normalize_name(v["name"]) == normalize_name(pkg["name"]) for v in vulnerable
            )
            marker = " ⚠️" if is_vuln else ""
            print(f"  {pkg['name']}: {pkg['version']} -> {pkg['latest_version']}{marker}")

    print(f"\n{'[DRY RUN] ' if args.dry_run else ''}Updating pyproject.toml...")
    updated = update_pyproject(args.pyproject, outdated, dry_run=args.dry_run)

    if updated == 0:
        print("\nNo matching dependencies found in pyproject.toml to update.")
        print("(Some packages may be transitive dependencies not listed directly)")
    else:
        print(f"\n{'Would update' if args.dry_run else 'Updated'} {updated} dependency version(s)")
        if not args.dry_run:
            print("\nRun 'pip install -e .[dev]' to install the updated versions")

    # Show command to fix remaining transitive vulnerabilities
    if vulnerable:
        # Filter out packages that are in pyproject.toml (they'll be updated via pip install)
        transitive_vulns = [
            pkg["name"]
            for pkg in vulnerable
            if normalize_name(pkg["name"]) not in {normalize_name(p["name"]) for p in outdated}
        ]
        if transitive_vulns:
            print("\nTo fix remaining transitive dependency vulnerabilities, run:")
            print("  pip install --upgrade " + " ".join(transitive_vulns))


if __name__ == "__main__":
    main()
