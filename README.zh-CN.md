# plugin-creator

一个用于**创建、校验、打包、版本管理 Claude Code 插件**的 Claude Code **skill**；同时还能针对一堆零散的 skill 给出"该怎么打包成插件"的建议。

这个 skill 是 [`skill-creator`](../skill-creator/) 在插件层面的对应物：`skill-creator` 产出单个 `SKILL.md`（外加配套文件），`plugin-creator` 则产出一个由 `.claude-plugin/plugin.json` manifest 串起来的**组件包**（skills / agents / hooks / MCP servers / LSP servers / monitors / themes），可直接 `claude plugin install` 安装。

权威参考：<https://code.claude.com/docs/en/plugins-reference>。

---

## 这个 skill 能做什么

- **Scaffold（脚手架）**：按需生成插件目录树，只创建你点名的组件。
- **Author（编写）**：内联编写、用 subagent 并行编写，或把单个 skill 委托给 `skill-creator`。
- **Validate（校验）**：根据官方 schema 校验 manifest 与每一个组件（28 种 hook 事件、MCP/LSP 形状、`${CLAUDE_PLUGIN_ROOT}` 引号检查、JSON 卫生、marketplace 严格模式 等等）。
- **Bump（版本递增）**：按 SemVer 递增（`major` / `minor` / `patch` / `set:X.Y.Z`）。
- **Package（打包）**：打包成可分发的 `.zip`，打包前会强制走一次校验。
- **Recommend bundles（建议分组）**：给定一个装着零散 skill 的目录，建议哪些合并成一个插件、哪些单独成插件。
- **Review（评审）**：静态 HTML 总览、manifest 评审 subagent、设计层面的 plugin-analyzer。

---

## 何时调用

当用户在做 Claude Code 插件相关的事情时，这个 skill 会被自动召回。具体来说，下列说法应当触发它：

- "帮我做一个 X 插件" / "create a plugin for X"
- "帮我校验这个插件 / 修一下我的 manifest"
- "把这堆 skill 打包成一个插件"
- "升一下版本号" / "打包发到 marketplace"
- "我有一堆 skill，应该怎么分组成插件？"
- "给我的插件加一个 hook / MCP server / LSP server / monitor / theme"

---

## 目录结构

```
plugin-creator/
├── SKILL.md                       # Claude 真正读取的主提示词
├── README.md                      # 英文版说明
├── README.zh-CN.md                # 本文件（简体中文）
├── LICENSE.txt
│
├── agents/                        # subagent 提示词，可并行
│   ├── component-author.md        # 根据一行规格写出单个组件
│   ├── manifest-reviewer.md       # 按 schema + marketplace 规则 lint plugin.json
│   ├── plugin-analyzer.md         # 整插件层面的设计评审
│   └── bundle-advisor.md          # 用 role / job-to-be-done 测试细化启发式聚类
│
├── scripts/                       # 确定性 Python 工具（不调用 LLM）
│   ├── __init__.py
│   ├── utils.py                   # Issue/Report 数据类、frontmatter 解析等
│   ├── scaffold_plugin.py         # 生成新插件目录树
│   ├── add_component.py           # 加单个组件（skill/command/agent/hook/mcp/lsp/monitor/theme）
│   ├── validate_plugin.py         # 完整校验，支持 --marketplace 严格模式与 --json 输出
│   ├── bump_version.py            # SemVer 递增并预填 CHANGELOG
│   ├── package_plugin.py          # 先校验后打包
│   ├── generate_review.py         # 生成静态 HTML 总览
│   └── recommend_bundles.py       # 对一堆零散 skill 做 Jaccard 启发式聚类
│
└── references/                    # 渐进式披露的深度资料
    ├── manifest_schema.md         # plugin.json 的全部字段
    ├── components.md              # 各类组件的标准布局与字段约束
    ├── hooks_events.md            # 全部 28 个 hook 事件
    ├── cli_commands.md            # `claude plugin ...` 命令参考
    ├── version_management.md      # SemVer 规则 + marketplace tag 策略
    └── bundling_heuristics.md     # recommend_bundles.py 的聚类规则
```

---

## 安装

### 方式一：克隆到用户级 skills 目录

```bash
git clone https://github.com/leoriczhang/plugin-creator.git ~/.claude/skills/plugin-creator
```

### 方式二：克隆到项目级 skills 目录

```bash
git clone https://github.com/leoriczhang/plugin-creator.git .claude/skills/plugin-creator
```

### 方式三：作为 Claude Code 插件安装

```bash
claude plugin install https://github.com/leoriczhang/plugin-creator
```

零依赖 —— 所有脚本均为纯 Python 3.8+，无需任何第三方包。

## 快速上手

装好之后，可以这样问 Claude：

- "做一个叫 `pdf-tools` 的插件，包含一个 skill 和一个 MCP server。"
- "校验一下 `~/work/legal-pack/` 里的插件。"
- "我在 `~/work/skills-standalone/` 里有一堆 skill，帮我看看怎么分组成插件。"
- "把这个插件升一个 minor 版本然后打包。"

Claude 会先读 `SKILL.md`，规划任务，再调用相应的脚本和 subagent。

---

## 两阶段的 Bundle 推荐器

