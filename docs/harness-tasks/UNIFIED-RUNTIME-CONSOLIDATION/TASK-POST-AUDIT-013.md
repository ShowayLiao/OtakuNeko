# TASK-POST-AUDIT-013：Provider SSRF、Egress Allowlist 与 Endpoint Authorization

## 目标

把用户可配置 Provider endpoint 和 /models/check 收口为默认 fail-closed 的外部网络边界，阻止内网、回环、link-local、metadata、私网 DNS、恶意 redirect 和未授权探测。

## 当前缺口

- PROVIDER_RESOLVE_DNS 默认关闭，PROVIDER_ALLOWED_HOSTS 默认为空。
- 非 local 模式下，任意公共域名如果未解析校验，可能指向私网地址。
- /models/check 没有业务身份依赖，且 Ollama 分支直接使用独立 httpx.AsyncClient。
- Provider endpoint、redirect、模型检查和主聊天请求需要统一使用相同的 host/port/DNS/redirect policy。

## 依赖与允许范围

### 依赖

- 现有 validate_provider_endpoint()、validate_provider_redirect() 和 ModelGateway HTTP client。
- TASK-POST-AUDIT-011 的 provider-neutral error contract。

### 允许修改

- backend/app/agents/provider_endpoint.py
- backend/app/api/v1/agent.py
- backend/app/harness/model_gateway.py
- backend/app/core/config.py
- backend/app/main.py
- docker-compose.yml 的安全配置说明和 fail-fast 校验
- backend/tests/agents/test_provider_endpoint.py
- backend/tests/acceptance/
- 对应 execution record

### 禁止修改

- 不进行生产部署、真实外部 endpoint 探测或生产迁移。
- 不把 local development 例外扩展到 cloud/deploy mode。
- 不只依赖 prompt、前端校验或环境变量注释作为 SSRF 防护。

## TDD 契约

实现前先增加失败测试，至少覆盖：

1. 非 local 模式拒绝 literal private、loopback、link-local、multicast、unspecified、IPv4-mapped IPv6 endpoint。
2. 非 local 模式拒绝解析到私网地址的 hostname；DNS 多记录中只要有一个危险地址就 fail-closed。
3. allowlist、scheme、port 和 hostname canonicalization 在初始请求和 redirect 上保持一致。
4. redirect 到私网、metadata、不同未授权 host 或未授权 port 时被拒绝。
5. /models/check 需要正确的业务认证/owner scope，并进行 rate limit 或等价保护。
6. Ollama、OpenAI-compatible 和 DeepSeek 检查都使用统一的安全 HTTP client，不自动跟随未经验证的 redirect。
7. DNS 失败、超时、provider 认证失败和 SSRF 拒绝映射为不同的 safe error category，不泄漏内部地址或 raw exception。
8. local mode 的显式 localhost 例外仍可用，但不能影响 cloud mode 的 fail-closed 语义。

## 实现要求

### 1. 配置 fail-closed

非 local 部署必须显式满足 DNS resolution、host/port allowlist 或受控 network egress 之一；配置缺失时应用启动或请求校验失败，不自动退回“只看字符串 host”的弱校验。

### 2. 统一请求边界

所有 Provider HTTP 请求都必须经过：

~~~text
validate initial URL
  -> resolve and validate addresses
  -> connect with no uncontrolled redirect
  -> validate every redirect target
  -> bounded timeout
  -> safe error normalization
~~~

不要在 /models/check、Memory extractor、ModelGateway 和其他 endpoint 中各自创建绕过校验的 Client。

### 3. 认证和 owner scope

/models/check 应使用与 /chat 一致的业务认证边界；header 中的 provider key 只能作为外部 Provider 凭据，不能代替 OtakuNeko 用户身份。日志、Trace 和错误响应不得暴露 key 或完整 endpoint 凭据。

## 验收

- provider endpoint 单元、安全负向和 redirect 测试通过；
- /models/check 的认证、owner scope 和错误投影有 API 测试；
- 后端全量测试、Ruff、适用 Eval 和 git diff --check 通过；
- Docker/local/cloud 配置契约有启动检查或明确测试；
- Review verdict 为 pass，无未处理 High/Medium security finding。

## 回滚

只能回滚到已验证的 local/single-worker adapter；cloud mode 不得通过关闭 DNS、allowlist 或 redirect 校验来恢复可用。若外部 Provider 不满足新边界，应将该 Provider 标记为不可用并保留安全错误，而不是放宽校验。
