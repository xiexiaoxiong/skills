---
name: evidence-collection
description: 输入权利人和疑似侵权链接后，按用户修改的61项五维重案证据方法先执行全部可运行调查，再生成逐行结论、表内小图和下一步重点的紧凑Word报告。默认调查被告商品、店铺、经营主体和关联主体；仅2-3-1至2-3-5可独立调查原告知名度。适用于商标、著作权、专利、包装装潢及不正当竞争重案的跨平台检索、企查查/工商/司法/监管调查、登录协作、证据固定和行动清单。
---

# 重案证据调查执行器

## 核心原则

先调查，后报告。不得先生成61行空清单再零散补查。

1. 以用户当前DOCX提取的61项为唯一任务集合；拒绝旧矩阵中的B、T、Q和`1-1-1A`。
2. 先从疑似侵权链接提取被告商品、品牌、SKU、店铺和平台展示主体。除`2-3-1`至`2-3-5`外，所有调查从被告种子出发。
3. 编译全部动作队列并持续执行所有`READY`动作。一个动作报错、登录受阻或需人工，不得让其他可执行动作停止。
4. 只有队列达到`QUIESCENT`，或用户明确要求部分输出，才生成正式用户报告。
5. 报告必须按“项目经理首页面板 -> 待办 -> 61行明细”的顺序给出实际结果、代表性小图和可执行工作单；完整动作日志、原图和原始JSON留在案件证据目录。
6. 用户只负责用手机扫描当前受控浏览器页面显示的登录二维码，并在完成后回复“已登录”。不得要求用户截图、上传二维码图片、输入或提供密码、验证码、Cookie、Local Storage或任何浏览器认证材料。
7. 小红书和微博调查必须先分别调用只读平台MCP `xiaohongshu`、`weibo`发现候选账号/笔记/帖子，再由`chrome-devtools`打开候选规范页、核对页面并由AI截图；只有无需登录的公开页在Chrome不可用时才可回退`playwright`。禁止调用AgentKey或任何AgentKey后端，禁止用通用搜索替代平台MCP。

## 运行入口

案件初始化和被告种子登记仍使用：

```bash
python3 scripts/checklist_case.py init --rights-holder "权利人" --url "侵权链接" --output-dir CASE_DIR
python3 scripts/checklist_case.py set-seed --case-dir CASE_DIR --file defendant_seed.json
```

随后必须使用运行队列，不得直接`fill`：

```bash
python3 scripts/run_case.py compile --case-dir CASE_DIR --run-dir CASE_DIR/work/run
python3 scripts/run_case.py next --case-dir CASE_DIR --run-dir CASE_DIR/work/run
python3 scripts/run_case.py commit --case-dir CASE_DIR --run-dir CASE_DIR/work/run --file action-result.json
python3 scripts/run_case.py status --case-dir CASE_DIR --run-dir CASE_DIR/work/run
```

主代理循环执行`next -> 调用真实工具 -> commit`，直到返回`QUIESCENT`、`WAITING_LOGIN`或`WAITING_MANUAL`。本地脚本只负责确定性调度，不得伪装已调用Browser、企查查、搜索或官方数据库。

运行状态和动作结构见[run-state.schema.json](references/run-state.schema.json)、[action-run.schema.json](references/action-run.schema.json)和[run-matrix-61.json](references/run-matrix-61.json)。

## 调查波次

1. `W0 SEED`：打开侵权链接，固定页面并提取完整被告种子。登录受阻时仅暂停依赖该页面的动作。
2. `W1 PRODUCT`：执行被告商品、SKU、店铺的站内和跨平台调查；并行执行五项原告知名度白名单。
3. `W2 ENTITY`：执行企查查MCP、国家企业信用信息、公示许可和关联主体调查。平台vendor名称精确命中企业时仍只写主体线索，店铺同一性待执照、订单、发票或平台披露核验。
4. `W3 OFFICIAL`：执行法院、监管、CNIPA、招投标、环评、年报、海关、执行和处罚等全部可用公开动作。
5. `W4 DERIVED`：执行比较、贡献率、故意和赔偿等依赖项。比较行必须先有被告材料；原告材料只能成对比较。
6. `W5 PARKED`：跑尽其他`READY`动作后，再集中处理登录和人工事项，形成明确工作单。

半自动项目也必须先运行公开子动作；只有确实需要测购、公证、专家、平台披露或法院调取的部分才能记为`WAITING_MANUAL`。

## 工具选择

