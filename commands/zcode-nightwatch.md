---
description: 打更人运行态保障——自检守护任务与客户端补丁,缺失自动装/补,支持改配置与卸载
---
按 `skills/zcode-nightwatch/SKILL.md` 执行(铁律:自检优先,缺装不问;收尾超过三句就是废话):

1. 自检两件:①`Get-ScheduledTask ZCodeNightwatch` 存在且 Ready;②busy-retry 补丁标记在
   `zcode.cjs` 里(Python 检查,别用 grep);
2. 缺什么补什么:任务缺失 → 静默跑 `nightwatch/install-nightwatch.ps1`(Git Bash 下加
   `MSYS_NO_PATHCONV=1`);补丁缺失 → `python nightwatch/busy_retry_patch.py` 后提醒重启 ZCode;
3. 一句话收尾:在位/刚装好 + 夜间窗口 + 日志位置。

$ARGUMENTS 可传自然语言指令,如 `改为夜间守护`、`卸载`、`改巡更间隔 20 分钟`——按技能文件的
维护章节处理。
