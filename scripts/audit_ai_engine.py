#!/usr/bin/env python3
"""
Read-only audit for the secure-surveillance-platform AI engine.

Usage:
    python scripts/audit_ai_engine.py

Optional:
    python scripts/audit_ai_engine.py --root ai-engine
    python scripts/audit_ai_engine.py --root ai-engine --json audit.json
    python scripts/audit_ai_engine.py --root ai-engine --no-tools

The script does NOT modify project files.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
import sys
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DEFAULT_ROOT = Path("ai-engine")

SOURCE_EXTENSIONS = {
    ".py",
    ".yaml",
    ".yml",
    ".json",
    ".toml",
    ".ini",
    ".cfg",
    ".env",
    ".md",
}

PYTHON_EXTENSIONS = {".py"}

IGNORE_DIRS = {
    ".git",
    ".venv",
    "venv",
    "env",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "node_modules",
    "dist",
    "build",
    ".idea",
    ".vscode",
}

PLACEHOLDER_PATTERNS = [
    (r"\bTODO\b", "TODO marker"),
    (r"\bFIXME\b", "FIXME marker"),
    (r"\bXXX\b", "XXX marker"),
    (r"NotImplementedError", "NotImplementedError"),
    (r"\bpass\s*(?:#.*)?$", "pass statement"),
]

SECURITY_PATTERNS = [
    (
        r"(password|passwd|secret|api[_-]?key|token)\s*=\s*['\"][^'\"]+['\"]",
        "Possible hard-coded secret",
    ),
    (
        r"(SECRET_KEY|JWT_SECRET|PRIVATE_KEY)\s*=\s*['\"][^'\"]+['\"]",
        "Possible hard-coded security key",
    ),
]

AI_KEYWORDS = {
    "yolo": "YOLO/object detection",
    "ultralytics": "YOLO/Ultralytics",
    "torch": "PyTorch",
    "tensorflow": "TensorFlow",
    "opencv": "OpenCV/video processing",
    "cv2": "OpenCV/video processing",
    "deepface": "DeepFace/face recognition",
    "face_recognition": "Face recognition",
    "insightface": "InsightFace",
    "easyocr": "EasyOCR/OCR",
    "paddleocr": "PaddleOCR",
    "tesseract": "Tesseract OCR",
    "ocr": "OCR",
    "onnx": "ONNX",
    "transformers": "Transformers",
    "huggingface": "Hugging Face",
}

ARCHITECTURE_TERMS = {
    "detection": [
        "detection",
        "detector",
        "object_detection",
        "inference",
    ],
    "face_recognition": [
        "face",
        "recognition",
        "embedding",
        "identity",
    ],
    "ocr": [
        "ocr",
        "license_plate",
        "licence_plate",
        "plate",
        "text_detection",
    ],
    "video": [
        "video",
        "frame",
        "rtsp",
        "camera",
        "stream",
        "capture",
    ],
    "threat": [
        "threat",
        "classification",
        "classifier",
        "weapon",
        "violence",
        "intrusion",
        "suspicious",
    ],
    "events": [
        "event",
        "detection_event",
        "ai_event",
        "result",
    ],
    "backend": [
        "backend",
        "api",
        "http",
        "requests",
        "httpx",
        "client",
        "ingestion",
        "incident",
        "evidence",
    ],
    "evidence": [
        "evidence",
        "artifact",
        "clip",
        "keyframe",
        "snapshot",
    ],
}


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class Finding:
    severity: str
    category: str
    title: str
    detail: str
    file: str | None = None
    line: int | None = None
    recommendation: str | None = None


@dataclass
class AuditReport:
    root: str
    summary: dict[str, Any]
    findings: list[Finding]
    inventory: dict[str, Any]
    architecture: dict[str, Any]
    tools: dict[str, Any]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def rel(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def iter_files(root: Path):
    for path in root.rglob("*"):
        if not path.is_file():
            continue

        if any(part in IGNORE_DIRS for part in path.parts):
            continue

        if path.suffix.lower() in SOURCE_EXTENSIONS:
            yield path


def iter_python(root: Path):
    for path in iter_files(root):
        if path.suffix.lower() == ".py":
            yield path


def add(
    findings: list[Finding],
    severity: str,
    category: str,
    title: str,
    detail: str,
    file: Path | None = None,
    root: Path | None = None,
    line: int | None = None,
    recommendation: str | None = None,
) -> None:
    findings.append(
        Finding(
            severity=severity,
            category=category,
            title=title,
            detail=detail,
            file=rel(file, root) if file and root else str(file) if file else None,
            line=line,
            recommendation=recommendation,
        )
    )


def run_command(
    command: list[str],
    cwd: Path,
) -> dict[str, Any]:
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )

        return {
            "command": command,
            "returncode": result.returncode,
            "stdout": result.stdout[-12000:],
            "stderr": result.stderr[-12000:],
        }

    except FileNotFoundError:
        return {
            "command": command,
            "returncode": None,
            "stdout": "",
            "stderr": f"Command not found: {command[0]}",
        }

    except subprocess.TimeoutExpired:
        return {
            "command": command,
            "returncode": None,
            "stdout": "",
            "stderr": "Command timed out after 180 seconds.",
        }


def line_number(text: str, match_start: int) -> int:
    return text.count("\n", 0, match_start) + 1


# ---------------------------------------------------------------------------
# Inventory
# ---------------------------------------------------------------------------

def audit_inventory(root: Path, findings: list[Finding]) -> dict[str, Any]:
    files = list(iter_files(root))
    python_files = list(iter_python(root))

    extension_counts = Counter(
        p.suffix.lower() or "<no extension>"
        for p in files
    )

    directories = sorted(
        {
            str(p.relative_to(root))
            for p in root.rglob("*")
            if p.is_dir()
            and not any(part in IGNORE_DIRS for part in p.parts)
        }
    )

    total_lines = 0

    for path in python_files:
        total_lines += read_text(path).count("\n") + 1

    expected_dirs = [
        "detection",
        "face-recognition",
        "ocr",
        "models",
    ]

    expected_any = {
        "detection": ["detection", "detector"],
        "face-recognition": ["face", "recognition"],
        "ocr": ["ocr"],
        "models": ["model", "models"],
    }

    for expected in expected_dirs:
        candidates = expected_any[expected]

        found = any(
            any(
                candidate.lower() in part.lower()
                for candidate in candidates
            )
            for part in root.parts
        )

        found = found or any(
            any(
                candidate.lower() in p.name.lower()
                for candidate in candidates
            )
            for p in root.iterdir()
            if p.is_dir()
        )

        if not found:
            add(
                findings,
                "INFO",
                "structure",
                f"Expected AI module not obvious: {expected}",
                "The expected architecture contains this module, but no obvious "
                "matching directory was found at the AI-engine root.",
                recommendation=(
                    "Confirm whether the functionality exists under another "
                    "name or whether the architecture needs updating."
                ),
            )

    return {
        "file_count": len(files),
        "python_file_count": len(python_files),
        "python_lines_approx": total_lines,
        "extensions": dict(extension_counts),
        "directories": directories,
    }


# ---------------------------------------------------------------------------
# AST analysis
# ---------------------------------------------------------------------------

def audit_python_ast(
    root: Path,
    findings: list[Finding],
) -> dict[str, Any]:
    functions = 0
    classes = 0
    async_functions = 0
    imports = Counter()
    external_imports = Counter()

    dangerous_calls = []

    for path in iter_python(root):
        source = read_text(path)

        try:
            tree = ast.parse(source, filename=str(path))
        except SyntaxError as exc:
            add(
                findings,
                "CRITICAL",
                "syntax",
                "Python syntax error",
                str(exc),
                path,
                root,
                exc.lineno,
                "Fix the syntax error before evaluating runtime behaviour.",
            )
            continue

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                functions += 1

                if isinstance(node, ast.AsyncFunctionDef):
                    async_functions += 1

            elif isinstance(node, ast.ClassDef):
                classes += 1

            elif isinstance(node, ast.Import):
                for alias in node.names:
                    name = alias.name.split(".")[0]
                    imports[name] += 1
                    external_imports[name] += 1

            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    name = node.module.split(".")[0]
                    imports[name] += 1
                    external_imports[name] += 1

            elif isinstance(node, ast.Call):
                func = node.func

                name = None

                if isinstance(func, ast.Name):
                    name = func.id

                elif isinstance(func, ast.Attribute):
                    name = func.attr

                if name in {
                    "eval",
                    "exec",
                    "compile",
                    "__import__",
                }:
                    dangerous_calls.append(
                        {
                            "file": rel(path, root),
                            "line": node.lineno,
                            "call": name,
                        }
                    )

    if dangerous_calls:
        for item in dangerous_calls:
            add(
                findings,
                "HIGH",
                "security",
                f"Dangerous dynamic execution: {item['call']}",
                "Dynamic code execution was found in AI-engine source.",
                root / item["file"],
                root,
                item["line"],
                "Remove dynamic execution or tightly constrain and justify it.",
            )

    return {
        "functions": functions,
        "classes": classes,
        "async_functions": async_functions,
        "imports": dict(imports.most_common()),
        "dangerous_calls": dangerous_calls,
    }


# ---------------------------------------------------------------------------
# Keyword / architecture audit
# ---------------------------------------------------------------------------

def audit_architecture(
    root: Path,
    findings: list[Finding],
) -> dict[str, Any]:
    texts: dict[str, str] = {}

    for path in iter_files(root):
        texts[rel(path, root)] = read_text(path).lower()

    combined = "\n".join(texts.values())

    component_hits: dict[str, list[str]] = {}

    for component, keywords in ARCHITECTURE_TERMS.items():
        hits = [
            keyword
            for keyword in keywords
            if keyword.lower() in combined
        ]
        component_hits[component] = hits

        if not hits:
            severity = "HIGH" if component in {
                "detection",
                "video",
                "events",
            } else "MEDIUM"

            add(
                findings,
                severity,
                "architecture",
                f"No clear implementation evidence for {component}",
                "Expected architecture terminology was not detected in the "
                "AI-engine source/configuration.",
                recommendation=(
                    "Inspect manually. If this capability is intentionally "
                    "outside the AI-engine, document the boundary explicitly."
                ),
            )

    ai_libraries = {}

    for keyword, description in AI_KEYWORDS.items():
        matching_files = [
            filename
            for filename, text in texts.items()
            if keyword.lower() in text
        ]

        if matching_files:
            ai_libraries[description] = matching_files[:20]

    return {
        "component_keyword_hits": component_hits,
        "detected_ai_libraries": ai_libraries,
    }


# ---------------------------------------------------------------------------
# Placeholder audit
# ---------------------------------------------------------------------------

def audit_placeholders(
    root: Path,
    findings: list[Finding],
) -> dict[str, Any]:
    matches = []

    for path in iter_python(root):
        text = read_text(path)

        for pattern, label in PLACEHOLDER_PATTERNS:
            for match in re.finditer(pattern, text, flags=re.IGNORECASE):
                line = line_number(text, match.start())

                matches.append(
                    {
                        "file": rel(path, root),
                        "line": line,
                        "type": label,
                        "text": match.group(0).strip(),
                    }
                )

                severity = "MEDIUM"

                if label in {
                    "NotImplementedError",
                    "pass statement",
                }:
                    severity = "HIGH"

                add(
                    findings,
                    severity,
                    "implementation",
                    label,
                    f"Potential unfinished implementation: {match.group(0).strip()}",
                    path,
                    root,
                    line,
                    "Determine whether this is intentional. If production "
                    "functionality is incomplete, implement it or explicitly "
                    "document the boundary.",
                )

    return {"matches": matches}


# ---------------------------------------------------------------------------
# Security audit
# ---------------------------------------------------------------------------

def audit_security(
    root: Path,
    findings: list[Finding],
) -> dict[str, Any]:
    matches = []

    for path in iter_files(root):
        text = read_text(path)

        if path.name.startswith(".env"):
            add(
                findings,
                "HIGH",
                "security",
                "Environment file present inside AI-engine",
                "A .env-style file exists inside the audited tree.",
                path,
                root,
                recommendation=(
                    "Ensure real secrets are not committed. Prefer environment "
                    "injection or a secret manager."
                ),
            )

        for pattern, label in SECURITY_PATTERNS:
            for match in re.finditer(
                pattern,
                text,
                flags=re.IGNORECASE,
            ):
                line = line_number(text, match.start())

                matches.append(
                    {
                        "file": rel(path, root),
                        "line": line,
                        "type": label,
                    }
                )

                add(
                    findings,
                    "CRITICAL",
                    "security",
                    label,
                    "A value resembling a hard-coded credential/key was found.",
                    path,
                    root,
                    line,
                    "Move secrets to environment/secret management and rotate "
                    "the exposed value if it is real.",
                )

    return {"matches": matches}


# ---------------------------------------------------------------------------
# Model / inference audit
# ---------------------------------------------------------------------------

def audit_models(
    root: Path,
    findings: list[Finding],
) -> dict[str, Any]:
    model_files = []
    model_references = []

    model_extensions = {
        ".pt",
        ".pth",
        ".onnx",
        ".engine",
        ".tflite",
        ".pb",
        ".weights",
        ".bin",
        ".safetensors",
    }

    for path in root.rglob("*"):
        if not path.is_file():
            continue

        if any(part in IGNORE_DIRS for part in path.parts):
            continue

        if path.suffix.lower() in model_extensions:
            model_files.append(rel(path, root))

    patterns = [
        r"YOLO\s*\(",
        r"YOLO\s*\.",
        r"load_model\s*\(",
        r"torch\.load\s*\(",
        r"from_pretrained\s*\(",
        r"cv2\.dnn",
        r"DeepFace",
        r"easyocr\.Reader",
        r"paddleocr",
    ]

    for path in iter_python(root):
        text = read_text(path)

        for pattern in patterns:
            for match in re.finditer(pattern, text, flags=re.IGNORECASE):
                model_references.append(
                    {
                        "file": rel(path, root),
                        "line": line_number(text, match.start()),
                        "pattern": pattern,
                    }
                )

    if not model_references:
        add(
            findings,
            "HIGH",
            "models",
            "No obvious model-loading/inference implementation found",
            "The audit could not identify common AI model loading or inference "
            "patterns.",
            recommendation=(
                "Confirm whether inference is delegated to another service. "
                "If so, document that boundary."
            ),
        )

    return {
        "model_files": model_files,
        "model_references": model_references,
    }


# ---------------------------------------------------------------------------
# Evidence boundary audit
# ---------------------------------------------------------------------------

def audit_evidence_boundary(
    root: Path,
    findings: list[Finding],
) -> dict[str, Any]:
    evidence_terms = [
        "evidence",
        "artifact",
        "clip",
        "keyframe",
        "snapshot",
        "sha256",
        "hash",
        "incident",
        "ingestion",
        "detection_event",
    ]

    hits = Counter()

    for path in iter_files(root):
        text = read_text(path).lower()

        for term in evidence_terms:
            if term in text:
                hits[term] += 1

    direct_crypto = any(
        term in hits
        for term in ["sha256", "hash"]
    )

    if direct_crypto:
        add(
            findings,
            "INFO",
            "boundary",
            "AI-engine contains evidence/hash terminology",
            "This is not automatically a defect, but it requires checking that "
            "the AI layer is not taking ownership of backend evidence security.",
            recommendation=(
                "AI should provide evidence bytes and trusted metadata; the "
                "backend Evidence Service should remain authoritative for "
                "hashing, encryption, storage, custody and audit."
            ),
        )

    return {"keyword_hits": dict(hits)}


# ---------------------------------------------------------------------------
# Network/API audit
# ---------------------------------------------------------------------------

def audit_api_boundary(
    root: Path,
    findings: list[Finding],
) -> dict[str, Any]:
    patterns = {
        "httpx": r"\bhttpx\b",
        "requests": r"\brequests\b",
        "aiohttp": r"\baiohttp\b",
        "fastapi": r"\bfastapi\b",
        "grpc": r"\bgrpc\b",
        "websocket": r"\bwebsocket\b",
    }

    hits = Counter()

    for path in iter_files(root):
        text = read_text(path).lower()

        for label, pattern in patterns.items():
            if re.search(pattern, text):
                hits[label] += 1

    network_calls = []

    call_patterns = [
        r"\.post\s*\(",
        r"\.get\s*\(",
        r"\.put\s*\(",
        r"\.delete\s*\(",
        r"client\.request\s*\(",
    ]

    for path in iter_python(root):
        text = read_text(path)

        for pattern in call_patterns:
            for match in re.finditer(pattern, text):
                network_calls.append(
                    {
                        "file": rel(path, root),
                        "line": line_number(text, match.start()),
                        "pattern": pattern,
                    }
                )

    if network_calls:
        add(
            findings,
            "INFO",
            "integration",
            "Outbound API/network calls detected",
            "The AI-engine communicates with external/backend services.",
            recommendation=(
                "Verify authentication, TLS, timeouts, retries, idempotency, "
                "correlation IDs, and error handling against the backend contract."
            ),
        )

    return {
        "libraries": dict(hits),
        "network_calls": network_calls,
    }


# ---------------------------------------------------------------------------
# Concurrency / resource audit
# ---------------------------------------------------------------------------

def audit_concurrency(
    root: Path,
    findings: list[Finding],
) -> dict[str, Any]:
    patterns = {
        "threading": r"\bthreading\b",
        "multiprocessing": r"\bmultiprocessing\b",
        "asyncio": r"\basyncio\b",
        "queue": r"\bqueue\b",
        "ThreadPoolExecutor": r"\bThreadPoolExecutor\b",
        "ProcessPoolExecutor": r"\bProcessPoolExecutor\b",
        "Lock": r"\bLock\s*\(",
        "Semaphore": r"\bSemaphore\s*\(",
    }

    hits = Counter()

    for path in iter_python(root):
        text = read_text(path)

        for label, pattern in patterns.items():
            if re.search(pattern, text):
                hits[label] += 1

    infinite_loops = []

    for path in iter_python(root):
        text = read_text(path)

        for match in re.finditer(r"\bwhile\s+True\s*:", text):
            infinite_loops.append(
                {
                    "file": rel(path, root),
                    "line": line_number(text, match.start()),
                }
            )

    if infinite_loops:
        add(
            findings,
            "MEDIUM",
            "concurrency",
            "Continuous worker loop detected",
            "A while True loop exists. This may be intentional for streaming "
            "but requires shutdown/backpressure/error handling review.",
            recommendation=(
                "Verify cancellation, graceful shutdown, exception isolation, "
                "frame backpressure and resource cleanup."
            ),
        )

    return {
        "concurrency_constructs": dict(hits),
        "continuous_loops": infinite_loops,
    }


# ---------------------------------------------------------------------------
# Logging audit
# ---------------------------------------------------------------------------

def audit_logging(
    root: Path,
    findings: list[Finding],
) -> dict[str, Any]:
    logging_hits = Counter()

    for path in iter_python(root):
        text = read_text(path)

        for term in [
            "logging",
            "logger",
            "structlog",
            "loguru",
            "print(",
        ]:
            if term.lower() in text.lower():
                logging_hits[term] += 1

    if not any(
        key in logging_hits
        for key in ["logging", "logger", "structlog", "loguru"]
    ):
        add(
            findings,
            "MEDIUM",
            "observability",
            "No obvious structured logging implementation",
            "The AI-engine does not appear to use a conventional logging "
            "framework.",
            recommendation=(
                "Use structured logging with camera ID, event ID, model "
                "version, correlation ID and processing latency where appropriate."
            ),
        )

    if "print(" in logging_hits:
        add(
            findings,
            "LOW",
            "observability",
            "print() usage detected",
            "Direct console output was found.",
            recommendation=(
                "Prefer the project's logging framework for production "
                "observability."
            ),
        )

    return {"logging_hits": dict(logging_hits)}


# ---------------------------------------------------------------------------
# Test audit
# ---------------------------------------------------------------------------

def audit_tests(
    root: Path,
    findings: list[Finding],
) -> dict[str, Any]:
    test_files = []

    for path in root.rglob("*"):
        if not path.is_file():
            continue

        if any(part in IGNORE_DIRS for part in path.parts):
            continue

        name = path.name.lower()

        if (
            name.startswith("test_")
            or name.endswith("_test.py")
            or "tests" in {p.lower() for p in path.parts}
        ):
            test_files.append(rel(path, root))

    if not test_files:
        add(
            findings,
            "HIGH",
            "testing",
            "No obvious AI-engine tests found",
            "No pytest-style test files or tests directory were detected.",
            recommendation=(
                "Add unit tests for detection, classification, OCR, face "
                "recognition, event contracts, failure handling and integration."
            ),
        )

    return {
        "test_file_count": len(test_files),
        "test_files": test_files,
    }


# ---------------------------------------------------------------------------
# Dependency/configuration audit
# ---------------------------------------------------------------------------

def audit_dependencies(
    root: Path,
    findings: list[Finding],
) -> dict[str, Any]:
    dependency_files = []

    for name in [
        "requirements.txt",
        "requirements-dev.txt",
        "pyproject.toml",
        "poetry.lock",
        "uv.lock",
        "Pipfile",
        "Pipfile.lock",
        "environment.yml",
        "environment.yaml",
    ]:
        path = root / name

        if path.exists():
            dependency_files.append(name)

    if not dependency_files:
        add(
            findings,
            "HIGH",
            "dependencies",
            "No obvious Python dependency manifest",
            "No standard dependency file was found at the AI-engine root.",
            recommendation=(
                "Ensure the AI-engine has reproducible dependency management."
            ),
        )

    return {"dependency_files": dependency_files}


# ---------------------------------------------------------------------------
# Static tool audit
# ---------------------------------------------------------------------------

def audit_tools(
    root: Path,
    findings: list[Finding],
    run_tools: bool,
) -> dict[str, Any]:
    if not run_tools:
        return {
            "skipped": True,
            "reason": "--no-tools specified",
        }

    results = {}

    commands = [
        ("ruff", [sys.executable, "-m", "ruff", "check", "."]),
        (
            "mypy",
            [
                sys.executable,
                "-m",
                "mypy",
                ".",
            ],
        ),
        (
            "pytest",
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
            ],
        ),
    ]

    for name, command in commands:
        result = run_command(command, root)
        results[name] = result

        if result["returncode"] is None:
            add(
                findings,
                "MEDIUM",
                "tooling",
                f"{name} could not be executed",
                result["stderr"],
                recommendation=(
                    f"Install/configure {name} in the AI-engine environment "
                    "and rerun the audit."
                ),
            )

        elif result["returncode"] != 0:
            severity = "HIGH" if name == "pytest" else "MEDIUM"

            add(
                findings,
                severity,
                "tooling",
                f"{name} failed",
                f"{name} returned exit code {result['returncode']}.",
                recommendation=(
                    f"Review the {name} output in the generated audit report "
                    "and fix failures before declaring the AI-engine green."
                ),
            )

    return {
        "skipped": False,
        "results": results,
    }


# ---------------------------------------------------------------------------
# README / documentation audit
# ---------------------------------------------------------------------------

def audit_documentation(
    root: Path,
    findings: list[Finding],
) -> dict[str, Any]:
    docs = []

    for path in root.rglob("*"):
        if not path.is_file():
            continue

        if any(part in IGNORE_DIRS for part in path.parts):
            continue

        if path.suffix.lower() in {".md", ".rst"}:
            docs.append(rel(path, root))

    if not docs:
        add(
            findings,
            "MEDIUM",
            "documentation",
            "No AI-engine documentation found",
            "No Markdown/reStructuredText documentation was detected.",
            recommendation=(
                "Document model versions, inputs/outputs, configuration, "
                "deployment, camera integration and backend contracts."
            ),
        )

    return {"documentation_files": docs}


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

def calculate_summary(
    findings: list[Finding],
) -> dict[str, Any]:
    counts = Counter(f.severity for f in findings)

    if counts["CRITICAL"]:
        status = "CRITICAL"
    elif counts["HIGH"]:
        status = "FAIL"
    elif counts["MEDIUM"]:
        status = "CONDITIONAL"
    elif counts["LOW"]:
        status = "PASS_WITH_NOTES"
    else:
        status = "PASS"

    return {
        "status": status,
        "total_findings": len(findings),
        "critical": counts["CRITICAL"],
        "high": counts["HIGH"],
        "medium": counts["MEDIUM"],
        "low": counts["LOW"],
        "info": counts["INFO"],
    }


# ---------------------------------------------------------------------------
# Human-readable report
# ---------------------------------------------------------------------------

def print_report(report: AuditReport) -> None:
    print()
    print("=" * 78)
    print("SECURE SURVEILLANCE PLATFORM — AI ENGINE AUDIT")
    print("=" * 78)

    print(f"Root: {report.root}")
    print()

    summary = report.summary

    print("STATUS")
    print("-" * 78)
    print(f"Overall:    {summary['status']}")
    print(f"Findings:   {summary['total_findings']}")
    print(f"Critical:   {summary['critical']}")
    print(f"High:       {summary['high']}")
    print(f"Medium:     {summary['medium']}")
    print(f"Low:        {summary['low']}")
    print(f"Info:       {summary['info']}")

    print()
    print("INVENTORY")
    print("-" * 78)

    inventory = report.inventory

    print(f"Files:              {inventory['file_count']}")
    print(f"Python files:       {inventory['python_file_count']}")
    print(f"Approx Python LOC:  {inventory['python_lines_approx']}")

    print()
    print("ARCHITECTURE SIGNALS")
    print("-" * 78)

    components = report.architecture["component_keyword_hits"]

    for component, hits in components.items():
        status = "FOUND" if hits else "NOT CLEAR"
        print(
            f"{component:20} {status:10} "
            f"{', '.join(hits) if hits else '-'}"
        )

    print()
    print("DETECTED AI TECHNOLOGIES")
    print("-" * 78)

    libraries = report.architecture["detected_ai_libraries"]

    if libraries:
        for library, files in libraries.items():
            print(f"{library}:")
            for filename in files[:5]:
                print(f"  - {filename}")
    else:
        print("No obvious AI libraries detected.")

    print()
    print("FINDINGS")
    print("-" * 78)

    if not report.findings:
        print("No findings.")
    else:
        severity_order = {
            "CRITICAL": 0,
            "HIGH": 1,
            "MEDIUM": 2,
            "LOW": 3,
            "INFO": 4,
        }

        ordered = sorted(
            report.findings,
            key=lambda f: (
                severity_order.get(f.severity, 99),
                f.category,
                f.title,
            ),
        )

        for index, finding in enumerate(ordered, start=1):
            location = ""

            if finding.file:
                location = finding.file

                if finding.line:
                    location += f":{finding.line}"

            print()
            print(
                f"[{finding.severity}] "
                f"{index}. {finding.title}"
            )

            print(f"    Category: {finding.category}")

            if location:
                print(f"    Location: {location}")

            print(f"    Detail:   {finding.detail}")

            if finding.recommendation:
                print(
                    f"    Action:   {finding.recommendation}"
                )

    print()
    print("=" * 78)
    print("AUDIT COMPLETE")
    print("=" * 78)
    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Read-only audit of the surveillance AI-engine."
    )

    parser.add_argument(
        "--root",
        type=Path,
        default=DEFAULT_ROOT,
        help="AI-engine directory to audit.",
    )

    parser.add_argument(
        "--json",
        type=Path,
        default=None,
        help="Optional JSON output path.",
    )

    parser.add_argument(
        "--no-tools",
        action="store_true",
        help="Skip Ruff, MyPy and pytest execution.",
    )

    args = parser.parse_args()

    root = args.root.resolve()

    if not root.exists():
        print(
            f"ERROR: AI-engine directory does not exist: {root}",
            file=sys.stderr,
        )
        return 2

    if not root.is_dir():
        print(
            f"ERROR: AI-engine root is not a directory: {root}",
            file=sys.stderr,
        )
        return 2

    findings: list[Finding] = []

    inventory = audit_inventory(root, findings)

    ast_info = audit_python_ast(root, findings)

    architecture = audit_architecture(root, findings)

    placeholders = audit_placeholders(root, findings)

    security = audit_security(root, findings)

    models = audit_models(root, findings)

    evidence = audit_evidence_boundary(root, findings)

    api = audit_api_boundary(root, findings)

    concurrency = audit_concurrency(root, findings)

    logging_info = audit_logging(root, findings)

    tests = audit_tests(root, findings)

    dependencies = audit_dependencies(root, findings)

    documentation = audit_documentation(root, findings)

    tools = audit_tools(
        root,
        findings,
        run_tools=not args.no_tools,
    )

    summary = calculate_summary(findings)

    report = AuditReport(
        root=str(root),
        summary=summary,
        findings=findings,
        inventory={
            **inventory,
            "ast": ast_info,
        },
        architecture=architecture,
        tools=tools,
    )

    # Keep these available in JSON without cluttering the main dataclass.
    report_dict = asdict(report)

    report_dict["implementation"] = placeholders
    report_dict["security"] = security
    report_dict["models"] = models
    report_dict["evidence_boundary"] = evidence
    report_dict["api_boundary"] = api
    report_dict["concurrency"] = concurrency
    report_dict["logging"] = logging_info
    report_dict["tests"] = tests
    report_dict["dependencies"] = dependencies
    report_dict["documentation"] = documentation

    print_report(report)

    if args.json:
        args.json.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        args.json.write_text(
            json.dumps(
                report_dict,
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        print(f"JSON report written to: {args.json}")

    # Exit non-zero for CRITICAL/HIGH findings.
    if summary["critical"] > 0:
        return 2

    if summary["high"] > 0:
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())