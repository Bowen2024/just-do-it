# 显式上游引用区

`develop-helper` 是本机软链，目标由 config/local.json 指定；链接不进入 Git。
保留上游目录关系，但不自动加载原 AGENTS、Router、平台配置或技能。
先校验基线；本阶段只读取和分析，不执行上游脚本、不写入原目录。
