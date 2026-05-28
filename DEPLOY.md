# Egencia 报账助手 - 部署上线指南

> **当前状态**: 代码已就绪 ✅ | GitHub已推送 ✅ | 待操作: Railway部署 + 飞书配置

---

## 第一步：Railway 部署（约 2 分钟）

### 1.1 创建项目
1. 打开 https://railway.app/dashboard
2. 点击 **New Project** → **Deploy from GitHub repo**
3. 选择 `yinfeng312/egencia-bot` 仓库
4. 点 **Import** → **Deploy Now**

### 1.2 配置环境变量（关键！）
部署会先失败（因为没有环境变量），这是正常的：

1. 在项目页面点击 **Variables** 标签
2. 添加以下 **4 个**变量：

| 变量名 | 值 |
|--------|-----|
| `FEISHU_APP_ID` | `cli_aa9fb0fc6cf8dbd3` |
| `FEISHU_APP_SECRET` | `kVDLMJMO8pFpMZOZwJPJKbknt7ltPWei` |
| `BITABLE_TOKEN` | `HR5ib2tFOaS1tisxIpjc7Qkinod` |
| `WEBHOOK_VERIFY_TOKEN` | `egencia_bot_verify_2026` |

3. 点 **Deployments** → 选最新的 → **Redeploy**

### 1.3 获取公网地址
部署成功后：
- 点击 **Settings** → **Networking**
- 复制生成的 **Public URL**，格式类似：`https://xxx.up.railway.app`
- **记住这个地址**，下一步飞书配置要用

---

## 第二步：飞书后台配置

### 2.1 开启机器人能力
1. 打开 https://open.feishu.cn/app （飞书开放平台）
2. 进入你的应用（App ID: `cli_aa9fb...`）
3. 左侧菜单 → **应用能力** → **机器人**
4. 开启 **机器人** 能力开关

### 2.2 配置事件订阅
1. 左侧菜单 → **事件与回调** → **事件配置**
2. **请求地址 URL** 填写：`https://你的railway域名.up.railway.app/`
3. **Encryption Mode** 选 **不加密**（后续可加）
4. 点击 **保存** → 飞书会发验证请求到你的 Railway 地址
5. 如果部署正常，验证会自动通过 ✅

### 2.3 添加事件权限
在 **事件配置** 页面，点击 **添加事件**：
- 搜索并添加：`im.message.receive_v1`（接收消息）

### 2.4 申请权限
左侧菜单 → **权限管理**，确保开通以下权限：

| 权限标识 | 用途 |
|---------|------|
| `im:message` | 接收/发送消息 |
| `im:message:send_as_bot` | 以机器人身份发送消息 |
| `im:file` | 下载用户文件 |
| `bitable:table` | 读写多维表格 |

### 2.5 发布版本
左侧菜单 → **版本管理与发布**：
1. 点击 **创建版本**
2. 填写版本号（如 `v1.0.0`）
3. 点 **申请发布**

---

## 第三步：测试验证

1. 在飞书中找到你的机器人（搜索机器人名称）
2. 发一条文字消息 → 应收到使用说明
3. 发一个 Egencia PDF 账单 → 应自动解析并返回表格链接

### 多维表格查看地址
```
https://acnjh1thgeif.feishu.cn/base/HR5ib2tFOaS1tisxIpjc7Qkinod
```

---

## 故障排查

| 问题 | 可能原因 | 解决方法 |
|------|---------|---------|
| Railway 部署失败 | 缺少环境变量 | 检查 Variables 是否4个都填了 |
| 飞书事件订阅验证失败 | Railway 未正常运行 | 检查 Deployment Logs |
| 收不到消息回复 | 权限未开通 | 确认 2.4 步的4个权限 |
| PDF 解析失败 | 非 Egencia 格式/扫描件 | 确认 PDF 有文字层 |
| 写入表格失败 | Bitable Token 错误 | 确认 BITABLE_TOKEN 正确 |