- `BROWSER`：动态网页、登录态页面、页面截图、可见字段和最终URL。
- `QCC_MCP`：工商登记、股权、实控人、主要人员、关联任职、许可、知识产权、经营和风险。可通过已配置MCP或`qcc-agent-cli`调用，原始JSON必须落盘。
- `WEB_SEARCH`：精确查询和跨平台线索；搜索摘要仅为线索，必须打开结果页才能升级事实等级。
- `OFFICIAL_DB`：国家企业信用信息、药监、CNIPA、法院、执行、政府采购、招投标、海关等官方来源。
- `HTTP_CAPTURE`：无需登录的静态页面和文件。

### 小红书/微博强制工具链

- `xiaohongshu`、`weibo`仅用于只读站内发现；不得点赞、关注、评论、发布、收藏、私信或修改任何平台数据。
- MCP命中只能生成候选，不能直接形成`FOUND`事实。候选必须由`chrome-devtools`打开规范账号页、笔记页或帖子页，记录跳转后的最终URL、访问时间和非秘密页面标识，并由AI保存截图。
- `playwright`仅可在Chrome不可用时验证无需登录的公开页；不得导入、复制或重建Chrome登录态，不得用于绕过二维码登录。
- 登录时必须在当前受控Chrome会话展示平台二维码，由用户自行扫码；用户回复“已登录”后，AI在同一会话核验并继续。用户截图、二维码图片或认证材料永远不是输入。
- 禁止AgentKey：不得调用AgentKey skill、provider、代理API或任何AgentKey后端；若平台MCP不可用，应记录运行失败或待重试，不得改走AgentKey。
- 可点击来源只能使用浏览器已验证的规范页URL。搜索页、搜索摘要、短链、分享跳转页和MCP返回的未打开URL不得进入报告超链接。
- `MANUAL`：测购、公证、问卷、专家、平台披露或法院调查令。

所有动作必须记录`executor`、`subject_role`、`seed_refs`、查询词/URL、开始结束时间、outcome、原始返回、截图、来源、错误码、重试和下一步。

## 登录协作

遵循[login-coordination-protocol.md](references/login-coordination-protocol.md)。skill只发出宿主无关的`LOGIN_REQUIRED`事件：

- 有UI的宿主把事件映射为弹窗、按钮或浏览器侧栏。
- 无UI但有共享浏览器时，用纯文本提示用户在当前受控会话登录并回复“已登录”。
- 无共享浏览器时返回`HOST_NO_BROWSER`，不得让用户在隔离浏览器登录后假装可复用会话。
- 用户确认后，Agent必须在原`session_ref`中验证成功，才能发出`RESUME`。
- 认证秘密不得写入案件文件或日志。

协议CLI：

```bash
python3 scripts/login_protocol.py required --case-dir CASE_DIR --provider jd --origin https://jd.com --target-url URL --session-ref OPAQUE --checkpoint jd.seed --browser-control --session-persistence --ui-prompt
python3 scripts/login_protocol.py confirmed --case-dir CASE_DIR --correlation-id ID --source USER_TEXT
python3 scripts/login_protocol.py resume --case-dir CASE_DIR --correlation-id ID --session-ref OPAQUE --checkpoint jd.seed --session-verified --verification-signal account-marker
python3 scripts/run_case.py resume --case-dir CASE_DIR --run-dir CASE_DIR/work/run --action-id ACTION_ID --kind LOGIN_REQUIRED --correlation-id ID --session-ref OPAQUE --checkpoint jd.seed --verification-signal account-marker
```

## 结果判定

`execution_state`与`result_status`必须分开：

- 执行态：`PLANNED`、`WAITING_DEPENDENCY`、`READY`、`RUNNING`、`WAITING_LOGIN`、`WAITING_MANUAL`、`RETRYABLE`、`TERMINAL`。
- 结论态：`COMPLETE_VERIFIED`、`PARTIAL_VERIFIED`、`LEAD_ONLY`、`NOT_FOUND`、`BLOCKED`、`NEEDS_HUMAN`、`NOT_APPLICABLE`、`CONFLICT`、`ERROR`。

`NOT_FOUND`仅可在该动作的completion policy所列范围全部执行后使用，且必须写成“本次检索未发现”，不得解释为事实不存在。技术错误记`ERROR`并继续队列。登录和人工项只能park，不能伪装终态完成。

主体路由和搜索纪律见[subject-routing.md](references/subject-routing.md)与[search-playbook.md](references/search-playbook.md)。

## 项目经理执行版报告（强制合同）

默认用户报告必须使用`scripts/render_pm_report.py`生成，并以[pm-report-summary.schema.json](references/pm-report-summary.schema.json)约束报告汇总输入。不得改用旧`render_compact_inline.py`、手工拼接Word或其他渲染入口。旧`fill/validate`仅用于生成保真审计底稿，不是默认用户报告；不得把长动作日志塞入用户版Word。

