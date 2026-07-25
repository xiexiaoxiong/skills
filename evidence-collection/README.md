# evidence-collection

重案证据清单 Skill（原 `heavy-case-evidence-builder`）的本地部署与安装说明。

## 1) 安装到本地仓库

```bash
cd /Users/xiexiaoxiong/Documents/skills
bash install/install.sh install evidence-collection
```

> 如果当前仓库没有 `install/install.sh`，请先按你们当前仓库里的安装脚本执行替代命令。

## 2) 运行依赖（一次性安装）

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r skills/evidence-collection/requirements.txt
```

可选/外部依赖（按你们环境实际）：
- Chrome（用于截图核验）
- qcc、xiaohongshu、weibo、chrome-devtools、playwright MCP 配置

