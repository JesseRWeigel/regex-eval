#!/usr/bin/env python3
"""Scan every tracked file for anything that should not be public, with controls that prove it read.

A scanner that opens no files is silent in exactly the same way as a clean tree, so this one plants
credential-shaped strings in a file it then scans and fails unless it finds every one of them. It
also fails when almost nothing is tracked, because before the first commit `git ls-files` returns
nothing and a scan over zero files passes without ever opening one.

The patterns are assembled from fragments at runtime so this file does not match its own pattern
list. A NUL byte anywhere makes git and grep treat a file as binary and skip it, so a binary file
is a finding here rather than something to pass over.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PATTERNS = [
    ("aws access key", re.compile("AKIA" + r"[0-9A-Z]{16}")),
    ("openai style key", re.compile("sk" + "-" + r"[A-Za-z0-9]{20,}")),
    ("github token", re.compile("gh" + "[pousr]" + "_" + r"[A-Za-z0-9]{30,}")),
    ("openrouter key", re.compile("sk" + "-or-" + r"v1-[A-Za-z0-9]{32,}")),
    ("private key block", re.compile("-----BEGIN " + r"[A-Z ]*PRIVATE KEY-----")),
    ("bearer header", re.compile(r"[Aa]uthorization:\s*[Bb]earer\s+[A-Za-z0-9._\-]{16,}")),
    ("password assignment", re.compile(r"(?i)\b(password|passwd|secret)\s*[=:]\s*['\"][^'\"]{6,}")),
    ("home path", re.compile("/" + "home/" + r"[a-z][a-z0-9_-]+/")),
    ("email address", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")),
]

# The corpus deliberately contains an at sign free of any domain, and nothing in this repository
# is a real address. Anything that looks like one is a finding.
ALLOWED_EMAILS: set = set()
ALLOWED_BINARY: set = set()

CONTROLS = [
    "AKIA" + "B" * 16,
    "sk" + "-" + "A" * 32,
    "gh" + "p" + "_" + "C" * 36,
    "-----BEGIN " + "RSA PRIVATE KEY-----",
    "/" + "home/" + "someone/secret/",
    "person" + "@" + "example.com",
]


def tracked_files() -> list:
    out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True,
                         check=False)
    return [line for line in out.stdout.splitlines() if line.strip()]


def scan_text(name: str, text: str) -> list:
    findings = []
    for label, pattern in PATTERNS:
        for match in pattern.finditer(text):
            if label == "email address" and match.group(0) in ALLOWED_EMAILS:
                continue
            findings.append(f"{name}: {label}: {match.group(0)[:48]}")
    return findings


def scan_file(path: str, name: str) -> tuple:
    with open(path, "rb") as handle:
        blob = handle.read()
    if b"\x00" in blob and name not in ALLOWED_BINARY:
        return ([f"{name}: contains a NUL byte, which makes git and grep skip it as binary and "
                 f"makes this scan blind to the whole file"], 0)
    try:
        text = blob.decode("utf-8")
    except UnicodeDecodeError:
        return ([f"{name}: is not valid UTF-8, so it was not scanned"], 0)
    return (scan_text(name, text), len(blob))


def main() -> int:
    names = tracked_files()
    if len(names) < 10:
        print(f"   FAIL only {len(names)} tracked file(s). A scan over an empty index passes "
              f"without opening anything, which is not the same as a clean tree.")
        return 1

    findings: list = []
    read_bytes = 0
    for name in names:
        path = os.path.join(ROOT, name)
        if not os.path.exists(path):
            continue
        problems, size = scan_file(path, name)
        findings += problems
        read_bytes += size

    # Positive controls, in a file the scanner then reads for real.
    with tempfile.TemporaryDirectory() as directory:
        planted = os.path.join(directory, "planted.txt")
        with open(planted, "w", encoding="utf-8") as handle:
            handle.write("\n".join(CONTROLS) + "\n")
        caught, _ = scan_file(planted, "planted.txt")
    missed = [control for control in CONTROLS
              if not any(control[:18] in line for line in caught)]
    if missed:
        print(f"   FAIL the scanner missed {len(missed)} planted control(s): {missed}")
        return 1

    # A negative control: a file with nothing to find must produce nothing.
    if scan_text("clean.txt", "the quick brown fox\n1.2.3.4\n#abc\n"):
        print("   FAIL the scanner reported a finding on a clean control")
        return 1

    if findings:
        print(f"   FAIL {len(findings)} finding(s) in tracked files:")
        for line in findings[:20]:
            print(f"     {line}")
        return 1

    print(f"   {len(names)} tracked files, {read_bytes} bytes read, no findings; "
          f"{len(CONTROLS)} planted controls all caught and a clean control stayed clean")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