正式报告继续读取`run_state.json`和`action_queue.json`并受运行队列门禁约束：只要仍有`READY`或`RUNNING`动作就必须拒绝输出，`RETRYABLE`按尚可执行动作同样拒绝输出。仅当用户明确要求阶段性报告时才允许部分输出，并在首页醒目标记“阶段性报告”及尚未执行范围；部分输出也不得把可继续运行的动作伪装成已完成。

报告阅读顺序固定且不可插入其他一级章节：

1. **项目经理首页面板**：先显示总任务数61、`AI已查看`数量、`项目经理待处理`数量、三类待处理数量、关键线索和当前阻塞。
2. **待办**：集中列出全部项目经理待处理项，按优先级排序，并给出责任角色和可直接执行的工作单。
3. **61行明细**：按原编号完整展示每一行的主状态、已查/未查范围、结果、来源、附图和下一步。

报告一级分类只能是`AI已查看`和`项目经理待处理`，不得再以平台、证据类型、优先级或内部执行态作为并列一级分类。内部`execution_state`和`result_status`继续保留在案件数据中，但用户可见主状态只能使用以下五态，文字和分隔符不得改写：

- `已查看｜有线索`
- `已查看｜未发现`
- `待处理｜需登录`
- `待处理｜需人工`
- `待处理｜运行失败`

将已取得事实、可核验材料或仅够继续追查的线索归为`已查看｜有线索`；仅在completion policy规定的平台和查询范围全部完成后，才归为`已查看｜未发现`。将登录阻断归为`待处理｜需登录`，将测购、公证、专家、平台披露、法院调取及其他线下操作归为`待处理｜需人工`，将工具报错、超时、解析失败、网络失败或重试耗尽归为`待处理｜运行失败`。

同一行只要仍有登录、人工或运行失败部分，主状态必须归入对应的`项目经理待处理`五态，不得用已完成子动作覆盖；同时在待办和61行明细中分别写明`已查：`具体平台、关键词和所得结果，以及`未查：`具体平台、动作和阻断原因。存在多种待处理原因时，按`需登录 -> 运行失败 -> 需人工`选择主状态，并保留其他未查原因。

不得把失败、超时、登录受阻、未执行或证据不足写成“未发现”。`已查看｜未发现`必须限定检索边界，至少写明“在【平台/数据库】以【关键词】检索，本次检索未发现【目标】”，并紧接“该结论仅限上述平台和关键词，不代表相关事实绝对不存在”。

每个`项目经理待处理`行必须同时写全以下三项，不得使用“后续核实”“建议补充”等空泛表述：

- `去哪做：`具体平台、数据库、页面入口、线下地点或受理机关。
- `怎么做：`登录、查询、筛选、测购、公证、申请披露、申请调查令或修复重跑的具体步骤。
- `保存什么：`应固定的截图、录屏、网页存证、订单、发票、样品、回函、原始文件、哈希或失败日志。

代表性缩略图放在对应61行结果区域，每行最多两张，禁止浮动图片、文本框、固定图片行高或单独逐行截图附录。按原图SHA-256去重；重复证据在其他行内部引用主行。无图时显示明确原因标签，不留空白图片区。

生成前先用`references/pm-report-summary.schema.json`校验汇总输入，再由`scripts/render_pm_report.py`一次生成报告并完成结构与视觉校验。校验通过后的DOCX视为不可变产物，禁止再用`python-docx`、解压改XML、LibreOffice或其他方式postprocess；如发现问题，必须修改源数据或渲染逻辑、重新生成并重新校验，不得在已校验文件上补丁修改。

## 交付门槛

- 恰好61个任务，所有可执行动作已成为终态或明确park。
- 队列无遗漏的`READY`、`RUNNING`或可重试动作。
- 报告严格按“项目经理首页面板 -> 待办 -> 61行明细”排列，一级分类仅有`AI已查看`和`项目经理待处理`，用户可见主状态仅使用固定五态。
- 每行都有结果摘要、平台状态和下一步重点；混合行归入待处理并同时列明`已查`和`未查`。
- 每个待处理行都写明`去哪做`、`怎么做`和`保存什么`；运行失败不得降格为未发现，未发现必须限定平台和关键词并声明不代表绝对不存在。
- 已核验事实都有真实来源；无结果、受阻、人工和工具错误均有边界说明。
- 图像只在结果列内，每行最多两张，来源/原图可点击且本地文件存在。
- 汇总输入通过`references/pm-report-summary.schema.json`校验，报告由`scripts/render_pm_report.py`生成并完成结构校验和视觉渲染；不达标时从源数据或渲染逻辑重新生成，校验后不得postprocess。
