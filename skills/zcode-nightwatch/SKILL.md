---
name: zcode-nightwatch
description: 打更人运行态保障——本技能的唯一使命是"打更人在运行"。任何会话提到打更人/夜间自动化守护/ZCode 崩溃卡死时:先自检 ZCodeNightwatch 计划任务,在位则报一行状态,缺失则不问直接静默安装并验证。不需要用户发号施令。不处理模型 API 报错(那是客户端补丁的事)。
---

# ZCode Nightwatch(打更人)

## 铁律:自检优先,缺装不问

用户引用本技能 = 想让打更人处于工作状态,**不是**想听介绍或被问要不要装。
任何触发的固定流程:

1. 自检两件:
   ①`Get-ScheduledTask ZCodeNightwatch` 存在且 Ready;
   ②busy-retry 补丁在场——
     `python -c "print('Math.min(e.state.streamRecoveryRetryCount' in open(r'<zcode_exe目录>\resources\glm\zcode.cjs',encoding='utf-8',errors='ignore').read())"`
     (zcode_exe 从 `nightwatch/nightwatch.json` 取)。
   两项都过 → 跳到 3。
2. 修复(不确认、不解释设计):①缺 → 直接运行安装器(默认值已合理:窗口 23:00-09:00、
   间隔 30 分钟、卡死阈值 15 分钟),完成后验证任务 Ready;②缺(多半是 ZCode 刚升级
   覆盖了主程序文件)→ 跑 `python nightwatch/busy_retry_patch.py`,成功后提醒用户
   重启 ZCode 加载;脚本 FAIL 则按其排查提示定位新结构,不盲改。
   唯一需要用户输入的例外:ZCode.exe 探测失败时给路径——只问这一件事。
3. 一句话收尾:在位/刚装好 + 夜间窗口 + 日志位置。超过三句就是废话。

维护/卸载/参数调整见下;`git clone` 本仓库到
`%USERPROFILE%\.agents\skills\zcode-nightwatch` 即获得本技能。

## 执行细节

### 安装器(自检失败时自动执行)

```bash
powershell -NoProfile -ExecutionPolicy Bypass -File nightwatch/install-nightwatch.ps1
# 可选参数:-ZcodeExe "D:\...\ZCode.exe" -NightWindow "23:00-09:00" -IntervalMinutes 30
#          -BusyRetryWindow all_day|night|off|HH:MM-HH:MM   (429 守护时段,默认 all_day)
```

Git Bash 环境下加 `MSYS_NO_PATHCONV=1`。装完自验:`Get-ScheduledTask ZCodeNightwatch`
状态 Ready;强跑一次(`schtasks /Run`)看 `nightwatch/nightwatch.log` 追加
`alive` 行、LastTaskResult=0。重跑安装器会保留既有配置值。
安装器会顺带应用 429 busy-retry 补丁(输出 `[OK]/[SKIP]` 即成功;ZCode 需重启加载)。

### 维护 / 查状态

- 日志:`nightwatch/nightwatch.log`(每次运行一行;非 alive 行即事件)。
- 改窗口/阈值:直接编辑 `nightwatch/nightwatch.json`(无需重注册任务,下一次运行生效)。
- 改检查间隔:重跑安装器(带 `-IntervalMinutes`)。
- 改 429 守护时段:编辑 `nightwatch.json` 的 `busy_retry_window`
  (`all_day`/`night`/`HH:MM-HH:MM`/`off`),再跑
  `python nightwatch/busy_retry_patch.py` 换窗,**重启 ZCode** 生效。

### 卸载

```bash
powershell -NoProfile -ExecutionPolicy Bypass -File nightwatch/uninstall-nightwatch.ps1
```

### 查看战报

战报有专属技能与命令,**不要在本技能里手动跑报告脚本**:

- 用户输入 `/zcode-nightwatch-report` 或问"打更人效果如何" → 由
  `zcode-nightwatch-report` 技能处理(会自动调用 humanizer 说人话);
- 终端里用户可直接敲 `nightwatch` 命令(安装器装的 shim,支持 `--days N` / `--md`)。
- 安装器新装时若目录里没有 `nightwatch/nightwatch_report.py`,提示用户 `git pull`。

## 设计要点(改代码前必读)

- **必须以 pythonw.exe 运行 + 所有子进程 CREATE_NO_WINDOW**:这是"无感"的根,改回
  python/cmd 会让每 30 分钟闪一次控制台(用户实测反感)。
- **计划任务必须是交互式登录类型**(默认),不要改成 S4U/"不管用户是否登录"——
  拉起 ZCode 要落在用户桌面上,session 0 启动的 GUI 用户看不见。
- 无响应重启跨**两次**检查确认(状态文件 `nightwatch-state.json` 记首次发现时刻),
  防止把短暂卡顿误杀;30 分钟节奏下从卡死到重启最坏 30-60 分钟,属设计取舍。
- 窗口判断支持跨午夜(`start > end` 形态)。
- **补丁自愈(patch_selfheal)每跳必跑、不做窗口门控**——升级随时发生;它只静默读写
  文件(补丁标记消失 → 重跑 patcher),**绝不因此重启 ZCode**,补丁在应用下次启动时
  自然加载。挂新补丁进自愈:nightwatch.json 的 `extra_patchers` 加
  `{name, marker, script}`。
- 白天(窗口外)触发会直接退出巡更逻辑——这是特性不是 bug;但补丁自愈在窗口判断之前
  已完成,不受此限。

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
