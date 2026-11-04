---
name: zcode-nightwatch
description: 守夜人——为 ZCode 桌面端夜间无人值守自动化任务提供应用级守护。安装/维护/卸载一个 Windows 计划任务:夜间窗口内自动拉起崩溃的 ZCode、强杀重启无响应卡死的 ZCode(无感运行,零窗口闪烁)。当用户要求"夜间自动化守护""ZCode 崩溃自动重启""装个守夜人"或反馈夜间任务因应用崩溃/卡死中断时使用。不处理模型 API 报错(那是客户端补丁的事)。
---

# ZCode Nightwatch(守夜人)

夜巡计划任务安装器 + 维护手册。本仓库根目录即 skill 根,可直接 `git clone` 到
`%USERPROFILE%\.agents\skills\zcode-nightwatch` 使用。

## 给 agent 的执行流程

### 安装(首次)

1. 读 `README.md` 确认用户需求(夜间窗口、检查间隔),不确定时问一句,默认
   窗口 23:00-09:00、间隔 30 分钟、卡死阈值 15 分钟。
2. 运行安装器(Git Bash 环境下必须落盘执行或加 `MSYS_NO_PATHCONV=1`,见坑速查):

   ```bash
   powershell -NoProfile -ExecutionPolicy Bypass -File nightwatch/install-nightwatch.ps1
   # 可选参数:-ZcodeExe "D:\...\ZCode.exe" -NightWindow "23:00-09:00" -IntervalMinutes 30
   ```

   ZCode 路径自动探测(HKCU/HKLM 卸载表 → LOCALAPPDATA 默认路径);探测失败时
   **向用户要路径**,用 `-ZcodeExe` 传入,不要瞎猜。
3. 验证:`Get-ScheduledTask ZCodeNightwatch` 状态 Ready;`schtasks /Run` 强跑一次后
   看 `nightwatch/nightwatch.log` 追加了 `alive`/`started` 行、LastTaskResult=0。
4. 汇报:任务名、节奏、窗口、日志位置。

### 维护 / 查状态

- 日志:`nightwatch/nightwatch.log`(每次运行一行;非 alive 行即事件)。
- 改窗口/阈值:直接编辑 `nightwatch/nightwatch.json`(无需重注册任务,下一次运行生效)。
- 改检查间隔:重跑安装器(带 `-IntervalMinutes`)。

### 卸载

```bash
powershell -NoProfile -ExecutionPolicy Bypass -File nightwatch/uninstall-nightwatch.ps1
```

### 效果战报(用户问"效果如何 / 挽回记录 / 战报 / 感受一下"时)

```bash
python nightwatch/nightwatch_report.py            # 近 7 天
python nightwatch/nightwatch_report.py --days 30  # 近 30 天
python nightwatch/nightwatch_report.py --md       # 结果另存 nightwatch-report.md
```

读给用户时讲清两层口径:**客户端补丁层**(429 忙碌重试计数,依赖 zcode-fixes 补丁在场,
报告头部会标注在场状态)与**应用守护层**(崩溃拉起 / 卡死重启,守夜人本体)。"未挽回"
一栏来自 tasks-index 的 lastError——会话后续成功运行会覆盖清零,故只反映当前在册的
回合死亡,不代表历史累计。

## 设计要点(改代码前必读)

- **必须以 pythonw.exe 运行 + 所有子进程 CREATE_NO_WINDOW**:这是"无感"的根,改回
  python/cmd 会让每 30 分钟闪一次控制台(用户实测反感)。
- **计划任务必须是交互式登录类型**(默认),不要改成 S4U/"不管用户是否登录"——
  拉起 ZCode 要落在用户桌面上,session 0 启动的 GUI 用户看不见。
- 无响应重启跨**两次**检查确认(状态文件 `nightwatch-state.json` 记首次发现时刻),
  防止把短暂卡顿误杀;30 分钟节奏下从卡死到重启最坏 30-60 分钟,属设计取舍。
- 窗口判断支持跨午夜(`start > end` 形态)。
- 白天(窗口外)触发会直接退出——这是特性不是 bug。

## 坑速查(Windows + Git Bash)

- Git Bash 把 `/xxx` 参数转路径:`schtasks /Query` 等加 `MSYS_NO_PATHCONV=1` 或落盘 .ps1。
- 复杂 PowerShell 一律落盘 .ps1 执行,单行 `-Command` 内嵌引号会被剥坏。
- schtasks 输出是 GBK,UTF-8 grep 会静默漏——用 PowerShell 的
  Get-ScheduledTask/Get-ScheduledTaskInfo 查询。
- pythonw 下 `sys.stdout` 是 None,print 前要判空。
- **Python 3.9 没有 `str | None` 注解语法**(导入即炸,任务静默 LastTaskResult=1 且无日志)——
  保留 `from __future__ import annotations` 或用 Optional。
- **PowerShell 5.1 的 `Set-Content -Encoding UTF8` 写出带 BOM 的 JSON**,`json.loads` 会静默
  失败——读取必须用 `encoding="utf-8-sig"`。
- **NSIS 卸载表的 `InstallLocation` 常为空**,ZCode 真实路径要从 `UninstallString` /
  `DisplayIcon` 的文件路径反推安装目录(安装器已内置该回退)。
