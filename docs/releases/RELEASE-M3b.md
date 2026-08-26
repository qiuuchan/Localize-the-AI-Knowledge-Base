# KB-AI · M3b Release Notes

## 交付日期

2026-07-02

## 范围

M3 step 4 第一批交付物:
- 跨平台 U 盘根定位(`get-usb-root.ps1`)
- 终端命令速查(`show-help.ps1`)
- 版本 + 健康度 1 行总览(`version.ps1`)
- `chat.ps1` 路径解析改造
- 验收测试(`test_m3b.ps1`)

## 用户场景覆盖

1. **换 U 盘盘符**:用户在 A 电脑拔出 U 盘,插入 B 电脑(D:→E:→F:),所有脚本仍能找到 KB-AI 根
2. **跨平台**:同一份代码在 Windows / macOS / Linux 都能运行
3. **第一次接触**:新用户 `pwsh -File scripts/show-help.ps1` 一屏看到所有可用命令
4. **健康度自检**:终端一行看出"KB-AI 当前能不能用"(版本 + 容器 + 数据 + 容量)

## 5 个交付文件

| 文件 | 行数 | 字节 |
|---|---|---|
| scripts/get-usb-root.ps1 | 210 | 7405 |
| scripts/show-help.ps1 | 100 | 4194 |
| scripts/version.ps1 | 258 | 8421 |
| scripts/chat.ps1 | 822 (+1) | 31628 (+113) |
| tests/test_m3b.ps1 | 964 | 42540 |

## 测试结果

- **M3b**:30/30 PASS(8 硬性 + 22 Mock)
- **M3a 回归**:20/20 PASS 无破坏

## 向后兼容

- M2a / M2b / M3a 既有 8 个 .ps1 脚本零修改
- start.bat / stop.bat 零修改
- docker-compose.yml 零修改
- .env 零修改

## 后续 plan(不在 M3b 范围)

- 其他脚本路径解析统一改造(只剩 chat 示范改)
- Dify Web UI 主题改色(走终端极简路线,Dify 默认)
- 图片理解(plan-010)
- 真机跨平台测试(plan-011)