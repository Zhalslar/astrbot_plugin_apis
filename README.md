<div align="center">

![:name](https://count.getloli.com/@astrbot_plugin_apis?name=astrbot_plugin_apis&theme=minecraft&padding=6&offset=0&align=top&scale=1&pixelated=1&darkmode=auto)

# astrbot_plugin_apis

_✨ [astrbot](https://github.com/Soulter/AstrBot) API聚合插件 ✨_

[![License](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![AstrBot](https://img.shields.io/badge/AstrBot-3.4%2B-orange.svg)](https://github.com/Soulter/AstrBot)
[![GitHub](https://img.shields.io/badge/作者-Zhalslar-blue)](https://github.com/Zhalslar)

</div>

## 💡 介绍

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

### 插件配置

请在astrbot面板配置，插件管理 -> astrbot_plugin_apis -> 操作 -> 插件配置

### Docker 部署配置

如果您是 Docker 部署，消息平台容器（如Napcat）、astrbot容器都要挂载宿主机中apis插件的数据目录（...data/plugins_data/astrbot_plugin_apis）

示例挂载方式(NapCat)：

- 对 **AstrBot**：`/vol3/1000/dockerSharedFolder -> /app/sharedFolder`
- 对 **NapCat**：`/vol3/1000/dockerSharedFolder -> /app/sharedFolder`

同时也可以参考[1#issuecomment-2837167979](https://github.com/Zhalslar/astrbot_plugin_apis/issues/1#issuecomment-2837167979)

## ⌨️ 使用说明

部分api站点需要密钥，如 倾梦API：<https://api.317ak.cn>， 此站点需前往网页，注册账号，获取ckey密钥，填入插件配置中的“api密钥 (api_keys)”

### 指令表

|     命令      |        说明        |
|:-------------:|:--------------------------:|
| api详情 xxx  | 具体查看某个api的参数，不提供参数时查看所有能触发api的关键词 |
| 删除api xxx  | 删除指定api        |
|   {关键词}     |   触发api      |

建议直接通过编辑"data\plugins\astrbot_plugin_apis\api_data.json"进行添加api、删除api，同时也方便修改更多参数。

- "keyword": api触发词，支持设置多个。
- "fuzzy": 默认为false，设置为true时可模糊匹配触发词，从而提高触发率, 谨慎设置，容易误触,
- "url"：api的请求地址，支持设置多个，一个URL请求失败时自动轮询下一个。
- "type"：api返回数据的类型，目前支持text、image、video、audio。
- "params"：api请求时输入的参数，参数的key为参数名，value为参数值，可指定默认值。
- "target"：返回数据的解析路径，例如"data.imgurl"表示返回数据中的data的imgurl字段。

```plaintext
"KFC": {
    "keyword": ["KFC","kfc","疯狂星期四", "肯德基", "v我50"],
    "fuzzy": true,
    "url": "https://api.317ak.com/API/wz/KFC.php",
    "type": "text",
    "params": {
        "type": "text"
    }
},
"艺术字": {
    "keyword": ["艺术字"],
    "url": "https://free.wqwlkj.cn/wqwlapi/ysz.php",
    "type": "image",
    "params": {
        "text": "",
        "id": "30",
        "color": "0000FF",
        "shadow": "FF0000",
        "background": "FFFFFF"
    },
    "target": "data.imgurl"
}
```

### 收录API

```plaintext
 ----共收录了160+个API（请用 api详情 查看）----


【text】52个：
讲讲社会、讲讲人生、讲个笑话、讲讲爱情、讲讲温柔、讲讲摆烂、来句古诗、
来碗毒鸡汤、讲讲舔狗、来句情话、讲讲伤感、来句骚话、讲讲英汉、电影票房、
脑筋急弯、随机谜语、随机姓名、B站更新、光遇任务、来点段子、兽语加密、
兽语解密、看看黄历、二次元形象、动漫一言、香烟价格、人品运势、KFC、QQ签名、
嘲讽、晚安、胡乱描述、Linux命令、身份证查询、高校查询、古诗文查询、今天吃什么、
黄金价格、人物年轮、车辆查询、起个网名、号码归属地、挑战古诗词、显卡排行榜、
垃圾分类、刑法、来碗鸡汤、发病、来句诗、文案、来篇文章、中草药、

【image】45个：
电脑壁纸、来个头像、手机壁纸、读世界、来份早报、生成二维码、测CP、看看风景、随便来点、
来点龙图、来点cos、来点二次元、海贼王、看看猫猫、doro结局、晚安、来点腹肌、原神、来点坤图、
看看腿、来点帅哥、超甜辣妹、每日一签、竖屏动漫壁纸、奥运会、光遇日历、斗图、热榜、星座运势、
小动物、三坑少女、画画、LOL查询、看看妞、bing图、随机上色、原神黄历、艺术字、搜图、每日日报、
搜表情、搜菜谱、高清壁纸、今日运势、日历、

【video】61个：
看看女大、看看骚的、看看玉足、看看漫画、看看emo、看看动漫、看看治愈、看看帅哥、
来点色色、女高中生、女大、欲梦、看看黑丝、看看白丝、高质量小姐姐、深刻推荐、
看看小葫芦、看看jk、看看久喵、仙桃猫、看看公主、看看心情、看看小雪、看看红鸾、
看看狼宝、看看雪梨、看看兔兔、拜托前辈、看看穿搭、鞠婧祎、音乐视频、周扬青、周清欢、
潇潇、看看甜妹、看看清纯、看看萌娃、看看慢摇、看看COS、看看余震、看看欲梦、看看萝莉、
看看晴天、光剑变装、动漫变装、完美身材、火车摇、蹲下变装、看看吊带、擦玻璃、背影变装、
安慕希、看看微胖、硬气卡点、黑白双煞、猫系女友、看看女仆、又纯又欲、看看甩裙、看看腹肌、看看原神、

【audio】8个：
每日听力、逆天语音、坤叫、报时、王者语音、喘息、原神语音、御姐撒娇、 

```

- 本插件支持从原始消息中提取参数，请用空格隔开参数，如 “艺术字 哈喽”
- 本插件支持从引用消息中提取参数，如“[引用的消息]艺术字”
- 提供的参数不够时，插件自动获取消息发送者、被 @ 的用户以及 bot 自身的相关参数来补充。

### 示例图

![5123084b9e5a5f9371db19224575a43](https://github.com/user-attachments/assets/73c38cc2-49b8-4d67-b48e-77cd28b1fd81)
![c37bb35479df19aa2da40d6a13eea564](https://github.com/user-attachments/assets/b8e6682a-1c0b-4743-86eb-b7ed39344a17)


## 📌 TODO

- [x] 实现api统一存储、调用
- [x] 支持动态添加、删除api
- [x] 自动保存api返回的数据
- [x] api失效时采用本地数据
- [x] api详情、api列表
- [x] 自动解析部分api返回的json格式数据
- [x] 支持一个api对应多个触发词

## 👥 贡献指南

- 🌟 Star 这个项目！（点右上角的星星，感谢支持！）
- 🐛 提交 Issue 报告问题
- 💡 提出新功能建议
- 🔧 提交 Pull Request 改进代码

## 📌 注意事项

- 请把astrbot的引用消息开关给关了，否则无法发送视频、音频（视频、音频不能引用）。
- Docker容器部署的astrbot要配置好路径映射，否则无法发送图片、视频、音频，不会配置映射的建议不要用docker部署。
- 海外服务器可能无法直接访问大部分API，网络问题自行解决。
- 收录的某些API可能并不稳定，存在失效的情况，属于正常现象。
- 如果想第一时间得到反馈，可以来作者的插件反馈群（QQ群）：460973561（不点star不给进）

## 🤝 鸣谢

本插件收录的免费api大多来自下面的站点，希望有能力的使用者可以赞助一下。另外如有某个api失效，可在各站点间找平替。

- 枫林API：<https://api.yuafeng.cn>
- 枫林API二代: <https://api-v2.yuafeng.cn>
- 稳定API：<https://api.xingchenfu.xyz>
- 倾梦API：<https://api.317ak.cn>， 此站点需注册账号获取ckey密钥！！
- 星之阁API：<https://api.xingzhige.com>
- 桑帛云API：<https://api.lolimi.cn>
- 糖豆子API：<https://api.tangdouz.com>
- PearAPI：<https://api.pearktrue.cn>
- 问情免费API：<https://free.wqwlkj.cn>
