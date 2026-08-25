# 核心业务闭环操作指南

主窗口工具栏自左向右对应标准业务的六个环节。推荐首次使用时按顺序体验一遍。

## 流程总览

```text
① Import People → ② Scan Folder → ③ Review Pending → ④ Archive
                          （Detect Duplicates / Export / Settings 随时可用）
```

## ① 导入人员（Import People）

点击工具栏 **Import People**，选择 `.txt` / `.xlsx` / `.xls` 名单文件。

- 每行一位人员：姓名必填；证件号（identity）、部门、备注可选。
- 身份号已存在的人员自动跳过（去重），结果在完成后提示导入/跳过/错误计数。
- 单行错误不会中断整批导入，错误明细写入日志并汇总展示。

## ② 扫描照片（Scan Folder)

点击 **Scan Folder** 选择照片目录，程序递归扫描图片并注册入库：

- 自动提取尺寸、拍摄时间（EXIF 优先）等内容元数据；
- 同一文件内容计算 SHA-256 哈希，供后续重复检测；
- 进度实时显示在底部状态栏，完成后照片出现在中央列表。

## ③ 审核识别结果（Review Pending)

执行过人脸匹配后，点击 **Review Pending** 打开审核对话框：

- 逐条查看候选匹配，**Approve**（采纳）或 **Reject**（驳回）；
- 只有 **approved** 的照片才会进入归档环节；
- 审核即时生效并持久化，可随时关闭稍后继续。

## ④ 归档（Archive）

点击 **Archive** 打开归档预览：

1. 预览对话框列出本次将执行的复制计划（目标路径 = `{ARCHIVE_ROOT}/{人员}/{日期}/{文件名}`）；
2. 可选择冲突策略：**skip**（默认，遇同名跳过）/ **overwrite**（覆盖）/ **rename**（自动加后缀改名）；
3. 勾选 **dry-run** 可只生成计划不落盘；
4. 在列表中多选照片可只归档选中项；未选择时归档全部 approved 照片。

> 若提示 `ARCHIVE_ROOT is not configured`，请在 `.env` 中设置该目录后重启，或改用命令行 `python main.py archive --archive-root <目录>`。

## 附加能力

| 功能 | 说明 |
|---|---|
| **Detect Duplicates** | 按内容哈希分组展示重复照片报告（只读，不做删除） |
| **Export** | 将人员/照片/审核/归档数据导出为 Excel（`.xlsx`）、CSV 或 HTML 报告 |
| **Settings**（Ctrl+,） | 调整界面主题、语言、匹配置信度阈值、后台并发数等偏好，保存于系统原生设置存储 |
| **插件菜单** | 加载自 `examples/plugins/` 的扩展动作（如统计报表、演示导入），失败插件自动隔离不影响主程序 |

## 命令行对照

| 图形操作 | 等效命令 |
|---|---|
| Scan Folder | `python main.py scan <目录> [--no-recursive] [--name 显示名]` |
| Archive（全量 approved） | `python main.py archive --archive-root <目录> [--dry-run] [--conflict-strategy ...]` |
| 历史哈希回填 | `python main.py backfill-content-hash` |
