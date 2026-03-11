# OrbLiteAgent

OrbLiteAgent 是基于 Streamlit 构建的轻量级智能体应用，面向交互式实验与原型验证，提供可视化界面用于对话交互与任务编排。

## 功能特性

- 支持交互式对话与任务执行
- 支持模型与工具的可配置接入
- 提供运行日志与结果展示
- 采用 Streamlit 构建的可迭代界面

## 界面预览

应用界面截图如下：

![界面预览 1](docs/example_01.png)

![界面预览 2](docs/example_02.png)

## 快速开始

### 环境要求

- Python 3.10 及以上版本

### 安装依赖

推荐使用 `uv` 安装依赖：

```bash
uv sync
```

或使用 `pip` 安装：

```bash
pip install -e .
```

### 运行应用

```bash
streamlit run streamlit_app.py
```

启动后，请根据终端提示在浏览器中访问对应地址。

## 配置说明

- `config/config.toml`：应用配置文件
- `config/mcp.json`：MCP 相关配置文件

## 目录结构

```
.
├── config/           # 配置文件
├── docs/             # 文档与截图
├── orblite/          # 核心代码
├── streamlit_app.py  # Streamlit 入口
├── stepup.py         # 启动/辅助脚本
├── pyproject.toml    # 项目依赖与配置
└── uv.lock           # 依赖锁定文件
```
