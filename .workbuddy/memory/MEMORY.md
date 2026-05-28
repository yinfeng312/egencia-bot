# Egencia 差旅账单飞书机器人 - 项目记忆

## 关键信息
- **多维表格**: `https://acnjh1thgeif.feishu.cn/base/HR5ib2tFOaS1tisxIpjc7Qkinod`
- **Token**: `HR5ib2tFOaS1tisxIpjc7Qkinod` | Table ID: `tblbIxthU2DScOEh`
- **去重字段**: 账单编号 (Itinerary Number)

## 技术备忘
- 飞书写入: key=字段名, 日期=毫秒时间戳, 单选=数组["值"]
- 查重: list接口+内存比对(搜索filter格式不稳定)
- PDF解析: 系统Python + pdfplumber

## 待办
- [ ] 对接飞书事件订阅
- [ ] 云部署 (Railway)
- [ ] 权限配置