这是这次给 plugin-creator 增加的核心新能力，专为"手里有一堆零散 skill"的用户设计。

**Stage 1 —— 启发式聚类（确定性、零依赖）：**

```bash
python -m scripts.recommend_bundles <skills 目录> \
  --threshold 0.18 \
  --min-bundle 2 \
  --output-md /tmp/bundle_report.md \
  --output-json /tmp/bundle_report.json
```

脚本会对每个 `SKILL.md` 的 `name` + `description` 分词（权重 2 倍），去停用词和管道词（"skill / claude / invoke" 等），算两两 Jaccard 相似度，把超阈值的边连起来，连通分量就是候选 **bundle**。落单的就是 **singleton**，并附一句话说明为什么没聚到一起。

阈值标定表（详细解释见 [references/bundling_heuristics.md](references/bundling_heuristics.md)）：

| Jaccard | 含义 |
|---|---|
| ≥ 0.40 | 高置信度，可以直接打包 |
| 0.20 – 0.40 | 大概率相关，建议复核 |
| 0.12 – 0.20 | 需要人工 / LLM 复核 |
| < 0.08 | 大概率无关 |

**Stage 2 —— 定性复核（LLM subagent）：**

把 stage 1 的 JSON 喂给 `bundle-advisor`。它会真的打开每个 `SKILL.md`，跑四个连贯性测试（角色重叠、job-to-be-done、cold-start、触发上下文），然后产出一份结构化方案：

- 对每个候选 bundle：`accept` / `split` / `merge` / `reject`，并给出一个能反映**真实角色 + 工作**的重命名插件名。
- 对每个 singleton：`solo-plugin` / `merge-into:<bundle>` / `drop`。
- 每条决策都附短理由。

最后按方案执行：scaffold 每个 accept 的 bundle、把成员 skill 搬进 `skills/`、校验、把版本设到 `0.1.0`、打包。

---

## 其他脚本一览

| 脚本 | 作用 |
|---|---|
| `scaffold_plugin.py` | 创建插件目录树（`.claude-plugin/plugin.json` + 你点名的组件目录） |
| `add_component.py` | 加单个组件，自动写好合规的桩；必要时同步更新 manifest |
| `validate_plugin.py` | schema + 路径 + JSON 卫生检查；`--marketplace` 进入严格模式；`--json` 机器可读 |
| `bump_version.py` | SemVer 递增（`major` / `minor` / `patch` / `set:X.Y.Z`），并预填 CHANGELOG |
| `package_plugin.py` | 先校验后打包 |
| `generate_review.py` | 生成单页 HTML 总览（manifest + 组件 + 校验结果） |
| `recommend_bundles.py` | 对一堆零散 skill 做启发式聚类 |

所有脚本都是纯 Python 3.8+，**不依赖任何第三方包** —— 连 `utils.py` 里都手写了一份最小化 YAML 解析器，避免引入 PyYAML。

---

## Subagent 列表

| Agent | 何时使用 |
|---|---|
| [`component-author`](agents/component-author.md) | 想并行起草单个组件（skill / agent / hook / mcp / lsp / monitor / theme） |
| [`manifest-reviewer`](agents/manifest-reviewer.md) | 想对 `.claude-plugin/plugin.json` 做结构化 lint（schema + 命名 + marketplace 就绪度） |
| [`plugin-analyzer`](agents/plugin-analyzer.md) | 想要设计层面的观察：缺失的互补组件、冗余 skill、hook 覆盖盲区、推荐的 SemVer 升级幅度 |
| [`bundle-advisor`](agents/bundle-advisor.md) | 手里有一堆零散 skill，想要一份"哪些合并、合并叫什么、哪些单独成插件"的方案 |

标准的 spawn 模式：

```
Read <plugin-creator-path>/agents/<agent-name>.md and follow it.
Inputs:
- <agent 特定输入>
Output to: <path>
```

Agent 返回 JSON；agent 跑完后读取那份 JSON，再按结构化结果继续动作。

---

## 设计要点

- **渐进式披露**：自动加载时 Claude 只读 `SKILL.md` 一份提示词。`references/` 里的深度资料只在涉及到对应决策时才加载。这样 token 成本低，skill 还能扩展。
- **启发式 + LLM，而不是只有 LLM**：打包、校验、版本递增、Bundle 启发式聚类都用确定性脚本完成，相同输入永远得到相同输出。LLM 只用来做真正定性的工作（写组件、复核 bundle、设计评审）。
- **零第三方依赖**：所有脚本都能在干净的 Python 3.8+ 上直接跑。目录扔到任何位置都能工作。
- **校验器作为质量门**：`package_plugin.py` 会先调 `validate_plugin.py`，校验失败就拒绝打包。这样"看起来 OK，发吧"的判断才可信。

---

## 参考资料

- Plugins reference：<https://code.claude.com/docs/en/plugins-reference>
- Plugin marketplaces：<https://code.claude.com/docs/en/plugin-marketplaces>
- 姊妹 skill：[`skill-creator`](../skill-creator/) —— 单 skill（不组装成 plugin）的场景

---

## 许可

MIT —— 详见 [LICENSE.txt](LICENSE.txt)。
