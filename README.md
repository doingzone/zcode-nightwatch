# ZCode Nightwatch(守夜人)

> 长夜将至,我从今开始守望。
> 你的 ZCode 夜间自动化任务由它值守——崩溃自动拉起,卡死自动重启,全程无感。

**ZCode Nightwatch** 是一个 Windows 计划任务技能:在你设定的夜间窗口内,每 30 分钟
巡查一次 ZCode 桌面端。它专治无人值守场景下最烦人的两种死法:

| 症状 | 处置 |
|------|------|
| ZCode 崩溃退出(夜间自动化全灭) | 下一次巡查自动拉起,会话自动恢复 |
| 应用卡死无响应(鼠标转圈点不动) | 连续两个周期确认后强杀重启,不误杀短暂卡顿 |

## 特性

- **无感运行**——计划任务动作是无控制台的 `pythonw.exe`,脚本内所有子进程带
  `CREATE_NO_WINDOW`,零窗口闪烁,你感知不到它的存在
- **一条命令安装**——自动探测 ZCode 安装路径(注册表)与 pythonw,写好配置、注册任务
- **可配置**——夜间窗口、检查间隔、卡死阈值全部参数化,配置文件热生效
- **保守处置**——卡死重启需跨两个检查周期确认,绝不误杀;白天窗口外完全不干活
- **效果战报**——`python nightwatch/nightwatch_report.py` 一条命令查看真实记录:
  429 忙碌重试自动挽回多少次、崩溃拉起/卡死重启各多少次、未挽回案例列表,效果可量化
- **agent 友好**——根目录即 SKILL.md,丢进 `.agents/skills` 即可让 AI 助手代装代管

## 安装

### 方式一:让 AI 助手装(推荐)

把本仓库 clone 到技能目录后,对助手说"给 ZCode 装个守夜人"即可:

```bash
git clone https://github.com/doingzone/zcode-nightwatch "%USERPROFILE%\.agents\skills\zcode-nightwatch"
```

### 方式二:手动一条命令

```powershell
git clone https://github.com/doingzone/zcode-nightwatch
powershell -NoProfile -ExecutionPolicy Bypass -File zcode-nightwatch\nightwatch\install-nightwatch.ps1
```

可选参数:`-ZcodeExe "D:\...\ZCode.exe"`(探测失败时指定)、`-NightWindow "23:00-09:00"`、
`-IntervalMinutes 30`、`-HangThresholdMin 15`。

要求:Windows 10+、Python 3.8+(带 pythonw)、ZCode 桌面端。任务以当前登录用户的
交互会话运行(拉起的窗口才会出现在你的桌面上)。

## 配置

`nightwatch/nightwatch.json`(安装器生成,改完下一轮生效,无需重注册):

```json
{
  "zcode_exe": "D:\\...\\ZCode.exe",
  "window": ["23:00", "09:00"],
  "hang_threshold_min": 15
}
```

日志:`nightwatch/nightwatch.log`,每次运行一行;非 `alive` 行即事件(启动/重启/等待确认)。

## 工作原理

每 30 分钟触发一次 → 窗口外立即退出 → 窗口内:`tasklist` 查进程 → 不在则
`os.startfile` 拉起;在则用 `Get-Process` 检查主窗口 `Responding`,无响应需跨两个周期
确认(状态文件记录首次发现时刻)再 `taskkill` 重启。整个链路对用户不可见。

## 边界

- 只管**应用级**生死;模型 API 429/限流、配额耗尽不归它管。
- 只守护交互登录会话;ZCode 崩溃时正在跑的 agent 会话由 ZCode 自身恢复,守夜人不重发任务。
- 卸载:`powershell -File nightwatch\uninstall-nightwatch.ps1`,干净利落。

## License

MIT
