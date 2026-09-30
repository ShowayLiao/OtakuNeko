# A-L0-04｜关键边界类型检查

## 范围与结果

在 `feature-harness` 的普通检出、基准提交 `2cdfb92308a044fd97907ccaa8f207f69f8b893e` 上执行。本任务没有活动 Harness Batch，不创建 Batch execution record。

`backend/pyproject.toml` 的 Mypy 范围从 `app/harness`、`app/capabilities`、`app/memory`、`app/trace` 扩到整个 `app/api` 和 `app/evaluation`。`.github/workflows/ci.yml` 的 `backend-quality-baseline` job 继续以 `uv run --locked mypy` 阻断；CI 的业务层 `TID251` 检查继续定位直接导入 Provider/框架对象的代码。API 入口和评测适配器可以直接使用 Provider SDK，业务层导入限制仍只作用于 `app/services`、`app/models`、`app/repositories`、`app/schemas`。

首次扩围命令 `uv run --locked --offline --directory backend mypy --no-pretty app/api app/harness app/capabilities app/evaluation` 退出 1：检查 68 个源文件，在 9 个文件中定位 30 条错误。原始错误行保存在 [`A-L0-04-initial-mypy-failures.txt`](A-L0-04-initial-mypy-failures.txt)。典型错误包括 `app/evaluation/adapter.py:195` 的状态类型、`app/api/v1/agent.py:501` 的可空密钥、`app/api/v1/collections.py:315` 的请求与服务参数类型，以及 `app/repositories/user_repo.py:127` 查询不存在的 `User.email` 字段。这些失败发生在修改前，不作为通过结果。

修复后 `uv run --locked --offline --directory backend mypy --no-pretty` 退出 0，检查 **85 个源文件、0 条错误**；相对原有 60 个文件的门禁增加 25 个文件。API 的 SQLModel 查询使用 `col(...)`，Collection 批量服务参数类型与实际兼容的两种请求模型一致，评测状态采用契约中的 Literal。未更改数据库结构、Provider 网络策略或对外响应模型。

## 验证与失败定位

以下命令在仓库根目录执行；本地使用仓库内的 `.uv-cache`、`--locked --offline` 和 `DEBUG=false`。`DEBUG=false` 是本地环境修正：继承的 `DEBUG=release` 不符合 Settings 的布尔字段，第一次子集测试因此未进入测试收集；修正后再运行的结果如下。

| 命令 | 退出码 | 结果 |
| --- | ---: | --- |
| `uv run --locked --offline --directory backend mypy --no-pretty` | 0 | 85 个源文件无错误 |
| `uv lock --check --offline --directory backend` | 0 | 锁文件一致，解析 105 个包 |
| `uv run --locked --offline --directory backend ruff check app tests` | 0 | 全后端 lint 通过 |
| `uv run --locked --offline --directory backend ruff format --check app/harness app/capabilities app/memory app/trace tests/harness tests/capabilities tests/memory tests/trace` | 0 | 既有阻断范围 114 个文件已格式化 |
| `uv run --locked --offline --directory backend ruff check --select TID251 app/services app/models app/repositories app/schemas` | 0 | 业务层直接导入边界通过 |
| `uv run --locked --offline --directory backend deptry . --no-ansi` | 0 | 扫描 174 个文件，0 个依赖问题 |
| `uv run --locked --offline --directory backend pytest -q` | 0 | 798 passed、1 skipped、306 warnings |
| `uv run --locked --offline --directory backend python -m app.evaluation.runner --config evals/config/fast.yaml` | 0 | 9/9 case 通过，0 失败 |

失败探针没有修改生产文件。把 `from openai import AsyncOpenAI` 经标准输入传给 `ruff check --select TID251 --stdin-filename app/services/_provider_probe.py -`，退出 1，并定位到 `app/services/_provider_probe.py:1:1` 的 `TID251`。把 `AsyncOpenAI` 赋给 `ModelCallResult` 的一次性 Mypy `-c` 探针退出 1，定位 `<string>:1` 的 `[assignment]`。这证明直接 Provider 导入和明确的错误类型赋值会失败；经 `Any` 间接传播的对象不由这两个静态检查完整证明。

快速评测报告位于 `backend/.runtime/evaluation/fast.json`：`pass_rate=1.0`、`routing_accuracy=1.0`、`safety_pass_rate=1.0`、平均 `latency_ms=9.56`；`baseline_failures=[]`。报告是本地生成文件，不作为远端 CI Run。Pytest 警告主要是既有 Pydantic class config、SQLModel `session.execute()` 弃用提示，以及本机 `.pytest_cache` 写入警告；1 个跳过项为既有测试跳过。

## 已知限制、结论和下一步

`UserRepo.get_by_email` 查询不存在的 `User.email` 字段，运行时会抛出 `AttributeError`，仓库内也没有调用点。已移除这个不可执行的历史仓库方法及其精确 `attr-defined` 忽略。若以后需要邮箱查找，应先定义用户邮箱字段、迁移、唯一性和相关测试，再新增查询能力。`jose`、`passlib` 和 `yaml` 缺少锁定的类型桩，对各自导入使用精确 `import-untyped` 忽略；若后续加入类型桩，应移除这些忽略并复测。

按 `docs/code-review.md` 审查完整未提交 diff 和本报告，类型门禁改动未新增 blocker、critical、high 或未处理 medium Finding；此前的 2 轮 Review 已移除无效邮箱查询。追加审查发现既有的共享 Subject 写接口缺少资源级授权：删除入口传入 `user_id`，但服务和仓库删除路径未使用该身份；更新入口也允许登录用户修改共享条目。按审查标准，整体 verdict 为 **changes_required**。用户于 2026-09-29 指示暂缓此问题，并已登记滴答清单待办 `A-L7-08｜完善共享条目的写入权限`，同时允许本次类型门禁改动在没有其他问题时提交。本次提交不代表该权限风险已解决。`git diff --check` 退出 0；CI YAML 能解析为 `software`、`backend-quality-baseline`、`harness`、`benchmark` 四个 job。

后续修复复现：`python -c 'from app.models.user import User; print(User.email)'` 退出 1，异常为 `AttributeError: email`；全仓生产代码和测试没有 `get_by_email` 调用点。删除该方法后，`mypy --no-pretty` 退出 0（85 个源文件）、`ruff check app tests` 退出 0、`pytest -q --disable-warnings` 退出 0（798 passed、1 skipped、306 warnings）；`rg -n 'get_by_email|User\.email' backend/app backend/tests` 无匹配。以上命令均通过锁定的本地 uv 环境执行。

本地结论：**Accept 类型门禁扩围与现有测试回归，权限风险按用户决定延期**。写本报告时尚未创建 PR/commit，未执行远端 GitHub Actions Run；远端 CI 需要在获得相应授权后核验。回滚方式是撤销本任务对 CI、Mypy 配置、相关 API/服务/评测类型修正和本报告的改动，无数据库或外部状态需要回滚。
