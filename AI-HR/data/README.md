# 测试简历数据说明

本目录包含多个不同行业和岗位的测试简历，用于生成面试邀请链接。

## 简历列表

| 文件名 | 岗位 | 行业 | 说明 |
|--------|------|------|------|
| 测试文本简历 | Java后端开发 | 技术/后端 | 原有的Java后端开发简历 |
| 测试文本简历-前端 | 前端开发工程师 | 技术/前端 | 原有的前端开发简历 |
| resume_fullstack.txt | 全栈开发工程师 | 技术/全栈 | 精通前后端开发，熟悉Vue/React和Node.js/Java |
| resume_product_manager.txt | 产品经理 | 产品 | 具备产品设计、用户研究、数据分析能力 |
| resume_ui_designer.txt | UI/UX设计师 | 设计 | 精通UI/UX设计，熟练使用Figma、Sketch |
| resume_data_analyst.txt | 数据分析师 | 数据 | 精通Python、SQL、机器学习算法 |
| resume_devops.txt | DevOps工程师 | 运维 | 精通Linux、Docker、Kubernetes、CI/CD |
| resume_civil_servant.txt | 公务员 | 政府/行政 | 具备政治素养、综合分析、组织协调能力 |

## 使用方法

### 单个简历生成面试邀请

```bash
# 使用默认简历（测试文本简历）
python scripts/generate_interview_invite.py --no-send-email

# 指定特定简历
python scripts/generate_interview_invite.py --resume data/resume_fullstack.txt --no-send-email

# 指定前端简历
python scripts/generate_interview_invite.py --resume "data/测试文本简历-前端" --no-send-email
```

### 批量生成面试邀请

#### Windows系统
```bash
# 运行批处理脚本
scripts\batch_generate_invites.bat
```

#### Linux/Mac系统
```bash
# 添加执行权限
chmod +x scripts/batch_generate_invites.sh

# 运行脚本
./scripts/batch_generate_invites.sh
```

## 岗位配置说明

每个简历对应的岗位要求已经在 `ai_hr/role_configs/` 目录下配置：

- **后端开发**: `tech/backend.yaml`
- **前端开发**: `tech/frontend.yaml`
- **全栈开发**: `tech/fullstack.yaml`
- **产品经理**: `product/product_manager.yaml`
- **UI设计师**: `design/ui_designer.yaml`
- **公务员**: `government/civil_servant.yaml`

系统会根据简历内容和JD自动识别岗位，并应用对应的面试配置。

## 面试流程说明

生成面试邀请后，系统会：

1. **自动识别岗位**: 根据简历内容和JD匹配最合适的岗位配置
2. **生成面试题目**: 根据岗位配置生成14道面试题（默认）
3. **题目分布**: 
   - S2（自我介绍）: 2题
   - S3（技术栈验证）: 5题
   - S4（项目深挖）: 5题
   - S5-S6（能力补充）: 2题
4. **岗位驱动**: 面试过程会根据岗位配置调整提问策略和评估标准

## 注意事项

1. 确保后端服务已启动（默认 http://127.0.0.1:8000）
2. 确保前端服务已启动（默认 http://localhost:5173）
3. 批量生成时会在每个请求之间等待2秒，避免服务器压力过大
4. 默认使用 `--no-send-email` 模式，只生成邀请链接不发送邮件
5. 生成的邀请链接可以直接在浏览器中打开进行测试

## 测试建议

1. **单岗位测试**: 先测试单个岗位的面试流程，验证题目生成和面试流程
2. **跨岗位测试**: 测试不同岗位的面试流程，验证岗位识别和配置应用
3. **批量测试**: 使用批量脚本生成多个岗位的面试邀请，验证系统稳定性

## 自定义简历

如需添加新的测试简历：

1. 在 `data/` 目录下创建新的 `.txt` 文件
2. 按照现有简历格式编写内容
3. 在批量脚本中添加对应的配置
4. 确保对应的岗位配置文件存在于 `ai_hr/role_configs/` 目录
