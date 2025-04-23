<div align="center">


# astrbot_plugin_apis

_✨ [astrbot](https://github.com/Soulter/AstrBot) API聚合插件 ✨_
[![License](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![AstrBot](https://img.shields.io/badge/AstrBot-3.4%2B-orange.svg)](https://github.com/Soulter/AstrBot)
</div>


## 📦 介绍

API聚合插件，海量免费API动态添加，热门API：看看腿、看看腹肌...


## 📦 安装

- 可以直接在astrbot的插件市场搜索astrbot_plugin_apis，点击安装即可  

- 或者可以直接克隆源码到插件文件夹：

```bash
# 克隆仓库到插件目录
cd /AstrBot/data/plugins
git clone https://github.com/Zhalslar/astrbot_plugin_apis

# 控制台重启AstrBot
```

## ⚙️ 配置
请在astrbot面板配置，插件管理 -> astrbot_plugin_apis -> 操作 -> 插件配置

## ⌨️ 使用说明

### 指令表

|     命令      |        说明        |
|:-------------:|:--------------------------:|
| /api列表      | 查看所有能触发api的关键词  |
| /api详情 xxx  | 具体查看某个api的参数 |
| /添加api xxx  | 添加指定api        |
| /删除api xxx  | 删除指定api        |
|   {关键词}     |   触发api      |


, 关键词包括：
```plaintext
待添加

```

- 本插件支持从原始消息中提取参数，请用空格隔开参数，如 “艺术字 哈喽”
- 本插件支持从引用消息中提取参数，如“[引用的消息]艺术字”
- 提供的参数不够时，插件自动获取消息发送者、被 @ 的用户以及 bot 自身的相关参数来补充。

### 示例图
![b421d15916a8db6109bb36c002ba2e5](https://github.com/user-attachments/assets/ec15b5f7-eec2-4552-814d-60dcc4196713)



## 📌 注意事项
1. 想第一时间得到反馈的可以来作者的插件反馈群（QQ群）：460973561
2. 感觉本插件做得还不错的话，点个star呗（右上角的星星）


## 📜 开源协议
本项目采用 [MIT License](LICENSE)
