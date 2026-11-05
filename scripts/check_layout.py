"""Validate application layer imports and runtime/authorization scenario coverage."""

import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHANGE = "2026-11-04-add-skeleton"
CHANGE_ROOT = ROOT / "openspec" / "changes"
LAYERS = {
    "api": {"api", "services", "observability"},
    "services": {"services"},
    "adapters": {"adapters", "config"},
}
API_DEPENDENCIES = {"flask", "werkzeug"}
ADAPTER_DEPENDENCIES = {"pymysql", "sqlalchemy"}


def check_layers():
    errors = []
    for layer, allowed in LAYERS.items():
        for path in (ROOT / "app" / layer).rglob("*.py"):
            for node in ast.walk(ast.parse(path.read_text())):
                if isinstance(node, ast.Import):
                    modules = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    if node.level:
                        errors.append(f"{path}:{node.lineno} 分层导入使用绝对路径")
                        continue
                    modules = (
                        [f"app.{alias.name}" for alias in node.names]
                        if node.module == "app"
                        else [node.module or ""]
                    )
                else:
                    continue
                for module in modules:
                    root, _, tail = module.partition(".")
                    if root == "app":
                        permitted = tail.split(".")[0] in allowed
                    else:
                        permitted = (
                            root in sys.stdlib_module_names
                            or (layer == "api" and root in API_DEPENDENCIES)
                            or (layer == "adapters" and root in ADAPTER_DEPENDENCIES)
                        )
                    if not permitted:
                        errors.append(f"{path}:{node.lineno} {layer} 导入了 {module}")
    return errors


def check_scenarios():
    change = CHANGE_ROOT / CHANGE
    if not change.is_dir():
        archive = CHANGE_ROOT / "archive"
        matches = [
            path
            for path in [archive / CHANGE, *archive.glob(f"*-{CHANGE}")]
            if path.is_dir()
        ]
        if len(matches) != 1:
            return ["找不到唯一骨架规约"]
        change = matches[0]
    expected = set()
    for capability in ("skeleton-runtime", "skeleton-access"):
        path = change / "specs" / capability / "spec.md"
        if not path.is_file():
            return [f"缺少规约 {path}"]
        ids = re.findall(
            r"^#### Scenario: ([A-Z]{2}-[NFB]\d{2}) ", path.read_text(), re.M
        )
        if not ids:
            return [f"没有场景 {path}"]
        expected.update(ids)
    actual = set()
    for path in (ROOT / "tests").rglob("test_*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
                actual.update(re.findall(r"[A-Z]{2}_[NFB]\d{2}", node.name))
    return [
        f"缺少用例 {scenario}"
        for scenario in sorted(expected)
        if scenario.replace("-", "_") not in actual
    ]


if __name__ == "__main__":
    failures = check_layers() + check_scenarios()
    if failures:
        raise SystemExit("\n".join(failures))
    print("分层及运行/授权场景映射通过")
