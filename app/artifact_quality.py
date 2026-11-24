"""Deterministic, read-only quality checks for submitted DAEP artifacts."""
import re
from urllib.parse import urlparse

_SHA_RE = re.compile(r"^(?:[0-9a-fA-F]{7,40})$")
_REPORT_TYPES = {"test_report", "test_result", "test_results"}


def assess_artifact_quality(artifact_type, uri, commit_sha=None, metadata=None, policy=None):
    kind = str(artifact_type or "").strip().lower().replace("-", "_")
    metadata = metadata if isinstance(metadata, dict) else {}
    policy = policy if isinstance(policy, dict) else {}
    checks = []

    parsed = urlparse(str(uri or "").strip())
    uri_ok = parsed.scheme in ("https", "http", "git", "ssh") and bool(parsed.netloc or parsed.scheme in ("git", "ssh"))
    checks.append({"key": "uri", "status": "PASS" if uri_ok else "FAIL",
                   "message": "交付地址格式有效" if uri_ok else "交付地址必须是有效的 HTTP(S)、Git 或 SSH URI"})

    if kind in ("git_commit", "commit", "source_commit") or policy.get("require_commit_sha"):
        valid = bool(_SHA_RE.fullmatch(str(commit_sha or "").strip()))
        checks.append({"key": "commit_sha", "status": "PASS" if valid else "FAIL",
                       "message": "Commit SHA 格式有效" if valid else "Git Commit 类型或项目策略要求提供 7-40 位十六进制 Commit SHA"})

    summary = metadata.get("test_summary") if isinstance(metadata.get("test_summary"), dict) else metadata
    values = [summary.get(k) for k in ("total", "passed", "failed")]
    valid_numbers = all(isinstance(v, int) and not isinstance(v, bool) and v >= 0 for v in values)
    valid_counts = valid_numbers and values[0] > 0 and values[1] + values[2] == values[0]
    if kind in _REPORT_TYPES:
        checks.append({"key": "test_summary", "status": "PASS" if valid_counts else "FAIL",
                       "message": "测试汇总数据完整且数量一致" if valid_counts else "测试报告必须包含 total、passed、failed 非负整数，total 大于 0 且 passed + failed = total"})
        if valid_counts:
            checks.append({"key": "test_result", "status": "PASS" if values[2] == 0 else "WARN",
                           "message": "没有失败用例" if values[2] == 0 else f"存在 {values[2]} 个失败用例，需要审核人员确认"})

    coverage = metadata.get("coverage_percent")
    if coverage is not None:
        valid_coverage = isinstance(coverage, (int, float)) and not isinstance(coverage, bool) and 0 <= coverage <= 100
        checks.append({"key": "coverage_percent", "status": "PASS" if valid_coverage else "FAIL",
                       "message": "覆盖率数值有效" if valid_coverage else "coverage_percent 必须是 0 到 100 之间的数字"})

    minimum = policy.get("min_coverage_percent")
    if minimum is not None and kind in _REPORT_TYPES:
        valid_minimum = isinstance(coverage, (int, float)) and not isinstance(coverage, bool) and 0 <= coverage <= 100
        passed = valid_minimum and coverage >= minimum
        checks.append({"key": "policy_min_coverage", "status": "PASS" if passed else "FAIL",
                       "message": f"覆盖率达到项目要求（{minimum}%）" if passed else f"项目要求覆盖率至少为 {minimum}%"})

    maximum_failed = policy.get("max_failed_tests")
    if maximum_failed is not None and kind in _REPORT_TYPES:
        passed = valid_counts and values[2] <= maximum_failed
        checks.append({"key": "policy_max_failed_tests", "status": "PASS" if passed else "FAIL",
                       "message": f"失败用例数未超过项目上限（{maximum_failed}）" if passed else f"失败用例数超过项目上限（{maximum_failed}）或测试汇总缺失"})

    failed = sum(1 for x in checks if x["status"] == "FAIL")
    warnings = sum(1 for x in checks if x["status"] == "WARN")
    score = round(100 * (len(checks) - failed) / len(checks)) if checks else 100
    return {"status": "FAIL" if failed else ("NEEDS_REVIEW" if warnings else "PASS"),
            "score": score, "failed_checks": failed, "warnings": warnings, "checks": checks}
