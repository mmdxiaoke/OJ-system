## 实验目标[¶](https://dbg-course.github.io/python-docs/oj/#_1 "Permanent link")

构建一个小型但功能完整的 Online Judge (OJ) 系统，分阶段实现，逐步掌握系统设计、API 开发、异步评测、权限控制和前后端交互等核心能力。进阶模块在此基础上引入大语言模型应用开发。

> 快速入门可参考[快速入门文档](https://lab.cs.tsinghua.edu.cn/rust/projects/oj/quick-start/)。

## 技术要求[¶](https://dbg-course.github.io/python-docs/oj/#_2 "Permanent link")

**异步编程实践**：本次作业要求使用 FastAPI 的异步接口（`async def`）完成所有 API 开发，目的是让大家初步体验异步编程的概念和用法。异步编程是现代 Web 开发的重要技术，有助于提高应用程序的并发性能。**不使用异步编程接口将拿不到本次作业分数，请同学们务必注意。**

**项目规模**：为了让大家初步体验较大项目的开发，本次作业代码行数预计在两千行左右，请同学们合理规划时间，做好进度管理。

**提交规范**：要求按照 [Conventional Commits](https://www.conventionalcommits.org/zh-hans/v1.0.0/) 规范编写 Git 提交信息，不符合规范的提交将酌情扣分。

---

## 基础模块（共30分）[¶](https://dbg-course.github.io/python-docs/oj/#30 "Permanent link")

| Step   | 名称   | 主要功能描述                  | 详细文档                                                                   |
| ------ | ---- | ----------------------- | ---------------------------------------------------------------------- |
| Step 1 | 题目管理 | 题目配置加载、字段校验、增删改查        | [step1.md](https://dbg-course.github.io/python-docs/oj/project/step1/) |
| Step 2 | 评测控制 | 程序执行、资源限制、输出比对、动态注册语言   | [step2.md](https://dbg-course.github.io/python-docs/oj/project/step2/) |
| Step 3 | 评测管理 | 提交记录查询、状态管理、重新评测        | [step3.md](https://dbg-course.github.io/python-docs/oj/project/step3/) |
| Step 4 | 用户管理 | 用户注册、登录、权限管理、用户信息查询     | [step4.md](https://dbg-course.github.io/python-docs/oj/project/step4/) |
| Step 5 | 评测日志 | 测试点明细、日志查询、可见性与访问审计     | [step5.md](https://dbg-course.github.io/python-docs/oj/project/step5/) |
| Step 6 | 前端交互 | 用户、题目和评测提交页面，与后端 API 对接 | [step6.md](https://dbg-course.github.io/python-docs/oj/project/step6/) |

---

## 进阶模块（共 10 分）[¶](https://dbg-course.github.io/python-docs/oj/#10 "Permanent link")

| 模块      | 名称      | 主要功能描述             | 详细文档                                                                       |
| ------- | ------- | ------------------ | -------------------------------------------------------------------------- |
| Advance | AI 智能命题 | 在 OJ 系统上实现 AI 辅助命题 | [advance.md](https://dbg-course.github.io/python-docs/oj/project/advance/) |

---

## API 文档[¶](https://dbg-course.github.io/python-docs/oj/#api "Permanent link")

所有接口、参数、异常、状态码等详见 [api.md](https://dbg-course.github.io/python-docs/oj/api/)。

---

## 评分标准[¶](https://dbg-course.github.io/python-docs/oj/#_3 "Permanent link")

参见 [requirements.md](https://dbg-course.github.io/python-docs/oj/requirements/)

---

## 学习资源[¶](https://dbg-course.github.io/python-docs/oj/#_4 "Permanent link")

- **技术教程**:

- [系统设计基础](https://github.com/donnemartin/system-design-primer)

- [Python 异步编程](https://docs.python.org/3/library/asyncio.html)

- [Agent 架构：从文本生成到工具调用](https://lab.cs.tsinghua.edu.cn/rust/projects/agent/agent-architecture/)

- **参考项目**:

- [Codeforces](https://codeforces.com/) - 知名OJ平台

- [LeetCode](https://leetcode.com/) - 编程练习平台

- [HackerRank](https://www.hackerrank.com/) - 技术评测平台

# Step1：题目管理

### 模块目标[¶](https://dbg-course.github.io/python-docs/oj/project/step1/#_1 "Permanent link")

实现题目配置的加载、动态增删改查，支持基础的 OJ 题目管理闭环。

---

### 前置知识要求[¶](https://dbg-course.github.io/python-docs/oj/project/step1/#_2 "Permanent link")

| 技术点         | 推荐学习内容                                   |
| ----------- | ---------------------------------------- |
| JSON 配置文件   | `json.load()`                            |
| REST API 基础 | FastAPI/Flask POST/GET/PUT/DELETE + 参数校验 |
| 异常处理        | `try/except`、HTTP 状态码                    |

---

### 任务分解[¶](https://dbg-course.github.io/python-docs/oj/project/step1/#_3 "Permanent link")

> 具体字段与接口请参考 [api.md](https://dbg-course.github.io/python-docs/oj/api/)

#### 任务 1：题目管理 API[¶](https://dbg-course.github.io/python-docs/oj/project/step1/#1-api "Permanent link")

- 目标：实现题目配置的加载、增删改查。
- 要点：
- 支持**查看题目列表**（返回所有题目的简要信息）。
- 支持**添加题目**（校验字段完整性，保存到存储目录）。
- 支持**编辑题目**（校验更新后的完整题目配置，覆盖原题目内容）。
- 支持**删除题目**（根据题目 id 删除配置文件）。
- 支持**查看具体题目信息**（根据题目 id 返回详细配置）。
- 所有操作需返回结构化 JSON，异常时返回合理 HTTP 状态码。
- 建议：配置内容存入本地目录（如 `problems/`），每题一个 JSON 文件。

---

### OJ 题目字段说明[¶](https://dbg-course.github.io/python-docs/oj/project/step1/#oj "Permanent link")

以洛谷 [P1001 A+B Problem](https://www.luogu.com.cn/problem/P1001) 为例，一个 OJ 题目通常需要以下字段：

#### 必选字段[¶](https://dbg-course.github.io/python-docs/oj/project/step1/#_4 "Permanent link")

1. **id**  
   题目唯一标识（如 "P1001"），用于检索和管理。
2. **title**  
   题目标题（如 "A+B Problem"），便于用户识别。
3. **description**  
   题目描述，详细说明题目的背景和要求。
4. **input_description**  
   输入格式说明，告诉用户输入数据的格式和要求。
5. **output_description**  
   输出格式说明，告诉用户输出数据的格式和要求。
6. **samples**  
   样例输入输出，通常为一个列表，每个元素包含 input 和 output 字段，帮助用户理解题意。
7. **constraints**  
   数据范围和限制条件（如 |a|,|b| ≤ 10^9），用于明确输入输出的边界。
8. **testcases** 测试点，代码准确性通过测试点通过比例给出，会按难易划分，经常有毒瘤出题人卡常、造临界情况等。

#### 可选字段[¶](https://dbg-course.github.io/python-docs/oj/project/step1/#_5 "Permanent link")

1. **hint**  
   额外提示，帮助用户解题（如"有负数哦！"）。
2. **source**  
   题目来源或出处。
3. **tags**  
   题目标签，便于分类检索（如"基础题"、"模拟"）。
4. **time_limit**  
   时间限制，默认单位为 "s"，用于评测。
5. **memory_limit**  
   内存限制，默认单位为 "MB"，用于评测。
6. **author**  
   题目作者。
7. **difficulty**  
   难度等级。

##### 示例结构（JSON）[¶](https://dbg-course.github.io/python-docs/oj/project/step1/#json "Permanent link")

`{   "id": "P1001",   "title": "A+B Problem",   "description": "输入两个整数 a, b，输出它们的和（|a|,|b| <= 10^9）。",   "input_description": "输入两个整数 a 和 b。",   "output_description": "输出 a+b 的结果。",   "samples": [     {       "input": "1 2",       "output": "3"     }   ],   "constraints": "|a|,|b| <= 10^9",   "testcases": [     {       "input": "1 2",       "output": "3"     }   ],   "hint": "有负数哦！",   "source": "洛谷",   "tags": ["基础题"],   "time_limit": 1,   "memory_limit": 128,   "author": "Luogu",   "difficulty": "入门" }`

---

### 评分细则[¶](https://dbg-course.github.io/python-docs/oj/project/step1/#_6 "Permanent link")

| 功能/接口       | 分值    | 评分说明        |
| ----------- | ----- | ----------- |
| 题目列表/详情 API | 3     | 路径、参数、响应、异常 |
| 题目增删改 API   | 2     | 路径、参数、响应、异常 |
| **小计**      | **5** |             |

# Step2：题目评测

### 模块目标[¶](https://dbg-course.github.io/python-docs/oj/project/step2/#_1 "Permanent link")

本模块将实现 OJ 题目的自动化评测。你需要从题库读取题目信息，接收用户提交的代码，自动运行并比对输出，返回结构化的评测结果。要求至少支持 Python 语言，进一步扩展支持 C++ 等多语言。

版本需求

建议 `python` 使用 `3.10` 版本；`C++` 使用 `GCC 9+, C++14` 版本

---

### 题目输入输出规范[¶](https://dbg-course.github.io/python-docs/oj/project/step2/#_2 "Permanent link")

与大一程设课类似，OJ 评测对输入输出格式有严格要求。以 [P1001 A+B Problem](https://www.luogu.com.cn/problem/P1001) 为例：

- **输入**：一行，包含两个整数 a 和 b，空格分隔。
- **输出**：一行，输出 a+b 的结果。

**注意事项：** - 不允许有多余提示语（如"请输入..."）。 - 输出末尾允许有换行，评测时会忽略多余的行末空格和最后一行多余换行。 - 输入输出必须严格匹配样例格式。

**输入样例：**

`1 2`

**输出样例：**

`3`

---

### 任务分解[¶](https://dbg-course.github.io/python-docs/oj/project/step2/#_3 "Permanent link")

#### 任务 1：支持 Python 评测[¶](https://dbg-course.github.io/python-docs/oj/project/step2/#1-python "Permanent link")

- 实现评测流程：自动读取题库中的样例输入输出，将输入传递给用户提交的 Python 代码，捕获输出并与标准答案比对。
- 需要实现异步评测，但仅需支持单用户提交任务即可，不要求支持多用户同时提交代码。关于异步实现，你可以参考 `asyncio.create_task` 这个接口。
- 返回结构化评测结果（如 AC/WA/RE/TLE），并记录可供提交详情页面展示的编译信息、运行结果和错误信息。

**测试点结果**

你只需要考虑如下测试点结果，如果非 `AC` ~ `CE` 状态全部归为 `UNK` 即可。

| 状态缩写    | 全称                    | 含义                         |
| ------- | --------------------- | -------------------------- |
| **AC**  | Accepted Answer       | 输出正确，程序运行无异常且输出结果与标准答案一致。  |
| **WA**  | Wrong Answer          | 输出错误，程序运行无异常但输出结果与标准答案不一致。 |
| **TLE** | Time Limit Exceeded   | 超时，程序运行超过了题目规定的时间限制。       |
| **MLE** | Memory Limit Exceeded | 内存超限，程序使用内存超过了题目限制。        |
| **RE**  | Runtime Error         | 运行时错误，如除零、数组越界、段错误等。       |
| **CE**  | Compilation Error     | 编译错误，代码无法通过编译。             |
| **UNK** | Unknown Error         | 未知错误，程序运行过程中发生了未被捕获的异常。    |

**评测状态**

对于评测状态，你只需要考虑如下三种。

| 状态          | 含义       |
| ----------- | -------- |
| **pending** | 评测正在进行中  |
| **success** | 评测正常返回结果 |
| **error**   | 评测过程出现问题 |

> **如何评测一个任务？**
> 
> 设想一下你在运行一段 python 代码，你需要先将代码保存至一个文件（如 `test.py`），然后调用 `python test.py`，在命令行阅读代码输出结果。现在同理，你只需要调用 `subprocess` 模块，将本该输出到命令行的结果捕获到变量中，与预期输出比对即可。

#### 任务 2：支持多语言评测[¶](https://dbg-course.github.io/python-docs/oj/project/step2/#2 "Permanent link")

> 本任务仅需额外实现 C++ 语言

- 在 Python 评测基础上，扩展支持 C++ 等其他语言。
- 需根据 `language` 字段自动选择编译/运行命令，C++ 需先编译再运行。
- 设计良好的语言配置与切换机制，便于后续扩展。

#### 任务 3：动态注册新语言[¶](https://dbg-course.github.io/python-docs/oj/project/step2/#3 "Permanent link")

- 支持已登录用户动态注册新语言，便于系统扩展。

#### 任务 4：查询支持的语言列表[¶](https://dbg-course.github.io/python-docs/oj/project/step2/#4 "Permanent link")

- 支持查询当前系统支持的所有编程语言。

---

### 评测流程说明[¶](https://dbg-course.github.io/python-docs/oj/project/step2/#_4 "Permanent link")

1. 读取题目信息：根据题目 id 获取输入输出样例和限制条件。
2. 接收用户代码：获取用户提交的代码及语言类型。
3. 运行与比对：将样例输入传递给用户代码，捕获输出并与标准答案比对。
4. 返回结果：以结构化方式返回评测状态、得分、编译信息、运行结果、错误信息、时间和内存等信息。

---

### 时间与内存限制要求[¶](https://dbg-course.github.io/python-docs/oj/project/step2/#_5 "Permanent link")

- 每道题目都应有 time limit（如 1 秒）和 memory limit（如 128MB）字段。
- 评测时，系统必须对用户代码的运行时间和内存消耗进行限制和监控。
- 超出限制时，评测结果应返回 TLE（Time Limit Exceeded，超时）或 MLE（Memory Limit Exceeded，超内存）。

#### 具体要求[¶](https://dbg-course.github.io/python-docs/oj/project/step2/#_6 "Permanent link")

1. 题目配置

2. 在题目 JSON 或数据库结构中，`time_limit` 和 `memory_limit` 字段可选，如果未设置的话，`time_limit` 和 `memory_limit` 按照语言配置、系统默认值的顺序逐项确定，系统默认值分别为 3 秒和 128 MB。

3. 示例：
   
   `{   "id": "P1001",   "title": "A+B Problem",   ...   "time_limit": 1.0,   "memory_limit": 128 }`

4. 评测实现

5. 评测时，自动读取题目的时间和内存限制。

6. 运行用户代码时，必须设置相应的资源限制（如 Python 的 resource、subprocess，或 Linux ulimit）。

7. 若用户代码超时或超内存，应立即终止进程，并返回对应的评测状态（TLE/MLE）。

8. 评测结果

9. 评测接口的响应中，仅需返回最终评测结果即可，具体请参考 `api.md`。详细测试点状态会在 [Step5](https://dbg-course.github.io/python-docs/oj/project/step5/) 中实现。

10. 认为一个测试点 10 分

---

### 评分细则[¶](https://dbg-course.github.io/python-docs/oj/project/step2/#_7 "Permanent link")

| 功能/接口     | 分值    | 评分说明           |
| --------- | ----- | -------------- |
| 多语言评测支持   | 2     | 评测流程支持多语言      |
| 动态注册新语言   | 1     | 支持动态注册、配置安全    |
| 查询支持语言列表  | 1     | 支持查询所有已注册语言    |
| 时间/内存限制实现 | 1     | 能正确限制并判定超时/超内存 |
| **小计**    | **5** |                |

# Step3：评测列表

### 模块目标[¶](https://dbg-course.github.io/python-docs/oj/project/step3/#_1 "Permanent link")

实现评测任务的列表查询、单个评测详情、重新评测等功能，支持分页、筛选、权限控制。

---

### 前置知识要求[¶](https://dbg-course.github.io/python-docs/oj/project/step3/#_2 "Permanent link")

| 技术点         | 推荐学习内容     |
| ----------- | ---------- |
| 数据结构设计      | 列表、字典、分页   |
| REST API 设计 | GET/PUT 路由 |
| 权限控制        | 用户/管理员区分   |

---

### 任务分解[¶](https://dbg-course.github.io/python-docs/oj/project/step3/#_3 "Permanent link")

#### 任务 1：评测列表查询[¶](https://dbg-course.github.io/python-docs/oj/project/step3/#1 "Permanent link")

- 目标：提供 API 查询评测任务列表，支持分页、筛选。
- 要点：可按用户、题目、状态等筛选，支持分页参数。

#### 任务 2：单个评测详情[¶](https://dbg-course.github.io/python-docs/oj/project/step3/#2 "Permanent link")

- 目标：提供 API 查询单个评测任务的详细信息。
- 要点：需校验权限，仅本人或管理员可查；响应应包含评测状态、总分以及可供前端展示的编译信息、运行结果和错误信息。单个测试点的结果通过 Step 5 的评测日志接口查询。

#### 任务 3：重新评测[¶](https://dbg-course.github.io/python-docs/oj/project/step3/#3 "Permanent link")

- 目标：管理员可对评测任务发起重新评测。
- 要点：需校验管理员权限，重新评测后状态变为 pending。

---

### 评分细则[¶](https://dbg-course.github.io/python-docs/oj/project/step3/#_4 "Permanent link")

| 功能/接口    | 分值    | 评分说明       |
| -------- | ----- | ---------- |
| 评测列表查询接口 | 2     | 多条件筛选、分页   |
| 单个评测详情接口 | 2     | 权限校验、响应结构  |
| 重新评测接口   | 1     | 权限、状态变更、异常 |
| **小计**   | **5** |            |

# Step4：用户管理

### 模块目标[¶](https://dbg-course.github.io/python-docs/oj/project/step4/#_1 "Permanent link")

实现用户的注册、登录登出、信息查询、权限管理、用户列表等功能，支持权限控制和安全校验。

---

### 前置知识要求[¶](https://dbg-course.github.io/python-docs/oj/project/step4/#_2 "Permanent link")

| 技术点         | 推荐学习内容          |
| ----------- | --------------- |
| 数据结构设计      | 用户表、权限字段        |
| Session 管理  | Cookie, Session |
| REST API 设计 | GET/POST/PUT 路由 |
| 权限控制        | 用户/管理员区分        |

---

### 任务分解[¶](https://dbg-course.github.io/python-docs/oj/project/step4/#_3 "Permanent link")

#### 任务 0：用户登录/登出/初始管理员[¶](https://dbg-course.github.io/python-docs/oj/project/step4/#0 "Permanent link")

- 目标：实现用户登录、登出接口，系统启动时自动创建初始管理员账户（账号为 `admin` / 密码为 `admintestpassword`）。

**Session 机制原理**

Session 是 Web 应用中维持用户状态的重要机制。由于 HTTP 协议是无状态的，服务器无法直接识别连续请求来自同一用户，因此需要 Session 来解决这个问题。

**工作流程：** 1. 用户首次访问时，服务器创建一个唯一的 Session ID 2. 服务器将 Session ID 通过 Cookie 发送给客户端 3. 客户端后续请求会自动携带这个 Cookie 4. 服务器根据 Session ID 查找对应的用户信息

**Session 存储方式：** - **内存存储**：速度快，但服务器重启会丢失，不适合生产环境 - **文件存储**：持久化，但并发性能较差 - **数据库存储**：可靠性高，支持分布式部署 - **Redis 存储**：高性能，支持过期策略，是主流选择

**安全考虑：** - Session ID 需要足够随机，防止被猜测 - 使用 HTTPS 传输 Cookie，防止被窃取 - 设置合理的过期时间，平衡用户体验和安全性 - 登出时要清除服务器端的 Session 数据

Session 相比 JWT 的优势是可以立即失效（服务器端删除），劣势是需要服务器端存储。建议查阅相关框架的 Session 文档，理解具体实现细节。

Session ID 生成

Session ID 用来唯一标记某个用户的某次会话，并且需要被服务器端存储， 所以你需要保证拿到大规模不重复的 ID。

可以使用 `uuid` 库的 `uuid4` 函数。

**中间件机制**

Web 框架通常使用中间件（Middleware）来处理 Session 管理。中间件是在请求处理过程中的拦截器，可以在请求到达路由处理函数之前或之后执行特定逻辑。

Session 中间件的工作原理： 1. 请求到达时，中间件从 Cookie 中读取 Session ID 2. 根据 Session ID 从存储中加载用户数据 3. 将用户信息附加到请求对象上 4. 请求处理完成后，中间件将 Session 数据保存回存储 5. 如果需要，更新 Cookie 中的 Session ID

这样设计的好处是业务代码无需关心 Session 的底层实现，只需要通过框架提供的接口访问用户信息即可。

**FastAPI Session 中间件示例**

`from starlette.middleware.sessions import SessionMiddleware  app.add_middleware(SessionMiddleware, secret_key="your-secret-key")  @app.post("/login") async def login(request: Request):     request.session["user_id"] = 1     return {"message": "登录成功"}`

建议查阅 Starlette 官方文档中的 [SessionMiddleware](https://www.starlette.io/middleware/#sessionmiddleware) 了解详细用法。

#### 任务 1：用户注册[¶](https://dbg-course.github.io/python-docs/oj/project/step4/#1 "Permanent link")

- 目标：提供用户注册 API。

**数据验证与唯一性约束**

用户注册需要验证输入数据的有效性。主要检查用户名是否已存在、密码是否符合要求。

**基本验证要点：** - 检查用户名长度（3-40 字符） - 检查密码长度（最少 6 位） - 查询数据库确认用户名未被使用 - 密码需要加密后存储（使用bcrypt库）

**处理流程：** 1. 接收用户名、密码参数 2. 验证格式是否正确 3. 检查用户名是否已存在 4. 加密密码并存储到数据库 5. 返回成功信息和用户ID

#### 任务 2：用户信息查询[¶](https://dbg-course.github.io/python-docs/oj/project/step4/#2 "Permanent link")

- 目标：提供 API 查询用户信息。

**权限控制基础**

用户信息查询需要控制权限，确保用户只能查看自己的信息，管理员可以查看所有用户信息。

**权限检查流程：** 1. 从 session 中获取当前登录用户信息 2. 检查要查询的用户ID是否是当前用户自己 3. 或者检查当前用户是否是管理员 4. 如果权限不足，返回403错误 5. 如果权限充足，返回用户信息（不包含密码）

**返回数据：**

`{   "code": 200,    "msg": "success",    "data":    {     "total": 3, // 查询到的用户总数     "users":      [       {"user_id": "1", "join_time": "1924-08-17", "submit_count": 100, "resolve_count": 9},       {"user_id": "2", "join_time": "1911-04-05", "submit_count": 90, "resolve_count": 8},       {"user_id": "3", "join_time": "2012-07-14", "submit_count": 80, "resolve_count": 7},     ]   } }`

时间获取

你可以使用如下命令获取 f'{year}-{month}-{day}' 格式的时间

`from datetime import datetime now = datetime.now() date_str = now.strftime("%Y-%m-%d")`

#### 任务 3：用户权限变更[¶](https://dbg-course.github.io/python-docs/oj/project/step4/#3 "Permanent link")

- 目标：管理员可变更用户权限（如设为 admin/banned）。

如果用户被 ban，其再登录时会被阻止。

**管理员权限检查**

只有管理员可以修改用户权限，需要严格验证操作者身份。

**基本实现：** 1. 检查当前用户是否是管理员 2. 获取要修改的用户ID和新权限 3. 验证新权限值是否有效（如user、admin、banned） 4. 更新数据库中的用户权限 5. 记录操作日志（谁在什么时候修改了谁的权限）

权限提示

注意，在 step1 ~ step3 中，我们没有对题目上传 / 语言创建等进行权限控制。在添加用户权限后，我们需要更新之前的功能。为简化，我们规定为：题目上传 / 创建语言可以由任意用户执行，但是删除题目操作**仅管理员可执行**，暂不考虑删除语言。此外，你还需要修改之前的接口，在用户未登录时无法进行增删查改。

#### 任务 4：用户列表查询[¶](https://dbg-course.github.io/python-docs/oj/project/step4/#4 "Permanent link")

- 目标：管理员可查询所有用户列表，支持分页、筛选。

**分页与筛选**

根据 API 文档，用户列表查询，支持分页参数。

**API 参数：** - `page`（可选）：页码 - `page_size`（可选）：每页大小

**返回格式：**

`{   "code": 200,    "msg": "success",    "data":    {     "total": 3, // 查询到的用户总数     "users":      [       {"user_id": "1", "username": "xiaoming", "join_time": "1924-08-17", "submit_count": 100, "resolve_count": 9},       {"user_id": "2", "username": "xiaohong", "join_time": "1911-04-05", "submit_count": 90, "resolve_count": 8},       {"user_id": "3", "username": "xiaogang", "join_time": "2012-07-14", "submit_count": 80, "resolve_count": 7},     ]   } }`

---

### 评分细则[¶](https://dbg-course.github.io/python-docs/oj/project/step4/#_4 "Permanent link")

| 功能/接口    | 分值    | 评分说明        |
| -------- | ----- | ----------- |
| 用户注册接口   | 2     | 路径、参数、响应、异常 |
| 用户信息查询接口 | 1     | 权限、响应、异常    |
| 用户权限变更接口 | 1     | 权限、参数、响应、异常 |
| 用户列表查询接口 | 1     | 分页、筛选、权限    |
| **小计**   | **5** |             |

# Step5：日志与权限

### 模块目标[¶](https://dbg-course.github.io/python-docs/oj/project/step5/#_1 "Permanent link")

- 实现评测日志的记录与查询，提升系统可追溯性和调试能力。
- 增加细粒度权限管理，如是否允许用户查看评测日志、测例详情等。
- 支持管理员对日志和权限的管理与审计。

---

### 前置知识要求[¶](https://dbg-course.github.io/python-docs/oj/project/step5/#_2 "Permanent link")

| 技术点         | 推荐学习内容      |
| ----------- | ----------- |
| 日志设计        | 日志结构、存储与查询  |
| 权限控制        | 角色权限、接口校验   |
| REST API 设计 | GET 路由、权限参数 |

---

### 任务分解[¶](https://dbg-course.github.io/python-docs/oj/project/step5/#_3 "Permanent link")

#### 任务 1：评测日志记录与查询[¶](https://dbg-course.github.io/python-docs/oj/project/step5/#1 "Permanent link")

- 目标：为每次评测任务记录日志。
- 要点：日志应与评测任务关联，支持按 `submission_id` 查询。

> 为简化，评测日志可见性变为公开后，所有登录的人都能看到这个评测的日志，但是没权限的用户仍对 `Step 2 & 3` 中评测的简单结果不可见

#### 任务 2：日志权限管理[¶](https://dbg-course.github.io/python-docs/oj/project/step5/#2 "Permanent link")

- 目标：实现细粒度权限控制，决定哪些用户可以查看哪些日志内容。
- 要点：
- 普通用户仅能查看自己的评测日志。
- 管理员可查看所有日志。
- 可扩展"允许公开日志"功能，支持题目设置是否允许**所有用户**查看日志详情。

#### 任务 3：权限配置与审计[¶](https://dbg-course.github.io/python-docs/oj/project/step5/#3 "Permanent link")

- 目标：支持管理员配置日志的可见性策略，并能审计用户的日志访问行为。
- 要点：权限配置可针对题目、用户角色等维度，审计日志记录用户的访问操作。

---

### 评分细则[¶](https://dbg-course.github.io/python-docs/oj/project/step5/#_4 "Permanent link")

| 功能/接口     | 分值    | 评分说明           |
| --------- | ----- | -------------- |
| 日志记录与查询   | 2     | 日志结构、查询接口、内容裁剪 |
| 日志/测例权限管理 | 2     | 权限配置、接口校验      |
| 审计与安全说明   | 1     | 日志访问审计         |
| **小计**    | **5** |                |

# Step6：前端交互

> 本模块不要求掌握 JavaScript、HTML、CSS 等前端技术，要求使用 Python 的 `streamlit` 库实现前端页面，并通过 REST API 与 FastAPI 后端交互。

### 什么是 Streamlit？[¶](https://dbg-course.github.io/python-docs/oj/project/step6/#streamlit "Permanent link")

Streamlit 是一个使用 Python 快速开发 Web 应用的开源框架。它提供表单、按钮、输入框、文件上传等常用组件，适合用于构建课程项目的交互界面。应用可通过以下命令启动：

`streamlit run app.py`

本模块要求实现一个与 OJ 后端配套的前端，覆盖用户、题目和评测提交三组页面。前端应调用前述模块实现的 API，不应绕过后端直接读写后端数据。

---

### 模块目标[¶](https://dbg-course.github.io/python-docs/oj/project/step6/#_1 "Permanent link")

- 实现 OJ 系统的基本前端页面，为用户管理、题目管理和评测提交提供可操作的图形界面。
- 完成前端与 FastAPI 后端的接口对接，正确处理身份状态、请求参数、响应数据和异常信息。
- 保证页面功能与前述模块的 API 行为一致。

---

### 前置知识要求[¶](https://dbg-course.github.io/python-docs/oj/project/step6/#_2 "Permanent link")

| 技术点              | 推荐学习内容                          |
| ---------------- | ------------------------------- |
| Streamlit 基础     | 页面布局、表单、按钮、输入组件、`session_state` |
| REST API 调用      | HTTP 方法、请求参数、JSON 响应、异常处理       |
| Cookie / Session | 登录状态保存、身份信息传递                   |
| 前后端交互            | 页面状态与后端数据的同步                    |

---

### 任务分解[¶](https://dbg-course.github.io/python-docs/oj/project/step6/#_3 "Permanent link")

#### 任务 1：用户页面组[¶](https://dbg-course.github.io/python-docs/oj/project/step6/#1 "Permanent link")

实现与用户系统相关的页面。相关页面的内容至少包括：

- 用户注册；
- 用户登录和退出；
- 用户信息展示；
- 用户管理。

只有登录后用户才能进行题目提交、结果查询等操作，需安全地保存身份信息。前端需要实现登录表单，调用后端登录 API，完成用户身份认证。

- 实现建议：
- 可用 session_state 或本地文件存储 token。
- 登录失败时给出友好提示。

用户管理页面仅应向具备相应权限的管理员提供。页面应根据登录状态和用户角色展示可执行的操作，并正确处理未登录、权限不足、用户被禁用等情况。

#### 任务 2：题目页面组[¶](https://dbg-course.github.io/python-docs/oj/project/step6/#2 "Permanent link")

实现与题目管理相关的页面。相关页面的内容至少包括：

- 题目列表；
- 题目详情；
- 题目新增；
- 题目编辑；
- 题目删除。

题目表单应覆盖题目配置所需字段，并在提交前进行必要的格式检查。题目删除等受限操作应遵循后端权限要求。

#### 任务 3：评测与提交页面组[¶](https://dbg-course.github.io/python-docs/oj/project/step6/#3 "Permanent link")

实现与代码提交和评测结果查询相关的页面。相关页面的内容至少包括：

- 代码提交；
- 提交记录列表；
- 提交记录详情；
- 评测状态；
- 编译信息、运行结果和错误信息。

用户需要通过网页提交代码，并能实时查看评测状态和结果。前端需实现代码提交表单，调用后端提交 API，并展示评测结果。

- 实现建议：
- 使用 streamlit 的文本框、下拉框等组件收集题号、语言、代码内容。
- 调用后端提交 API，获取 submission_id。
- 轮询或手动查询 submission_id 的评测状态与结果，并展示。

提交后，页面应能够展示任务当前状态，并在评测完成后展示后端允许当前用户查看的结果。对于编译失败、运行错误、超时等情况，应提供明确的状态和错误提示。

#### 任务 4：前端与后端接口对接[¶](https://dbg-course.github.io/python-docs/oj/project/step6/#4 "Permanent link")

前后端分离架构下，所有数据流转均依赖 API，需保证参数、路径、状态码一致。应确保所有前端操作均通过 REST API 与后端交互，并严格遵循 [API 文档](https://dbg-course.github.io/python-docs/oj/api/)中的接口规范。

实现时应注意：

- 可封装统一的 API 调用函数，集中处理请求、身份信息和异常；
- 正确保存和传递登录会话，不得在页面代码中硬编码用户身份；
- 根据 HTTP 状态码和响应中的 `code` 字段展示成功或失败信息；
- 页面状态应与后端数据保持一致，不应仅在前端模拟操作结果。

---

### 评分细则[¶](https://dbg-course.github.io/python-docs/oj/project/step6/#_4 "Permanent link")

| 功能/接口     | 分值    | 评分说明                |
| --------- | ----- | ------------------- |
| 用户页面组     | 2     | 注册、登录/退出、用户信息、角色管理  |
| 题目页面组     | 1     | 题目列表、详情、新增、编辑、删除    |
| 评测与提交页面组  | 1     | 代码提交、记录查询、状态及运行信息展示 |
| 前端与后端接口对接 | 1     | API 调用、会话传递、响应与异常处理 |
| **小计**    | **5** |                     |

# AI 智能命题[¶](https://dbg-course.github.io/python-docs/oj/project/advance/#ai "Permanent link")

## 模块目标[¶](https://dbg-course.github.io/python-docs/oj/project/advance/#_1 "Permanent link")

程序设计训练（Python）课程的教师与助教需要根据每节课的教学内容设计配套 OJ 题目。命题过程通常包含知识点梳理、难度控制、题面编写、测试点构造以及题目测试等多个环节，需要投入较多时间。

本模块要求开发 AI 智能命题功能，辅助课程教师与助教完成每节课的 OJ 出题工作。命题人员可以输入题目必须覆盖的知识点、预期难度以及其他不同维度的要求；系统应能够据此独立完成题目设计、题目配置生成和测试点生成等多个环节，生成可用于 OJ 题目新增或编辑的完整结果。

本模块不限定具体的页面结构、任务流程或技术方案。实现可以围绕真实命题需求扩展检索、脚本执行、测试数据生成等能力。

---

## 前置知识要求[¶](https://dbg-course.github.io/python-docs/oj/project/advance/#_2 "Permanent link")

| 技术点       | 推荐学习内容                   |
| --------- | ------------------------ |
| 大语言模型 API | HTTP 请求、JSON 数据、模型输入与输出  |
| 模型配置      | 提供商 URL、模型名称、模型密钥        |
| 异步任务      | 后台任务、任务状态管理、异常处理         |
| 实时通信      | 流式响应、SSE、WebSocket 或状态轮询 |
| 用量统计      | 输入/输出 Token、模型价格与费用计算    |
| 配置安全      | API 密钥等敏感信息的保存与使用        |

上述内容不限定具体框架或实现协议，可参考程序设计训练（Rust）课程的 [Agent 架构](https://lab.cs.tsinghua.edu.cn/rust/projects/agent/agent-architecture/)了解相关概念。

---

## 基本功能要求[¶](https://dbg-course.github.io/python-docs/oj/project/advance/#_3 "Permanent link")

### R1. 出题交互界面[¶](https://dbg-course.github.io/python-docs/oj/project/advance/#r1 "Permanent link")

系统应提供可操作的 AI 智能命题界面。可以在基础模块的题目新增、题目编辑页面上扩展相关功能，也可以新增独立的 AI 智能命题页面。

界面应能够提交命题需求、展示处理状态和结果，并支持将所得内容用于后续的题目新增、审阅或修改。具体交互形式不作统一限制。

### R2. 可自定义模型配置[¶](https://dbg-course.github.io/python-docs/oj/project/advance/#r2 "Permanent link")

系统应支持配置以下模型信息：

- 提供商 URL；
- 模型名称；
- 模型密钥。

配置结果应实际应用于后续模型请求，不得将服务提供商、模型名称或模型密钥固定在程序代码中。模型密钥属于敏感信息，不应在日志、页面响应或错误信息中明文泄露。

### R3. 实时进度渲染和中断功能[¶](https://dbg-course.github.io/python-docs/oj/project/advance/#r3 "Permanent link")

AI 智能命题任务执行期间，界面应持续展示可观察的进度信息，不得仅在任务全部完成后返回最终结果。

系统应提供任务中断功能。中断操作应能够实际终止当前任务或阻止其继续执行，并在界面中明确展示任务已中断的状态。具体可采用流式响应、SSE、WebSocket、轮询等方式实现，不限定技术方案。

### R4. Token 用量与价格统计[¶](https://dbg-course.github.io/python-docs/oj/project/advance/#r4-token "Permanent link")

系统应统计模型调用产生的 Token 用量，并根据相应的模型价格计算调用费用。统计结果应在界面中清晰展示，至少能够反映当前任务的 Token 用量和费用。

若模型接口能够分别返回输入 Token 和输出 Token，应分别记录和展示。费用统计应说明所采用的计价依据；模型接口不提供完整用量信息时，应明确标注统计方式及其限制。

---

## 设计参考[¶](https://dbg-course.github.io/python-docs/oj/project/advance/#_4 "Permanent link")

以下示例用于说明本模块关注的设计方向，不限定具体实现方式，也不要求采用其中列出的全部功能。

### 正例[¶](https://dbg-course.github.io/python-docs/oj/project/advance/#_5 "Permanent link")

#### 示例一：通过多次迭代完善题目[¶](https://dbg-course.github.io/python-docs/oj/project/advance/#_6 "Permanent link")

允许 AI 按照相应改编要求修改已生成题目（或者其他已有题目）。例如，调整题目的背景与考察内容、修改/加强测试用例，或在保留原有考查目标的基础上设计新的题目情境。

该设计允许 AI 通过多次迭代逐渐完成命题任务，出题人可以根据当前结果继续提出修改要求。具体的迭代流程和交互形式应根据实际设计确定。

#### 示例二：通过工具扩展能力[¶](https://dbg-course.github.io/python-docs/oj/project/advance/#_7 "Permanent link")

为 AI 提供若干与命题场景相关的可调用工具。例如，通过 Web 检索相关题目设计资料，或通过服务器 CLI 编写并运行测试数据生成脚本。

该设计利用外部工具扩展模型能力，使系统能够完成单纯文本生成以外的命题任务。工具的选择、权限和执行范围应根据实际设计确定。

### 反例[¶](https://dbg-course.github.io/python-docs/oj/project/advance/#_8 "Permanent link")

#### 示例三：与基础功能相互割裂[¶](https://dbg-course.github.io/python-docs/oj/project/advance/#_9 "Permanent link")

仅在页面中添加“AI 出题”按钮，触发后返回一个包含题目信息的压缩包。

该功能与已有题目管理模块相互割裂，所得内容不能便捷地进入题目审阅、编辑或维护流程。

#### 示例四：未能有效辅助命题[¶](https://dbg-course.github.io/python-docs/oj/project/advance/#_10 "Permanent link")

AI 功能只能完成单一的文本生成，或者所得题目与输入的知识点、约束条件明显无关。

该功能未能有效处理所声明的命题需求，出题的主要工作仍需人工重新完成。

---

## 评分标准[¶](https://dbg-course.github.io/python-docs/oj/project/advance/#_11 "Permanent link")

本模块满分为 10 分。

| 评分项               | 分值     | 评分内容                                                 |
| ----------------- | ------ | ---------------------------------------------------- |
| R1. 出题交互界面        | 1      | 是否提供完整、可操作的 AI 智能命题界面；是否能够提交需求、展示结果，并与题目新增或修改等操作合理衔接 |
| R2. 可自定义模型配置      | 1      | 是否支持配置提供商 URL、模型名称和模型密钥；配置是否实际应用于模型请求                |
| R3. 实时进度渲染和中断功能   | 1      | 是否能够实时展示任务进度；是否能够有效中断正在执行的任务，并正确反馈任务状态               |
| R4. Token 用量与价格统计 | 1      | 是否能够统计并清晰展示 Token 用量和模型调用费用；费用计算依据是否明确               |
| 题目合理性             | 2      | AI 智能命题生成的题目是否满足真实课程要求，是否符合输入的知识点、难度及其他命题要求          |
| 测试用例有效性           | 2      | 测试用例是否覆盖不同边界条件，数据规模和构造是否能有效区分用户提交的不同时间复杂度算法          |
| 功能易用性             | 2      | 交互流程是否符合使用习惯，操作是否便捷，功能状态和结果展示是否清晰                    |
| **合计**            | **10** |                                                      |

# 

# 评分标准[¶](https://dbg-course.github.io/python-docs/oj/requirements/#_1 "Permanent link")

共50分，其中实验功能验收占40分，代码规范5分，实验报告5分。本次作业最终会按照比例缩放到总评30%。

## 时间节点[¶](https://dbg-course.github.io/python-docs/oj/requirements/#_2 "Permanent link")

1. OJ 系统的功能实现，在**9月10日（周四）**由助教线下验收（验收形式后续通知，参考第一次大作业）。
2. 助教会为每位同学创建好仓库。所有源代码需要在**9月10日（周四）课前完成**，需在网络学堂提交最后一次 git commit 号。
3. 实验报告在 **9月10日（周四）晚上23:59** 在网络学堂截止提交。
4. **作业原则上不接受补交。**需要有足够的原因（如医学证明）才能接受补交，且每人仅有一次补交机会。

**逾期未参加验收，实验功能部分记零分。请同学们务必按时参加验收！如遇到极特殊情况，请及时联系助教。**

---

## 实验功能[¶](https://dbg-course.github.io/python-docs/oj/requirements/#_3 "Permanent link")

以下评分标准均建立在正确使用fastapi的异步编程接口上，不使用异步编程的无法拿到本次作业分数。

### 基础模块（共 30 分）[¶](https://dbg-course.github.io/python-docs/oj/requirements/#30 "Permanent link")

| 模块          | 主要评分点                | 分值  |
| ----------- | -------------------- | --- |
| Step 1 题目管理 | 题目配置加载、校验与增删改查       | 5   |
| Step 2 评测控制 | 程序执行与资源限制            | 5   |
| Step 3 评测管理 | 提交记录查询、状态管理与重新评测     | 5   |
| Step 4 用户管理 | 用户注册、登录与权限管理         | 5   |
| Step 5 评测日志 | 测试点明细、可见性与访问审计       | 5   |
| Step 6 前端交互 | 用户、题目、评测提交页面及前后端接口对接 | 5   |

### 进阶模块（共 10 分）[¶](https://dbg-course.github.io/python-docs/oj/requirements/#10 "Permanent link")

| 模块      | 主要评分点                     | 分值  |
| ------- | ------------------------- | --- |
| AI 智能命题 | R1–R4、题目合理性、测试用例有效性与功能易用性 | 10  |

---

### 代码规范（5分）[¶](https://dbg-course.github.io/python-docs/oj/requirements/#5 "Permanent link")

参考第一次爬虫大作业，另外，本次对git提交会做更详尽的检查。请同学们正确使用git，**避免将大文件提交到git，这将会是扣分项**。

**Git 提交规范**：要求尽量按照 [Conventional Commits](https://www.conventionalcommits.org/zh-hans/v1.0.0/) 规范编写提交信息，不符合规范的提交将酌情扣分。提交信息应包含类型（如 feat、fix、docs 等）和简洁的描述。

---

### 实验报告（5分）[¶](https://dbg-course.github.io/python-docs/oj/requirements/#5_1 "Permanent link")

| 评分点     | 分值  | 达标标准                                 |
| ------- | --- | ------------------------------------ |
| 系统功能与设计 | 2   | 介绍系统架构、主要功能、技术选型、模块划分                |
| 关键实现与难点 | 2   | 说明关键技术实现、遇到的难点与解决方案                  |
| 成果展示    | 1   | 展示系统效果、边界测试结果                        |
| AI使用说明  | 0   | 介绍 AI 使用的工具链、工作流和 Vibe Coding 的代码比例等 |
| 总结与建议   | 0   | 反思收获、改进建议、时间投入等                      |

- 报告建议为PDF，结构清晰，图文并茂。

---

## 扣分项（视情节严重程度）[¶](https://dbg-course.github.io/python-docs/oj/requirements/#_4 "Permanent link")

> 本次作业允许使用 Vibe Coding，但这并不意味着可以忽视对代码架构和基本原理的理解。我们鼓励同学们在掌握基本原理和代码结构的基础上，借助 Vibe Coding 完成更现代化、更完整的作业。此外，对于使用 Vibe Coding 的同学，需要在报告中提交一份 AI 使用说明。

- 抄袭/作弊，0分处理。
- 未按时参加验收的，功能部分记零分。
- 代码/报告严重缺失，或未按要求提交，酌情扣分。
- 代码/报告与演示内容不符，酌情扣分。
