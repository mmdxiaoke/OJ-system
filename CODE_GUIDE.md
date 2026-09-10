# 代码导读（CODE GUIDE）

> 目标：让接手这个项目的人能回答三个问题——**这个功能在哪？这个请求怎么走完的？我要改一处该动哪里？**
> 
> 文中行号基于 `main` 分支 commit `d2c6401`。如果行号对不上，用符号名（函数名）搜索即可，符号名是稳定锚点。
> 完整接口契约见 [API.md](API.md)，整体说明见 [README.md](README.md)。

---

## 0. 先看你要干什么

| 你的目的                    | 直接看                                                     |
| ----------------------- | ------------------------------------------------------- |
| 第一次读这个项目，想理清请求怎么走       | [§1 一条请求的完整生命周期](#1-一条请求的完整生命周期)                        |
| 想知道某个功能对应哪个文件           | [§3 按功能查代码](#3-按功能查代码)                                  |
| 想改默认时间/内存限制、提交频率、会话有效期  | [§4.1 全局配置](#41-全局配置一切可调参数的唯一出处)                        |
| 想加一个新接口                 | [§7 常见改动指引](#7-常见改动指引)                                  |
| 想改评测判定逻辑（比如加 SPJ、改比对规则） | [§3.2 评测引擎](#32-step-2--3评测引擎) + [§4.6](#46-评测状态与测试点状态) |
| 想改前端某个页面                | [§5 前端代码地图](#5-前端代码地图)                                  |
| 想知道 data/ 里那些 JSON 长什么样 | [§6 数据文件格式](#6-数据文件格式)                                  |
| 改完怎么验证没坏                | [§8 调试与验证](#8-调试与验证)                                    |

---

## 1. 一条请求的完整生命周期

以 `POST /api/submissions/`（提交代码）为例，这是全项目最复杂的一条链路：

```
Streamlit 页面
  frontend/views/submission_page.py::_submit()            ← 收集题目/语言/代码
    │
    └─ frontend/api_client.py::OJClient.submit()          ← 带上 Cookie 发 HTTP
         │
         ▼
FastAPI 应用 backend/app.py::create_app()
  ├─ access_log_middleware (app.py:61)                    ← 只记方法/路径/状态码，不记请求体
  └─ 路由匹配 backend/routers/submissions.py:27
       │
       ├─ 1. 鉴权依赖 Depends(get_current_user)            core/deps.py:47
       │       ├─ 读 Cookie oj_session                    config.py:50
       │       ├─ 查 data/sessions.json                    core/deps.py:21 _resolve_session
       │       └─ 未登录 → 抛 ApiError(401)；banned → 403
       │      （依赖先于请求体校验执行，所以 401 一定优先于 400）
       │
       ├─ 2. 解析并校验请求体 read_json_body()             core/request.py:11
       │       └─ _str_field() 检查必填/类型 → 400
       │
       ├─ 3. 频率限制 check_rate_limit()                   services/submission_service.py:48 → 429
       ├─ 4. 题目存在？ get_problem_or_404()               services/problem_service.py:41 → 404
       ├─ 5. 语言存在？ get_language_or_404()              services/language_service.py:201 → 404
       │
       ├─ 6. 落库 create_submission()                      services/submission_service.py:65
       │       └─ 写 data/submissions/{id}.json（状态 pending）
       │
       ├─ 7. 起后台任务 start_judge()                       services/submission_service.py:105
       │       └─ asyncio.create_task(judge_submission_task)
       │            └─ judge/engine.py::judge_submission()   ← 真正的评测，见 §3.2
       │
       └─ 8. 立刻返回 {code:200, data:{submission_id, status:"pending"}}
```

**三个贯穿全局的约定**（不理解它们会看不懂所有路由）：

1. **统一响应**：任何返回都是 `{"code": int, "msg": str, "data": any}`，`code` 恒等于 HTTP 状态码。
   构造成功响应统一用 `core/responses.py::ok()`（:48），抛错统一用 `raise ApiError(状态码, "消息")`（:32）。
2. **异常优先级**：`401 > 403 > 400 > 429 > 409 > 404 > 500`（`core/responses.py:18`）。
   实现方式 = 鉴权放 `Depends`（天然最先执行）+ 路由内部按优先级顺序显式检查。
3. **错误绝不泄露内部信息**：全局兜底处理器 `core/responses.py::register_exception_handlers()`（:53）
   把未捕获异常统一变成 `500 internal server error`，不含堆栈和路径。

---

## 2. 文件职责总表

### 后端 `backend/`

| 文件                               | 一句话职责                               | 最该记住的符号                                                 |
| -------------------------------- | ----------------------------------- | ------------------------------------------------------- |
| `app.py`                         | 应用工厂：中间件、异常处理器、注册路由、启动初始化           | `create_app()` :41                                      |
| `config.py`                      | **所有可调参数的唯一出处**                     | `DEFAULT_TIME_LIMIT` :36、`builtin_languages()` :87      |
| `core/responses.py`              | 统一响应与异常体系                           | `ApiError` :32、`ok()` :48                               |
| `core/storage.py`                | JSON 文件持久化（原子写 + 异步锁）               | `JsonFile` :38、`write_json_file()` :123                 |
| `core/security.py`               | 密码哈希、会话 ID、模型密钥加解密                  | `hash_password()` :26、`encrypt_secret()` :90            |
| `core/deps.py`                   | 会话解析与权限依赖                           | `get_current_user()` :47、`require_admin()` :56          |
| `core/request.py`                | 读请求体（校验失败统一 400）                    | `read_json_body()` :11                                  |
| `core/pagination.py`             | 分页参数语义                              | `parse_pagination()` :7                                 |
| `models/problem.py`              | 题目字段校验与默认值补全                        | `parse_problem_body()` :58、`with_defaults()` :114       |
| `services/problem_service.py`    | 题目 CRUD 与可见性                        | `create_problem()` :58、`set_log_visibility()` :84       |
| `services/user_service.py`       | 用户注册/认证/角色/统计                       | `create_user()` :58、`authenticate()` :102               |
| `services/language_service.py`   | 语言注册与**命令安全校验**                     | `validate_language_config()` :114、`split_command()` :45 |
| `services/submission_service.py` | 提交记录、限流、列表查询与视图裁剪                   | `create_submission()` :65、`query_submissions()` :177    |
| `services/stats_service.py`      | `submit_count` / `resolve_count` 统计 | `summarize()` :18                                       |
| `services/log_service.py`        | 日志访问审计的记录与查询                        | `record_access()` :20                                   |
| `judge/engine.py`                | 评测主流程：编译→逐点运行→汇总                    | `judge_submission()` :68、`_judge_in_workdir()` :129     |
| `judge/runner.py`                | 进程执行：超时、内存监控、进程树清理                  | `run_program()` :147、`_memory_monitor()` :128           |
| `judge/comparator.py`            | 输出比对                                | `normalize()` :8、`compare()` :18                        |
| `ai/config_store.py`             | 模型配置存取（密钥加密）                        | `save_config()` :42、`resolved_config()` :115            |
| `ai/llm_client.py`               | OpenAI 兼容客户端（流式 + 用量）               | `LLMClient` :45、`extract_json()` :204                   |
| `ai/pipeline.py`                 | 六阶段命题流水线                            | `run_pipeline()` :139、`_verify_data()` :273             |
| `ai/task_manager.py`             | 任务调度、SSE 推送、中断、计费                   | `AITask` :23、`_run_task()` :155、`cancel_task()` :306    |
| `routers/*.py`                   | HTTP 层：解析参数、调服务、返回响应                | 见 §3 各节                                                 |

### 前端 `frontend/`

| 文件                         | 一句话职责                         | 最该记住的符号                                         |
| -------------------------- | ----------------------------- | ----------------------------------------------- |
| `app.py`                   | 入口：页面注册与侧边栏                   | `PAGES` :30、`main()` :39                        |
| `api_client.py`            | 唯一的 HTTP 出口（Cookie 会话 + 统一异常） | `OJClient` :42、`ApiResult` :20                  |
| `views/common.py`          | 页面公共件：选择器、表单编辑器、详情渲染          | `problem_selector()` :200、`problem_form()` :331 |
| `views/dashboard.py`       | 仪表盘首页                         | `render()` :16                                  |
| `views/auth_page.py`       | 用户中心                          | `_login_register()` :44、`_admin_panel()` :141   |
| `views/problem_page.py`    | 题库                            | `_detail()` :78、`_create()` :129                |
| `views/submission_page.py` | 评测中心                          | `_submit()` :66、`_records()` :125               |
| `views/ai_page.py`         | AI 智能命题                       | `_compose()` :101、`_watch()` :151               |

---

## 3. 按功能查代码

### 3.1 Step 1：题目管理

| 接口                          | 路由函数                                           | 服务层                                  |
| --------------------------- | ---------------------------------------------- | ------------------------------------ |
| `GET /api/problems/`        | `routers/problems.py::list_problems` :23       | `problem_service.list_problems` :12  |
| `POST /api/problems/`       | `add_problem` :30                              | `problem_service.create_problem` :58 |
| `GET /api/problems/{id}`    | `get_problem` :39                              | `problem_service.get_problem` :28    |
| `PUT /api/problems/{id}`    | `update_problem` :48                           | `problem_service.update_problem` :67 |
| `DELETE /api/problems/{id}` | `delete_problem` :58（`Depends(require_admin)`） | `problem_service.delete_problem` :76 |

**字段校验全在 `models/problem.py`**：

* `ProblemPayload` :24 定义必填/可选字段与类型；
* `parse_problem_body()` :58 做二次校验（id 正则、文本长度、`time_limit` 范围、`time_limit`/`memory_limit` 缺省时**存 `None` 而不是默认值**——这是为了在评测时能实现「题目 → 语言 → 系统默认」的取值链，见 `judge/engine.py::_effective_limits` :35）；
* `with_defaults()` :114 只在**返回给前端时**补默认值（`str → ""`、`list → []`、`time_limit → 3.0`）。

**两个容易记错的返回码**：题目 id 重复是 `409`，用户名重复是 `400`（这是 API 文档的规定，不是笔误）。

### 3.2 Step 2 & 3：评测引擎

评测是本项目的技术核心，链路分成四段：

```
submission_service.start_judge (:105)          ← 起 asyncio 后台任务
  └─ judge/engine.py::judge_submission (:68)   ← 取题目/语言、定限制
       └─ _judge_in_workdir (:129)             ← 建临时目录、写源码
            ├─ 编译/语法检查                    ← engine.py 内部
            ├─ 逐测试点 run_program()           ← judge/runner.py:147
            │    ├─ _memory_monitor (:128)      ← psutil 轮询 RSS，超限杀进程 → MLE
            │    ├─ asyncio.wait_for(timeout)   ← 超时 → TLE
            │    └─ _kill_tree (:74)            ← 杀整棵进程树
            ├─ comparator.compare (:18)         ← 忽略行末空格/末尾空行
            ├─ _classify (:50)                  ← 运行结果 → AC/WA/TLE/MLE/RE/UNK
            └─ finish_submission()              ← 回写得分、details、耗时、内存
```

| 关注点       | 代码位置                                          | 说明                                              |
| --------- | --------------------------------------------- | ----------------------------------------------- |
| 资源限制怎么取   | `engine.py::_effective_limits` :35            | 题目配置 → 语言配置 → 系统默认（3s / 128MB）                  |
| 内存怎么判 MLE | `runner.py::_memory_monitor` :128             | 每 20ms 采样进程树 RSS（`config.MEMORY_POLL_INTERVAL`） |
| 超时怎么判 TLE | `runner.py::run_program` :147                 | `asyncio.wait_for` + 超时杀进程树                     |
| 输出比对规则    | `comparator.py::normalize` :8                 | 行末空格、末尾空行忽略，其余严格一致                              |
| 得分怎么算     | `engine.py::_judge_in_workdir` :129           | 每测试点 10 分，`counts = 测试点数 × 10`                  |
| CE 怎么判    | `engine.py::_judge_in_workdir` :129           | 编译命令非 0 退出；Python 用 `py_compile` 检查语法           |
| 提交频率限制    | `submission_service.py::check_rate_limit` :48 | 60 秒 3 次，进程内计数                                  |

**动态注册语言的安全边界**（改这里前务必读）：

* `language_service.py::split_command` :45 —— 自己实现的分词器，**不走 shell**，直接拒绝 `; | & \` $ < >` 换行等字符；
* `check_executable_allowed` :90 —— 只允许 `ALLOWED_EXECUTABLES` :25 白名单（g++/python/javac/node…），明确禁止 `FORBIDDEN_EXECUTABLES` :35（sh/bash/cmd/powershell/sudo…）；
* `validate_language_config` :114 —— 校验 name/ext/占位符/限制范围；
* `{src}` `{exe}` `{workdir}` 由 `engine.py::_build_argv` :25 替换成临时目录里的绝对路径。

### 3.3 Step 3：评测管理

| 接口                                  | 路由函数                                           | 关键逻辑                     |
| ----------------------------------- | ---------------------------------------------- | ------------------------ |
| `GET /api/submissions/`             | `routers/submissions.py::list_submissions` :51 | 一级条件不可全空、分页语义、普通用户强制只看自己 |
| `GET /api/submissions/{id}`         | `get_submission` :83                           | 非本人非管理员 → 403；不存在 → 404  |
| `PUT /api/submissions/{id}/rejudge` | `rejudge` :94                                  | 仅管理员，重置为 pending 后重新起任务  |

**「三种视图」的裁剪规则**（前端展示与 API 文档对齐的关键）：

* `summary_view` :210 —— 列表用；`pending`/`error` 只返回 `submission_id` + `status`；
* `detail_view` :222 —— 详情用；`pending` 时其余字段为 `null`；
* `owner_view` :239 —— 在详情基础上补 `user_id/problem_id/language/code/submit_time`。

### 3.4 Step 4：用户与权限

| 接口                         | 路由函数                             | 服务层                                                          |
| -------------------------- | -------------------------------- | ------------------------------------------------------------ |
| `POST /api/auth/login`     | `routers/auth.py::login` :28     | `user_service.authenticate` :102 → `deps.create_session` :63 |
| `POST /api/auth/logout`    | `logout` :49                     | `deps.drop_session` :83                                      |
| `POST /api/users/`         | `routers/users.py::register` :33 | `user_service.create_user` :58                               |
| `POST /api/users/admin`    | `create_admin` :21               | 同上，`role="admin"`                                            |
| `GET /api/users/{id}`      | `get_user` :52                   | 非本人非管理员 → 403                                                |
| `GET /api/users/`          | `list_users` :43                 | 仅管理员 + 分页                                                    |
| `PUT /api/users/{id}/role` | `update_role` :63                | 仅管理员；非法角色 400，用户不存在 404                                      |

* **权限判断的唯一入口**：`core/deps.py`。要改鉴权规则（比如加「教师」角色），只动这个文件。
* **初始管理员**：`user_service.ensure_initial_admin` :49，由 `app.py::_startup` :85 调用；账号密码在 `config.py:57`。
* **banned 用户**：登录时 `authenticate` 抛 403；已登录会话在 `get_current_user` :47 里也返回 403。
* **统计口径**：`stats_service.py`。`submit_count` 按提交次数累加；`resolve_count` 按「有过满分提交的题目数」去重（`_is_accepted` :7）。

### 3.5 Step 5：评测日志与审计

| 接口                                      | 路由函数                                      | 关键逻辑                          |
| --------------------------------------- | ----------------------------------------- | ----------------------------- |
| `GET /api/submissions/{id}/log`         | `routers/logs.py::get_submission_log` :16 | 见下方可见性规则                      |
| `PUT /api/problems/{id}/log_visibility` | `set_log_visibility` :51                  | 仅管理员，写 `problem.public_cases` |
| `GET /api/logs/access/`                 | `list_access_logs` :62                    | 仅管理员，返回裸数组（按 API 文档）          |

**日志可见性规则**（`logs.py:16` 内部，改动时注意顺序）：

1. 提交不存在 → 404（不记录审计）；
2. `allowed = 管理员 or 本人 or 题目 public_cases`，否则记录 `status=403` 并抛 403；
3. `details` 只在「管理员 或 public_cases=True」时返回；
4. 每次通过前置检查的访问都会写一条审计（`log_service.record_access` :20）。

### 3.6 Step 6：前端

见 [§5 前端代码地图](#5-前端代码地图)。要点：**所有数据都经过 `api_client.py`**，页面里不出现 `requests`。

### 3.7 Advance：AI 智能命题

| 接口                                      | 路由函数                      | 说明                                |
| --------------------------------------- | ------------------------- | --------------------------------- |
| `GET/PUT /api/ai/model-config`          | `routers/ai.py` :26 / :32 | 查询只返回 `api_key_configured`，永不返回密钥 |
| `POST /api/ai/problem-tasks/`           | `create_task` :42         | 创建任务并立即返回 task_id                 |
| `GET /api/ai/problem-tasks/{id}`        | `get_task` :65            | 状态/进度/结果/用量                       |
| `GET /api/ai/problem-tasks/{id}/events` | `task_events` :73         | SSE 实时进度                          |
| `PUT /api/ai/problem-tasks/{id}/cancel` | `cancel_task` :116        | 真中断                               |
| `POST /api/ai/problem-tasks/{id}/apply` | `apply_task` :123         | 把结果导入题库（create/update）            |

**任务执行链**：

```
task_manager.create_task (:104)
  └─ asyncio.create_task(_run_task) (:155)
       ├─ config_store.resolved_config (:115)   ← 解密密钥，仅内存可见
       ├─ pipeline.run_pipeline (:139)
       │    1 analyze → 2 statement → 3 solution → 4 generator → 5 verify → 6 finalize
       │    └─ _verify_data (:273)              ← 真跑生成脚本 + 标程 + 暴力解交叉验证
       ├─ _on_event (:217)                      ← 进度入队 + 落盘
       └─ _add_usage (:241)                     ← Token 累计与费用计算
```

* **中断**：`cancel_task` :306 调 `task.runner.cancel()`，会一并取消进行中的 httpx 流式请求；
* **SSE**：`_publish` :264 把事件塞进每个订阅者的 `asyncio.Queue`，路由侧 `event_stream()` 逐条下发；
* **Token 计费**：`_add_usage` :241，公式 `输入/单位×单价 + 输出/单位×单价`；接口没返回 `usage` 时标记 `estimated=True`。

### 3.8 系统接口

| 接口                 | 位置                            | 说明                                              |
| ------------------ | ----------------------------- | ----------------------------------------------- |
| `GET /`            | `routers/system.py::root` :33 | 服务信息                                            |
| `GET /health`      | `health` :42                  | 健康检查（前端「连通性」按钮用）                                |
| `POST /api/reset/` | `reset_system` :47            | 清数据、退出登录、重建初始管理员；`OJ_RESET_OPEN=1` 时放宽为「登录用户即可」 |

---

## 4. 关键机制

### 4.1 全局配置：一切可调参数的唯一出处

`backend/config.py`。想改默认时间/内存限制、提交频率、会话有效期、用户名密码长度，**只改这里**：

| 参数                                            | 行号        | 默认值                           |
| --------------------------------------------- | --------- | ----------------------------- |
| `DEFAULT_TIME_LIMIT` / `DEFAULT_MEMORY_LIMIT` | :36 / :37 | 3 s / 128 MB                  |
| `SCORE_PER_TESTCASE`                          | :38       | 10                            |
| `MAX_OUTPUT_BYTES`                            | :41       | 4 MB                          |
| `COMPILE_TIME_LIMIT`                          | :43       | 10 s                          |
| `MEMORY_POLL_INTERVAL`                        | :45       | 0.02 s                        |
| `SESSION_COOKIE_NAME` / `SESSION_TTL_SECONDS` | :50 / :51 | `oj_session` / 7 天            |
| `ADMIN_USERNAME` / `ADMIN_PASSWORD`           | :57 / :58 | `admin` / `admintestpassword` |
| `USERNAME_MIN_LEN` 等                          | :63-:65   | 3 / 40 / 6                    |
| `SUBMIT_RATE_WINDOW` / `SUBMIT_RATE_MAX`      | :70 / :71 | 60 s / 3 次                    |
| `builtin_languages()`                         | :87       | python / cpp / c 的编译运行命令      |

### 4.2 统一响应与异常优先级

* 构造成功：`ok(msg, data)`（`core/responses.py:48`）；
* 抛业务错：`raise ApiError(404, "problem not found")`（:32）；
* 优先级表：`STATUS_PRIORITY`（:18）——它只是文档化的约束，真正的执行顺序由「`Depends` 先于 body 校验」+ 路由内显式检查保证；
* 422 → 400：`register_exception_handlers` 里注册了 `RequestValidationError` 处理器（:53 起）；
* 兜底 500：同一函数的 `Exception` 处理器，**不含堆栈**。

### 4.3 会话与鉴权

| 环节         | 代码                                                                  |
| ---------- | ------------------------------------------------------------------- |
| 生成 ID      | `security.py::new_session_id` :56（uuid4 + 随机字节）                     |
| 建会话 / 删会话  | `deps.py::create_session` :63 / `drop_session` :83                  |
| 读会话（含过期清理） | `deps.py::_resolve_session` :21                                     |
| 下发 Cookie  | `routers/auth.py::_set_session_cookie` :15（HttpOnly + SameSite=Lax） |
| 依赖注入       | `deps.py::get_current_user` :47 / `require_admin` :56               |

### 4.4 存储与并发

`core/storage.py`：

* `JsonFile` :38 —— 单文件读写，内部一把 `asyncio.Lock`，写操作走「临时文件 + `os.replace`」原子替换；
* `read_json_file` :113 / `write_json_file` :123 / `delete_file` :136 —— 按 id 分文件的题目/提交用它们；
* `problem_lock` :160 / `submission_lock` :164 —— 每个题目/提交一把锁，保证「读-改-写」不互相覆盖；
* 阻塞 I/O 一律用 `asyncio.to_thread` 包装，避免卡住事件循环。

### 4.5 分页规则（`core/pagination.py:7`）

| `page` | `page_size` | 行为           |
| ------ | ----------- | ------------ |
| 空      | 空           | 返回全部         |
| 空      | 有值          | 第一页          |
| 有值     | 空           | **400 参数错误** |
| 有值     | 有值          | 对应页          |

### 4.6 评测状态与测试点状态

两套状态不能混：

* **submission 状态**：`pending` / `success` / `error`（`error` 只在**评测流程本身**出问题时出现）；
* **测试点结果**：`AC` / `WA` / `TLE` / `MLE` / `RE` / `CE` / `UNK`，写在 `submission.details` 里，通过 Step 5 的日志接口暴露。

注意：编译失败（CE）时 submission 状态仍是 `success`（因为评测正常返回了结果），只是 `score=0`、`compile_info.result="failed"`。

---

## 5. 前端代码地图

### 5.1 页面 → 文件 → 函数

| 导航页     | 文件                         | 主要函数                                                                                    |
| ------- | -------------------------- | --------------------------------------------------------------------------------------- |
| 仪表盘     | `views/dashboard.py`       | `render` :16（含未登录引导 `_welcome_guest` :82）                                               |
| 用户中心    | `views/auth_page.py`       | `_login_register` :44、`_profile` :102、`_admin_panel` :141、`_settings` :205              |
| 题库      | `views/problem_page.py`    | `_list` :61、`_detail` :78、`_create` :129、`_edit` :139、`_delete` :151、`_visibility` :169 |
| 评测中心    | `views/submission_page.py` | `_submit` :66、`_records` :125、`_detail` :179、`_languages` :210、`_rejudge` :251          |
| AI 智能命题 | `views/ai_page.py`         | `_model_config` :43、`_compose` :101、`_watch` :151、`_show_result` :198、`_task_list` :250 |

页面注册在 `app.py::PAGES` :30；侧边栏状态与快捷按钮在 `app.py::main` :39。

### 5.2 公共组件（`views/common.py`）

改前端交互几乎都会用到这些：

| 函数                                    | 行号          | 作用                               |
| ------------------------------------- | ----------- | -------------------------------- |
| `client()`                            | :74         | 取当前会话的 `OJClient`                |
| `require_login()` / `require_admin()` | :95 / :103  | 未登录/无权限时提示并 `st.stop()`          |
| `notify()` / `show_data()`            | :114 / :123 | 统一成功/失败提示                        |
| `problem_list()`                      | :167        | 带会话缓存的题目列表                       |
| `problem_selector()`                  | :200        | 题目下拉（含 🔄 刷新）                    |
| `submission_selector()`               | :252        | 提交下拉（+ 手动输入兜底）                   |
| `pager()`                             | :285        | 上一页/下一页                          |
| `cases_editor()`                      | :306        | 样例/测试点逐条编辑器                      |
| `problem_form()`                      | :331        | 题目字段表单                           |
| `json_or_form_editor()`               | :396        | 表单 / JSON 双模式 + 自动 create/update |
| `render_submission_detail()`          | :437        | 提交详情 + 测试点明细（多处复用）               |
| `submission_table()`                  | :495        | 提交列表表格                           |

### 5.3 API 客户端（`api_client.py`）

* `ApiResult` :20 —— 封装 `status / code / msg / data`，`ok` 属性判断是否成功，`error_text()` 生成统一错误文案；
* `OJClient.request` :56 —— 所有请求的唯一出口，网络异常也转成 `ApiResult`，页面永不崩；
* 业务方法按模块分组：用户 :90-113、题目 :119-134、语言与评测 :140-163、AI :169-190；
* `ai_events()` :190 —— SSE 流式读取，`yield (event, data)`。

---

## 6. 数据文件格式

`data/` 目录（已 gitignore），可直接用编辑器打开排查问题：

| 文件                      | 结构                                                                                                                                                                 |
| ----------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `problems/{id}.json`    | 题目配置；`time_limit`/`memory_limit` 为 `null` 表示「未显式设置」，评测时回落到语言/系统默认                                                                                                  |
| `submissions/{id}.json` | `{submission_id, user_id, problem_id, language, code, status, score, counts, compile_info, run_info, error_info, details[], time, memory, created_at, updated_at}` |
| `users.json`            | `{next_id, users:{id: {user_id, username, password_hash, role, join_time, created_at}}}`                                                                           |
| `sessions.json`         | `{sessions:{session_id: {user_id, created_at}}}`                                                                                                                   |
| `languages.json`        | `{languages:{name: {name, file_ext, compile_cmd, run_cmd, time_limit, memory_limit, exe_ext, check_cmd}}}`                                                         |
| `access_logs.json`      | `{logs:[{user_id, problem_id, action, time, timestamp, status}]}`                                                                                                  |
| `ai_config.json`        | `{config:{provider_url, model, api_key_enc, input_price, output_price, price_unit, updated_at}}`（密钥已加密）                                                            |
| `ai_tasks.json`         | `{tasks:{task_id: 任务快照}}`                                                                                                                                          |
| `secret.key`            | 本地主密钥（32 字节，权限 600，**不要提交**）                                                                                                                                       |

`details[]` 的每一项形如 `{"id": 1, "result": "AC", "time": 0.049, "memory": 9.68, "message": ""}`。

---

## 7. 常见改动指引

| 想做的事                 | 需要改的地方                                                                                                                                                                      |
| -------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 加一个新接口               | ① 在 `routers/xxx.py` 加 `@router.get/post`，用 `Depends(get_current_user)` 或 `require_admin` 声明权限；② 业务逻辑放 `services/xxx_service.py`；③ 返回 `ok(...)`；④ 在 `tests/test_api.py` 加断言 |
| 加一个前端页面              | ① 新建 `frontend/views/xxx_page.py`，暴露 `render()`；② 在 `app.py::PAGES` 注册；③ 数据一律通过 `api_client.py` 取                                                                           |
| 改默认时间/内存限制           | `config.py:36`、`config.py:37`                                                                                                                                               |
| 改提交频率限制              | `config.py:70` + `submission_service.py::check_rate_limit` :48                                                                                                              |
| 新增内置语言               | `config.py::builtin_languages()` :87（注意白名单 `language_service.py:25`）                                                                                                        |
| 支持新的评测判定（如 SPJ、浮点误差） | `judge/comparator.py` + `judge/engine.py::_classify` :50                                                                                                                    |
| 改内存/超时判定方式           | `judge/runner.py::run_program` :147、`_memory_monitor` :128                                                                                                                  |
| 改错误文案                | 抛出点的 `ApiError(码, "文案")`；全局兜底在 `core/responses.py:53`                                                                                                                       |
| 加角色（如 teacher）       | `config.py::VALID_ROLES` :76 → `core/deps.py` 加依赖 → 各路由替换依赖                                                                                                                 |
| 改题目字段校验规则            | `models/problem.py::parse_problem_body` :58                                                                                                                                 |
| 改日志可见性策略             | `routers/logs.py::get_submission_log` :16                                                                                                                                   |
| 改 AI 命题流程/提示词        | `ai/pipeline.py`：`STAGES` :36、`run_pipeline` :139、各阶段 user prompt                                                                                                           |
| 改 Token 计价公式         | `ai/task_manager.py::_add_usage` :241                                                                                                                                       |
| 改前端某个页面的布局           | 对应 `views/*_page.py` 里的 `_xxx()` 函数；公共件在 `views/common.py`                                                                                                                  |

---

## 8. 调试与验证

```bash
python run.py backend                 # 起后端，http://127.0.0.1:8000/docs 可直接点接口
python run.py frontend                # 起前端，http://127.0.0.1:8501
python run.py test                    # 228 项接口断言
python run.py test-frontend           # 45 项前端断言
python -m ruff check .                # 代码规范
python examples/load_problems.py      # 导入示例题目
```

**测试文件与功能的对应关系**：

| 测试位置                                            | 覆盖内容                               |
| ----------------------------------------------- | ---------------------------------- |
| `tests/test_api.py::test_users`                 | Step 4：注册/登录/权限/禁用/列表分页            |
| `tests/test_api.py::test_problems`              | Step 1：增删改查、字段校验、409/404           |
| `tests/test_api.py::test_languages`             | Step 2：语言列表、注册、命令注入拦截              |
| `tests/test_api.py::test_judge`                 | Step 2：AC/WA/TLE/MLE/RE/CE、部分得分、限流 |
| `tests/test_api.py::test_submission_management` | Step 3：筛选分页、详情权限、重新评测              |
| `tests/test_api.py::test_logs`                  | Step 5：可见性、details 裁剪、审计           |
| `tests/test_api.py::test_ai`                    | Advance：配置、SSE、中断、计费、导入题库          |
| `tests/test_api.py::test_reset`                 | 系统重置                               |
| `tests/test_frontend.py`                        | 页面渲染 + 登录/建题/提交/详情/改角色交互           |
| `tests/fake_llm_server.py`                      | 本地假模型服务，让 AI 链路可离线测试               |

**改代码时的推荐节奏**：改 `services/` → 跑 `python run.py test`；改 `frontend/` → 跑 `python run.py test-frontend`；两者都跑一遍再提交。

---

## 9. 命名与代码约定

* **分层**：`routers`（HTTP 细节）→ `services`（业务）→ `core/storage`（持久化）。路由里不写业务逻辑，服务里不碰 `Request`。
* **异步**：所有 I/O 用 `async def`；阻塞调用包 `asyncio.to_thread`；长任务用 `asyncio.create_task` 并保存引用（见 `submission_service._judge_tasks`、`task_manager._persist_tasks`）。
* **命名**：私有辅助函数前缀 `_`；服务函数用动词开头（`create_/get_/update_/delete_/list_`）；`_or_404` 后缀表示「不存在就抛 404」。
* **注释**：只在「为什么这么做」处写中文注释（比如安全白名单、状态码优先级），不复述代码在做什么。
* **提交信息**：Conventional Commits（`feat(scope): 描述` / `fix` / `test` / `docs` / `chore`）。
* **行宽**：120 字符，`ruff check` 必须零告警。
