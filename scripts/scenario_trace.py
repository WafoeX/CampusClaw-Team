"""核对已实现能力的场景、测试入口及真实依赖断言。"""

import ast
import json
import re
from pathlib import Path

SCENARIO = re.compile(r"^#### Scenario: ([A-Z][A-Z0-9]*-[NFB][0-9]+)(?:[ \t]|$)", re.M)


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"重复声明 {key}")
        result[key] = value
    return result


def local_file(root, name):
    path = root / name
    if (
        not isinstance(name, str)
        or Path(name).is_absolute()
        or ".." in Path(name).parts
        or not path.resolve().is_relative_to(root.resolve())
        or not path.is_file()
    ):
        raise ValueError(f"无效文件 {name}")
    return path


def resolve_spec(root, name):
    location = root / "openspec" / "changes"
    path = location / name
    if path.is_file():
        return local_file(root, str(path.relative_to(root)))
    change, *tail = Path(name).parts
    archive = location / "archive"
    matches = [
        candidate.joinpath(*tail)
        for candidate in [archive / change, *archive.glob(f"*-{change}")]
        if candidate.joinpath(*tail).is_file()
    ]
    if len(matches) != 1:
        raise ValueError(f"找不到唯一规格 {name}")
    return local_file(root, str(matches[0].relative_to(root)))


def validate_entry(root, entry):
    if not isinstance(entry, dict):
        raise ValueError("映射必须是对象")
    if "pending" in entry:
        task_file = local_file(root, entry["task_file"])
        if not entry.get("reason") or not re.search(
            rf"^- \[ \] {re.escape(entry['pending'])} ", task_file.read_text(), re.M
        ):
            raise ValueError("待验证场景必须绑定未完成任务和理由")
        return
    path = local_file(root, entry["test"])
    if (
        not path.name.startswith("test_")
        or path.suffix != ".py"
        or not path.is_relative_to(root / "tests")
    ):
        raise ValueError(f"未登记 pytest 文件 {path}")
    tree = ast.parse(path.read_text())
    functions = {
        node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)
    }
    function = functions.get(entry["function"])
    if function is None or not function.name.startswith("test_"):
        raise ValueError(f"缺少 pytest 函数 {entry['function']}")
    if not any(
        isinstance(node, ast.Assert)
        or (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "pytest"
            and node.func.attr == "raises"
        )
        for node in ast.walk(function)
    ):
        raise ValueError(f"测试没有实际断言 {function.name}")
    if "script" not in entry:
        return
    script = local_file(root, entry["script"])
    runner = functions.get(entry["runner"])
    if runner is None or not any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == runner.name
        for node in ast.walk(function)
    ):
        raise ValueError(f"测试未调用脚本入口 {entry['runner']}")
    executions = [
        node
        for node in ast.walk(runner)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "compose"
    ]
    expected_read = f'Path(__file__).with_name("{script.name}").read_text()'
    expected_ast = ast.dump(ast.parse(expected_read, mode="eval").body)
    if not any(
        [ast.literal_eval(arg) for arg in call.args[:5]]
        == ["exec", "-T", "app", "python", "-c"]
        and any(ast.dump(arg) == expected_ast for arg in call.args[5:])
        and script.parent == path.parent
        for call in executions
    ):
        raise ValueError(f"脚本未由 Compose 入口执行 {script}")
    assertion = ast.parse(entry["assertion"]).body
    if len(assertion) != 1 or not isinstance(assertion[0], ast.Assert):
        raise ValueError("脚本证据必须是 assert")
    # 只接受模块执行路径上的断言，函数内未调用的断言不能充当脚本证据。
    nodes = list(ast.parse(script.read_text()).body)
    assertions = []
    while nodes:
        node = nodes.pop()
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        if isinstance(node, ast.Assert):
            assertions.append(ast.dump(node))
        nodes.extend(ast.iter_child_nodes(node))
    if assertions.count(ast.dump(assertion[0])) != 1:
        raise ValueError(f"缺少脚本断言或断言不唯一 {script}: {entry['assertion']}")


def check_traceability(root):
    errors = []
    try:
        manifest = json.loads(
            local_file(root, "tests/scenario-map.json").read_text(),
            object_pairs_hook=unique_object,
        )
        if (
            set(manifest) != {"version", "implemented", "planned"}
            or manifest["version"] != 1
            or not isinstance(manifest["implemented"], dict)
            or not isinstance(manifest["planned"], dict)
        ):
            raise ValueError("非法场景清单结构")
        implemented = manifest["implemented"]
        planned = manifest["planned"]
        if not implemented or implemented.keys() & planned.keys():
            raise ValueError("实现状态为空或重复")
        declared = implemented.keys() | planned.keys()
        location = root / "openspec" / "changes"
        active = {
            str(path.relative_to(location))
            for path in location.glob("*/specs/*/spec.md")
        }
        for missing in sorted(active - declared):
            errors.append(f"规格未声明实现状态 {missing}")
        for name, reason in planned.items():
            resolve_spec(root, name)
            if not isinstance(reason, str) or not reason.strip():
                raise ValueError(f"规划能力缺少理由 {name}")
            change = resolve_spec(root, name).parents[2]
            if not (change / "tasks.md").is_file():
                raise ValueError(f"规划能力缺少任务 {name}")
        for name, entries in implemented.items():
            spec = resolve_spec(root, name)
            text = spec.read_text()
            identifiers = SCENARIO.findall(text)
            headings = re.findall(r"^#### Scenario: .+$", text, re.M)
            if len(headings) != len(identifiers) or len(identifiers) != len(
                set(identifiers)
            ):
                raise ValueError(f"场景编号非法或重复 {name}")
            expected = set(identifiers)
            if not expected or not isinstance(entries, dict):
                raise ValueError(f"非法场景集合 {name}")
            errors.extend(
                f"缺少场景映射 {name} {key}"
                for key in sorted(expected - entries.keys())
            )
            errors.extend(
                f"多余场景映射 {name} {key}"
                for key in sorted(entries.keys() - expected)
            )
            for key, entry in entries.items():
                try:
                    validate_entry(root, entry)
                except (KeyError, TypeError, ValueError, SyntaxError, OSError) as error:
                    errors.append(f"无效场景映射 {key}: {error}")
    except (KeyError, TypeError, ValueError, SyntaxError, OSError) as error:
        errors.append(f"场景清单错误: {error}")
    return errors


if __name__ == "__main__":
    failures = check_traceability(Path(__file__).resolve().parents[1])
    if failures:
        raise SystemExit("\n".join(failures))
    print("已实现能力的场景及执行入口映射通过")
