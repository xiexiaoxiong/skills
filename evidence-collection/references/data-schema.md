# 案件数据结构

## 运行态文件

案件目录必须新增：

- `run_state.json`：run_id、case_state、ready_count、waiting_login、waiting_manual、terminal_count、started_at、updated_at、pause_reason。
- `work/action_queue.json`：61项任务编译得到的全部动作规格和依赖。
- `action_runs.jsonl`：每次真实工具动作的原子记录。
- `work/login/state.json`和`work/login/events.jsonl`：宿主无关的登录协作状态；不得包含认证秘密。

`row_results`需同时记录`execution_state`、`result_status`、planned/executed/terminal动作数、scope_exhausted、pause_reasons、compact_result、next_step_focus。

附件需记录原图和缩略图路径及SHA-256、source_url、primary_row_id、duplicate_group_id、display_priority。默认报告每行最多展示两张缩略图，重复原图只在主行显示。

## case.json

必需字段：

- schema_version
- case_id
- created_at、timezone
- rights_holder.raw_input
- suspected_infringement_url
- defendant_seed.status、defendant_seed.source_url、defendant_seed.extracted_at
- defendant_seed.product_full_name、product_short_name、brand、model_sku、platform_item_id
- defendant_seed.shop_account、shop_account_id、seller_display_name、business_entity
- defendant_seed.manufacturer_registrant、address、phone
- defendant_seed.seed_refs：每个非空种子字段对应的页面或证据引用
- case_name
- plaintiff、defendants、cause、court、case_number（未知可为空）
- disclaimer

## search_tasks.json

每项任务：

- id：与 evidence-matrix.json 一致
- section、dimension、title、priority、automation
- required_subjects：至少包含DEFENDANT；仅2-3-1至2-3-5使用PLAINTIFF_REPUTATION白名单
- target_url、queries
- status：PENDING、IN_PROGRESS、DONE、NEEDS_HUMAN、NOT_FOUND、BLOCKED、NOT_APPLICABLE
- result_urls、notes、updated_at

不得用 NOT_FOUND 代替不存在的事实判断。只有完成案件类型与事实判断后，才能把确实无关的方向标为 NOT_APPLICABLE，并写明理由；不得为消除警告而批量关闭。

`defendant_seed.status` 取值为READY、PARTIAL或BLOCKED。除2-3-1至2-3-5外，任务执行前必须取得至少一个可核验被告种子；商品名未提取时优先登录重试，仍失败则保留BLOCKED，不得改用原告产品种子。

## 行级动作主体

每条action必需字段：

- subject_role：DEFENDANT、PLAINTIFF_REPUTATION、RIGHTS_BASIS、COMPARISON、NEUTRAL或MANUAL。
- seed_refs：非空数组，指向本次动作实际使用的种子或材料引用。
- platform、query或url、accessed_at、outcome及必要的note。

`PLAINTIFF_REPUTATION` 仅允许用于2-3-1至2-3-5。`COMPARISON` 必须在同一行已有在先DEFENDANT动作，且其 `seed_refs` 同时指向被告材料和固定比较材料。`RIGHTS_BASIS` 只查询注册号、权利状态及授权链，不得替代被告调查。

## evidence_manifest.json

每件证据：

- id：E001 起连续
- group_id：1至5
- title、source_org、source_type
- url、final_url、accessed_at、timezone
- acquisition_method
- fact_status：VERIFIED、STRONG_INFERENCE、LEAD、NEEDS_HUMAN、NOT_FOUND、BLOCKED、LEGAL_ASSESSMENT
- litigation_status：PUBLIC_CAPTURE、FIXED、NEEDS_NOTARIZATION、NEEDS_DISCLOSURE、NEEDS_COURT_ORDER
- file_path、sha256、size_bytes、mime_type、page_range
- proof_points
- limitations
- linked_task_ids
- derived_files
- contains_personal_data、privacy_redactions
- tool_version

原始件放 evidence/original，元数据放 evidence/metadata，派生件放 evidence/derived。派生件不得覆盖原始件。

## 日志

access_log.jsonl 每行记录：

- timestamp、url、action、status
- final_url、http_status、content_type、bytes、sha256
- error、evidence_id

search_log.jsonl 每行记录：

- timestamp、task_id、query、source、subject_role、seed_refs
- result_url、result_status、notes

所有时间使用带时区 ISO 8601。哈希使用 SHA-256。
