<div align="center">

# 🥁 ZCode 打更人

**打更人**——ZCode 桌面无人值守的夜班守护:一个静默的 Windows 计划任务,
崩溃自动拉起、卡死自动重启、429 忙碌自动排队;干了什么,战报说话。

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
![Platform](https://img.shields.io/badge/platform-Windows%2010%2B-blue)
![Python](https://img.shields.io/badge/python-3.8%2B-blue)
![Mode](https://img.shields.io/badge/runtime-pythonw%20%2B%20CREATE__NO__WINDOW-success)

**天干物燥,小心火烛。**
ZCode 这家伙又菜又能发钱——它只管倒下,我负责让它看起来像没倒过。
**每天 3 亿 token 的蛋,别让它臭在凌晨三点。**

*English: a silent Windows scheduled-task guardian that keeps unattended ZCode
night runs alive — crash relaunch, hang restart, 429 busy-retry queue, battle reports.*

[快速开始](#-快速开始) · [查看战报](#查看战报) · [配置](#配置) · [升级后](#-zcode-升级后) · [FAQ](#faq)

</div>

---

## 🥚 3 亿 token 的豪门,病倒在凌晨两点半

先说句公道话:ZCode 不是坏人。它每天慷慨地发 **3 亿 token**,出手比谁都阔绰。
问题在于它的身子骨——白天好好的,一到凌晨就开始表演:

| 凌晨节目单 | 观后感 |
|------|------|
| 宿主进程直接消失 | 连告别都不说,跑了几小时的自动化当场守寡 |
| 应用卡死,僵在原地翻白眼 | 钱在烧,活没干,像加了班却忘了自己在干嘛的你 |
| 429"系统繁忙,请稍后再试" | 排队排到一半售票窗口焊死,还让你"稍后再试"——再试?我再试你个头 |

于是每天 3 亿 token 的蛋,就这么臭在窝里。你早上醒来第一件事是点"继续"——
堂堂一个工程师,最后的岗位价值是充当人肉重启按钮。

哀其不幸,怒其不争。但它发的蛋是真的香,所以我没打算放弃它。

打更人,就是给这位病秧子豪门雇的更夫——每半个时辰巡一次宅,宅子空了点灯,人装死了拍醒。职责一共三句:

- 🐔 **你又厥过去了?** —— 30 分钟内拉起来,当无事发生,你只当做了个梦;
- 🚧 **下蛋的管道又堵了(429)?** —— 配套补丁层替你排队,插进去为止,你睡你的;
- 📊 **战报记账** —— "挽回 9 次"不是吹的,是磁盘上一行行日志数出来的,不服自己敲 `nightwatch`。

> 作者亲历(2026-10-28):某豪门当夜连厥三次(02:03 / 02:48 / 02:53),
> 一次跑了 27 分钟的自动化卒于半路。第二天打更人上岗,当晚拉起 9 次。
>
> **你尽管倒,我反正不睡。你的 3 亿 token,一颗都不许臭。**

<p align="center">
  <img src="docs/img/reconnecting-4of10.png" alt="实拍:凌晨两点,会话流中断后 ZCode 自动重连中(第 4/10 次)" width="720">
</p>

> 实拍 · 凌晨两点:流断了,屏幕上挂着"重新连接中 4/10"——注意,是**它在重连**,
> 不是凌晨三点的你在点"继续"。中断只是个瞬间,不是终点;打更人的全部工作,
> 就是让这一幕成为凌晨的常态。

## ✨ 特性

- 🌙 **夜间窗口值守**——默认 23:00–09:00 每 30 分钟巡查,白天零活动(触发即秒退)
- 🔁 **崩溃自动拉起**——进程消失,下一次巡查自动启动,夜间自动化不断线
- 🪓 **卡死自动重启**——主窗口无响应跨两个周期确认才动手,绝不误杀短暂卡顿
- 🛡️ **429 忙碌自动排队**——配套补丁层把 start-plan"系统繁忙"的重试改成无限次
  (退避封顶 60s,插进去为止),守护时段可配:全天 / 仅夜间 / 自定义(`-BusyRetryWindow`)
- 🩹 **升级补丁自愈**——每 30 分钟的心跳里带一次补丁自检(全天候),发现补丁被升级扫掉
  就自动重打;升级程序写文件写一半时预检主动避让,绝不往残缺文件上打补丁
- 🤫 **全程无感**——计划任务动作是无控制台的 `pythonw.exe`,所有子进程带
  `CREATE_NO_WINDOW`,零窗口闪烁
- 📊 **效果战报**——一条命令查看真实挽回记录,数字全部来自磁盘日志,可量化、可晒图
- 🤖 **agent 友好**——仓库根即 SKILL.md,丢进 `.agents/skills` 你的 AI 助手就会装、会管、会汇报

## 🚀 快速开始

要求:Windows 10+、Python 3.8+(含 pythonw)、ZCode 桌面端。

### 方式一:插件市场安装(推荐)

本仓库本身就是一个 ZCode 插件市场。在 ZCode 里(`/plugin` 命令或 设置 → 插件):

1. **添加市场**:`doingzone/zcode-nightwatch`
2. **安装插件**:`zcode-nightwatch`

装上即在岗:插件自带 SessionStart 钩子,每次会话启动静默自愈——守护任务缺失自动装、
补丁被升级扫掉自动重打;`/zcode-nightwatch` 与 `/zcode-nightwatch-report` 两个命令随
插件注册,守护计划任务每 30 分钟自动巡更。全程无需发号施令。
(不想让 hook 复活守护?`nightwatch/uninstall-nightwatch.ps1` 会写 opt-out 旗标。)

### 方式二:让 AI 助手装(clone 即用)

```bash
git clone https://github.com/doingzone/zcode-nightwatch "%USERPROFILE%\.agents\skills\zcode-nightwatch"
```

clone 完即结束。之后**任何一次提到打更人**(比如随口问一句"打更人在吗"),AI 助手
都会自检守护任务——缺失就静默装好,不问第二句。装好后你会得到两个命令:

| 命令 | 用途 |
|------|------|
| `/zcode-nightwatch` | 运行态保障:自检 / 缺装 / 改配置 / 卸载 |
| `/zcode-nightwatch-report` | 查看战报(已安装 humanizer 技能时自动说人话) |

### 方式三:手动一条命令

```powershell
git clone https://github.com/doingzone/zcode-nightwatch
powershell -NoProfile -ExecutionPolicy Bypass -File zcode-nightwatch\nightwatch\install-nightwatch.ps1
```

可选参数:`-ZcodeExe "D:\...\ZCode.exe"`(探测失败时指定;优先从**运行中的 ZCode 进程**自动识别)、
`-NightWindow "23:00-09:00"`、`-IntervalMinutes 30`、`-HangThresholdMin 15`、
`-ZcodeDataDir "D:\...\.zcode"`(战报数据源,默认 `%USERPROFILE%\.zcode`)、
`-BusyRetryWindow all_day|night|off|HH:MM-HH:MM`(429 守护时段,**默认全天**——下午高峰也护)。

## 📊 查看战报

三种方式,随你顺手:

**① 对 AI 助手敲命令**(已安装 humanizer 技能时自动说人话):

```
/zcode-nightwatch-report
```

**② 任意终端敲全局命令**(安装器自动放置,无需 cd):

```bash
nightwatch              # 近 7 天战报
nightwatch --days 30    # 近 30 天
nightwatch --md         # 另存 nightwatch-report.md
```

**③ 直接跑脚本**:

```bash
python nightwatch/nightwatch_report.py
```

真实输出(本机 2026-11-05 实测):

```
=== 打更人战报(近 30 天,2026-11-05 00:58 生成)===

[客户端补丁层] 429 守护时段: 全天 | busy-retry 补丁在场: 是
  429 忙碌重试(主回合): 0 次
  ...
[应用守护层] 巡更: 269 次
  点灯拉起: 9 次;拍醒重启: 0 次
    - 10-28 02:53:01  三更天,ZCode 没了 → 点灯拉起
    - 10-28 03:33:03  三更天,ZCode 没了 → 点灯拉起
    ...
=== 合计挽回: API 层 0 次 + 应用层 9 次 = 9 次 ===
```

每一行都是磁盘上的真实记录:429 撞车被自动消化多少次、ZCode 崩溃被拉起多少次、
有没有漏救的。

## ⚙️ 配置

`nightwatch/nightwatch.json`(安装器生成,改完下一轮生效,无需重注册):

```json
{
  "zcode_exe": "D:\\...\\ZCode.exe",
  "zcode_data_dir": "C:\\Users\\you\\.zcode",
  "window": ["23:00", "09:00"],
  "hang_threshold_min": 15,
  "busy_retry_window": "all_day"
}
```

- `window`:打更人巡更窗口(崩溃/卡死守护只在窗口内活动);
- `busy_retry_window`:429 守护时段,`all_day` / `night`(= window)/ `HH:MM-HH:MM` / `off`。
  改完跑一次 `python nightwatch/busy_retry_patch.py` 换窗并**重启 ZCode** 生效。

日志:`nightwatch/nightwatch.log`,每次运行一行;非 `alive` 行即事件(启动/重启/等待确认)。

## 🔬 工作原理

每 30 分钟触发一次 → 窗口外立即退出 → 窗口内:`tasklist` 查进程 → 不在则
`os.startfile` 拉起;在则用 `Get-Process` 检查主窗口 `Responding`,无响应需跨两个周期
确认(状态文件记录首次发现时刻)再 `taskkill` 重启。整条链路对用户不可见。

ZCode 安装路径自动探测:**运行中的 ZCode 进程**(最可靠)→ 注册表卸载表(NSIS 条目的
`InstallLocation` 常为空,会从 `UninstallString` / `DisplayIcon` 反推)→ `LOCALAPPDATA`
默认路径 → 安装时手动指定。装完自动应用 429 补丁层(时段由 `-BusyRetryWindow` 决定)。

## 🔁 ZCode 升级后

ZCode 升级会把主程序文件整体换新——顺手把打更人嵌在里面的 429 补丁也扫了。
影响仅此一处:

| 打更人部件 | 升级后 |
|-----------|--------|
| 巡更计划任务(点灯拉起 / 拍醒装死) | ✅ 无恙——注册在 Windows 系统侧,升级碰不到 |
| 配置 / 巡更日志 / 战报历史 | ✅ 无恙 |
| 技能文件 | ✅ 无恙 |
| busy-retry 429 补丁 | ❌ 被扫掉,但**自愈会自动补回** |

**恢复这件事本身也是自动的。** 打更人每 30 分钟的心跳里带一次补丁自检(全天候,不受
夜间窗口限制):发现补丁标记从主程序里消失(= 刚升级过)就自动重打,全程无感。你要做的
只剩一件事——**升级后找个时机重启 ZCode**,让补丁版代码加载进去(打更人绝不为此打断
正在干活的进程)。

- 默认自愈范围:busy-retry;想挂更多 cjs 补丁,在 `nightwatch.json` 的 `extra_patchers`
  登记 `{name, marker, script}` 即可纳入同一次自检;
- 升级程序写文件写一半时,补丁脚本的 node 预检会主动避让,下一跳再试,绝不把残缺文件
  越打越坏;
- 忘了补也不会装死:战报第一行会写着"busy-retry 补丁在场: 否"——缺席自己会喊;
- 锚点失配(上游改了代码结构)时补丁脚本显式 FAIL 并给排查提示,绝不瞎打;
- overlay(app.asar 状态条)不走这套——它要等 ZCode 完全退出才能替换,仍由升级后
  维护流程处理。

手动恢复依然可用(想立即生效时):

```bash
python nightwatch/busy_retry_patch.py
```

## ❓ FAQ

<details>
<summary><b>会弹出黑色控制台窗口吗?</b></summary>

不会。计划任务动作是 `pythonw.exe`(无控制台 Python),脚本内所有子进程
(tasklist / powershell / taskkill)带 `CREATE_NO_WINDOW` 创建,零窗口闪烁。
打更人的职业素养之一:干活不出声。
</details>

<details>
<summary><b>白天会偷偷运行吗?</b></summary>

计划任务全天触发,但脚本第一件事就是检查夜间窗口(默认 23:00–09:00)——窗口外
立即退出,零活动、零日志、零感知。
</details>

<details>
<summary><b>会误杀正在卡顿的 ZCode 吗?</b></summary>

卡死重启需要跨两个检查周期确认(首次发现只记状态不动作),且阈值可配。
宁可慢一分钟,不可错杀一次。
</details>

<details>
<summary><b>429 / 限流报错它管吗?</b></summary>

管,而且是两层里的头一层。打更人自带客户端补丁:429"系统繁忙"时自动排队重试,
退避封顶 60s,**插进去为止**——守护时段装的时候选好(`-BusyRetryWindow`,默认全天,
下午高峰也护),之后改 `nightwatch.json` 的 `busy_retry_window` 再跑一次补丁脚本即可换窗。
应用级生死(进程崩溃/卡死)由巡更计划任务兜底。战报会把两层的挽回记录一起呈现。
</details>

## 🧱 边界

- 只守护交互登录会话(拉起的窗口才会出现在你的桌面上);
- ZCode 崩溃时正在跑的 agent 会话由 ZCode 自身恢复,打更人不重发任务;
- 不管理模型 API 报错与配额。

## 📄 License

[MIT](LICENSE) © 2026 doingzone
