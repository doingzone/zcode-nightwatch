---
description: 查看打更人战报——429 自动消化多少次、崩溃拉起多少次、卡死重启多少次、补丁自动重打多少次
---
按 `skills/zcode-nightwatch-report/SKILL.md` 执行:

1. **自愈先行**:计划任务 `ZCodeNightwatch` 不存在时,先静默运行
   `nightwatch/install-nightwatch.ps1`(不问用户),Git Bash 下加 `MSYS_NO_PATHCONV=1`;
2. 运行 `python "<插件根目录>/nightwatch/nightwatch_report.py" $ARGUMENTS`
   (`$ARGUMENTS` 原样透传,支持 `--days N`、`--md`;为空 = 近 7 天);
3. 已安装 humanizer 技能时按其指引把战报说成人话,否则按技能文件的白话模板;
   **数据一个都不能改**,开头第一句给"合计挽回 N 次"。
