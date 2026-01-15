# 前端与后端API对接调整计划

## 1. 核心问题分析
根据后端API文档，需要调整前端代码以确保API调用与文档一致，主要问题包括：
- `LoginResponse`类型不匹配，后端返回`access_token`而非`token`
- 部分API调用的响应处理需要调整
- 确保所有API端点、参数和响应格式与文档一致

## 2. 调整方案

### 2.1 `api.ts` 文件调整
- 修正`LoginResponse`接口，添加`access_token`、`token_type`、`user`字段
- 更新`login`函数，正确处理后端返回的响应格式
- 确保所有API函数的返回类型与后端文档一致

### 2.2 `settingsHelper.ts` 文件调整
- 移除或调整与新API不兼容的代码
- 确保存储逻辑与新的API设计一致

### 2.3 `SettingsModal.tsx` 文件调整
- 更新`login`调用，处理新的响应格式
- 确保正确保存用户信息到上下文
- 调整AI Token保存逻辑

### 2.4 其他组件检查
- 确保所有组件使用的API函数参数和响应处理正确
- 验证`DoubanImportDialog`、`GridImportModal`、`ManualAddDialog`等组件的API调用

## 3. 实施步骤
1. 首先修改`api.ts`，确保核心API类型和函数正确
2. 然后修改`settingsHelper.ts`，调整存储逻辑
3. 接着修改`SettingsModal.tsx`，确保登录流程正确
4. 最后检查其他组件，确保API调用一致

## 4. 验证方法
- 运行前端项目，检查编译错误
- 测试登录流程，确保能正确获取和保存JWT令牌
- 测试收藏、搜索等功能，确保API调用正常
- 检查控制台，确保没有API错误

## 5. 预期结果
- 所有前端文件与后端API文档一致
- 前端项目能正常编译和运行
- API调用能正确处理响应
- 登录、收藏、搜索等功能正常工作