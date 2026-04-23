# 岗位配置文档

## 概述

本目录包含AI-HR面试系统的岗位配置文件。每个岗位配置定义了该岗位的能力模型、面试策略、题目生成规则等。

## 目录结构

```
role_configs/
├── _base.yaml              # 基础配置（所有岗位继承）
├── schema.json             # JSON Schema验证规范
├── tech/                   # 技术岗位族
│   ├── backend.yaml
│   ├── frontend.yaml
│   ├── fullstack.yaml
│   ├── mobile.yaml
│   ├── ai_ml.yaml
│   ├── qa.yaml
│   └── sre.yaml
├── product/                # 产品岗位族
│   ├── product_manager.yaml
│   ├── product_owner.yaml
│   └── technical_pm.yaml
├── design/                 # 设计岗位族
│   ├── ui_designer.yaml
│   ├── ux_designer.yaml
│   └── interaction_designer.yaml
├── government/             # 政府/行政岗位族
│   └── civil_servant.yaml
└── business/               # 商业岗位族
    ├── sales.yaml
    ├── marketing.yaml
    └── operations.yaml
```

## 配置文件格式

所有配置文件使用YAML格式，必须符合`schema.json`定义的规范。

### 基本结构

```yaml
# 配置版本
version: "1.0"

# 继承基础配置（可选）
extends: "_base"

# 岗位信息
role:
  id: "backend_engineer"
  family: "engineering"
  display_name:
    zh: "后端工程师"
    en: "Backend Engineer"
  match_rules:
    keywords: ["后端", "backend"]
    skills: ["java", "python"]

# 通用能力
universal_competencies:
  ownership:
    weight: 0.15
    description: "主人翁意识"
    evidence_types: ["initiative"]

# 岗位特定能力
role_competencies:
  technical_depth:
    weight: 0.25
    description: "技术深度"
    evidence_types: ["real_usage"]

# 其他配置...
```

## 配置验证

使用以下命令验证配置文件：

```bash
python scripts/validate_configs.py
```

## 贡献指南

请参阅 [CONTRIBUTING.md](CONTRIBUTING.md)
