# Clients 模块 — 外部资源客户端

## 模块简介

封装对外部 Web 资源的 HTTP 请求与 HTML 抓取逻辑。
与 `app/services/` 中的 API 客户端不同，此模块专注于 **网页抓取（Scraping）**，
不调用 JSON API，而是直接爬取 HTML 页面并返回原始文本供后续解析。

## 核心功能

| 客户端 | 功能 | 数据来源 |
|--------|------|----------|
| `BangumiClient` | 抓取 Bangumi 评论页面 | `https://bgm.tv/subject/{id}/comments` |
| `BangumiClient` | 抓取 Bangumi 长评页面 | `https://bgm.tv/subject/{id}/reviews` |

## 文件结构说明

```
clients/
└── bangumi_client.py  # Bangumi 网页抓取客户端（HTML Scraper）
```

### bangumi_client.py — 网页抓取客户端 ([源码](bangumi_client.py))

- **类 `BangumiClient`**：基于 httpx 的异步 HTTP 客户端
  - 配置了浏览器级 User-Agent 和 Referer 头以绕过反爬
  - `get_comments_html(subject_id)` — 获取短评页面的 HTML
  - `get_reviews_html(subject_id)` — 获取长评页面的 HTML
  - 30 秒超时，带 HTTP 状态码错误处理和网络异常日志

**注意**：此模块与 `app/services/bangumi_client.py` 是不同的组件：
- `app/clients/bangumi_client.py` → **HTML 抓取**（原始网页）
- `app/services/bangumi_client.py` → **JSON API 调用**（Bangumi Open API）

## 依赖关系

**被谁调用**：
- `app/services/bangumi_service.py` → 调用 `BangumiClient` 获取短评/长评 HTML，然后用 BeautifulSoup 解析

**调用谁**：
- 无内部依赖，仅依赖第三方库 `httpx`

**外部依赖**：
- `httpx` — 异步 HTTP 客户端
