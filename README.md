<div align="center">

# Cloud Save Max

基于 [cloud-auto-save-x](https://github.com/OzoO0/cloud-auto-save-x) v1.0.9版本改造的网盘自动转存工具

[![wiki](https://img.shields.io/badge/wiki-Documents-green?logo=github)](https://github.com/Cp0204/quark-auto-save/wiki)
[![GitHub releases](https://img.shields.io/github/v/release/wuanqicll-del/cloud-save-max?logo=github)](https://github.com/wuanqicll-del/cloud-save-max)
[![Docker pulls](https://img.shields.io/docker/pulls/wuanqicll/cloud-save-max?logo=docker&logoColor=white)](https://hub.docker.com/r/wuanqicll/cloud-save-max)

</div>

## 项目简介

Cloud Save Max 是基于 [cloud-auto-save-x](https://github.com/OzoO0/cloud-auto-save-x) v1.0.9版本进行改造的网盘自动转存工具，保留了原项目大部分功能，修改了一些逻辑并新增了大量新功能，做到一次添加之后全程无需手动管理。

## 本项目新增功能（部分，细节的就不说了）

### 搜索与筛选

- 🔍 **搜索筛选词/过滤词**：搜索结果支持关键词筛选和过滤，支持"包含所有"和"包含任意"两种模式
- 📅 **搜索时间过滤**：按发布时间过滤搜索结果
- 👤 **分享者黑白名单**：
- 1:支持在搜索结果和预览窗里面优选和屏蔽特定分享者
- 2:可设置只看优选分享者和显示屏蔽分享者，优选者在搜索结果以绿色背景显示，开启显示被屏蔽分享者后，被屏蔽分享者以红色背景显示 
   （屏蔽分享者谨慎使用，有些分享者分享的资源可能缺集，但是本项目针对此问题专门做了优化，可以做到转存的内容百分百不会缺集）

### 文件夹与文件过滤

- 📁 **文件夹筛选/过滤**：按文件夹名称筛选或过滤，支持"包含所有"和"包含任意"模式
- 📅 **文件夹时间过滤**：按文件夹时间过滤
- 📄 **文件关键词筛选/过滤**：按文件名关键词筛选或过滤，支持"包含所有"和"包含任意"模式
- 📅 **文件时间过滤**：按文件时间过滤
- 📦 **最小文件大小**：过滤小于指定大小的文件
- 🔄 **自动更新文件时间过滤**：追剧进度追上最新集数时自动更新文件时间过滤

### 自动换链

- 🔗 **智能换链**：
- 1:解除只有115支持自动换链的限制，支持所有网盘
- 2:大量重构自动换链逻辑，配合各种过滤/筛选规则，可以实现精准换链到自己想要的资源
- 3:链接失效或当前集数不是最新时自动触发换链
- 4:支持无tmdb api自动换链

### 任务模板

- 📋 **模板保存**：将常用配置保存为模板，快速应用
- 🏷️ **模板管理**：支持创建、编辑、删除模板
- 🔧 **模板内容**：包含筛选词、过滤词、重命名规则、文件大小等配置

### 预览与操作

- 👁️ **预览窗优化**：显示文件筛选标记、分享者信息、文件时间
- ❌ **红叉标记**：清晰显示文件被过滤的原因
- 📊 **连贯性检查**：支持部分连贯，资源缺集会只转存当前进度+1连贯的部分，随后会触发自动换链补充其他集，新任务首次执行会从0+1开始，支持 zip 压缩包格式

### 重命名与变量

- 📝 **魔法变量扩展**：新增 `{E0}`、`{E2}` 变量
- 🎯 **内置规则选择**：支持从预设规则中选择重命名规则，优化了内置预设，支持综艺（期数/上下集）的重命名

### 其他增强

- 🗓️ **任务编辑**：支持直接创建关联同步任务，配合openlist/alist可实现精准定位目录同步strm，无需扫其他不相关目录，减少某些网盘风控风险
- 💾 **缓存优化**：搜索和验证结果缓存，可设置缓存时间，资源不会随时更新，建议设置10分钟及以上
- ⚙️ **系统设置**：新增优选者/屏蔽名单管理、关键词过滤预设管理、任务模板管理、验证与缓存管理
- 🗜️ **自动解压**：解压后自动移动到保存目录并重命名
- ⌚️ **cron定时**：增加预览，输入cron表达式后可预览详细执行时间规则

---

## 原项目简介

<div align="center">

# 网盘自动转存

网盘签到、自动转存、命名整理、发推送提醒、刷新媒体库一条龙，内置自动修复异常任务能力。

</div>

> ⛔️⛔️⛔️ 注意！资源不会每时每刻更新，**严禁设定过高的定时运行频率！** 以免账号风控和给网盘服务器造成不必要的压力。雪山崩塌，每一片雪花都有责任！

### 简介

网盘自动转存（Cloud Auto Save X 简称 CASX）是一个基于 FastAPI + Vue3 的 Web 应用，提供网盘自动转存功能，可以帮助你：

- 🔄 **自动转存**：定时或自动（根据节目状态和任务进度）运行，自动转存各种网盘分享链接中的文件
- 🔄 **数据同步**：基于OpenList实现的多网盘数据同步和网盘与NAS本地的数据同步
- 📝 **智能规则**：在为手动配置重命名规则并且配置TMDB配置时，支持自动识别-重命名
- 🧩 **文件过滤**：通过过滤规则排除不需要的文件或文件夹，支持高级过滤功能
- 📊 **任务管理**：支持多任务管理，支持全局统一设置及单任务独立设置，支持任务筛选和排序
- 🔍 **资源搜索**：智能搜索网盘资源，自动识别链接可用性，自动定位到分享目录
- 🎬 **影视发现**：浏览豆瓣热门影视榜单，一键快速创建任务，智能填充配置
- 📅 **追剧日历**：追踪节目播出时间，了解转存进度，支持海报视图和日历视图
- ✅ **自动签到**：每日自动签到领空间（支持：夸克网盘、天翼云盘、百度网盘）
- 🔔 **通知推送**：支持多个通知推送渠道，及时了解转存状态
- 🔌 **插件系统**：支持多种插件扩展功能，包括媒体库局部刷新、下载任务推送、strm 文件生成等

### 自动转存功能

- 分享链接自动识别资源存放文件夹
- 转存任务文件智能重命名（需配置TMDB API密钥）
- 智能搜索资源并自动填充（集成 CloudSaver、PanSou，支持有效性检查、支持所有过滤/筛选。
- 支持自动解压压缩包（仅限夸克高级会员）
- 支持一次性转存任务

### 部署

#### Docker 部署

Docker 部署提供 WebUI 进行管理配置，部署命令：

```shell
docker run -d \
  --name cloud-save-max \
  -p 5115:5115 \ # 映射端口，:前的可以改，即部署后访问的端口，:后的不可改
  -v ./cloud-save-max/data:/app/backend/data \ # 必须，配置持久化
  -v ./cloud-save-max/media:/media \ # 可选，模块alist_strm_gen生成strm使用
  -v ./cloud-save-max/strm:/strm \ # 可选，项目本身生成strm使用
  -v ./cloud-save-max/nasfile:/app/backend/data/sync/nasfile \ # 可选，用于同步任务Local使用，可与网盘数据同步
  --network bridge \
  --restart unless-stopped \
  wuanqicll/cloud-save-max:latest
```

docker-compose.yml

```yaml
name: cloud-save-max
services:
  cloud-save-max:
    image: wuanqicll/cloud-save-max:latest
    container_name: cloud-save-max
    network_mode: bridge
    ports:
      - 5115:5115 # 映射端口，:前的可以改，即部署后访问的端口，:后的不可改
    restart: unless-stopped
    volumes:
      - ./cloud-save-max/data:/app/backend/data # 必须，配置持久化
      - ./cloud-save-max/media:/media # 可选，模块alist_strm_gen生成strm使用
      - ./cloud-save-max/strm:/strm # 可选，项目本身生成strm使用
      - ./cloud-save-max/nasfile:/app/backend/data/sync/nasfile # 可选，用于同步任务Local使用，可与网盘数据同步
```

管理地址：<http://yourhost:5115>


| 环境变量             | 默认         | 备注                           |
| ---------------- | ---------- | ---------------------------- |
| `PORT`           | `5115`     | 管理后台                       |
| `DEBUG`          | `0`        | 开启调试模式，打印更多日志信息 |
| `DRAMA_RUNTIME_RETRY_MAX_ATTEMPTS`        | `0`        | 最大重试次数，默认3次，0表示不重试 |
| `DRAMA_RUNTIME_RETRY_BACKOFF_SECONDS`        | `1`        | 重试延迟时间，默认1秒 |
| `DRAMA_RUNTIME_RETRY_MAX_BACKOFF_SECONDS`        | `8`        | 最大重试延迟时间，默认8秒 |
| `DRAMA_RUNTIME_RETRY_JITTER_RATIO`        | `0.2`        | 重试延迟随机化比例，默认0.2 |

### 正则处理示例

| pattern                        | replace                 | 效果                                                 |
| ------------------------------ | ----------------------- | -------------------------------------------------- |
| `.*`                           | <br />                  | 无脑转存所有文件，不整理                                       |
| `\.mp4$`                       | <br />                  | 转存所有 `.mp4` 后缀的文件                                  |
| `^【电影TT】花好月圆(\d+)\.(mp4\|mkv)` | `\1.\2`                 | 【电影TT】花好月圆01.mp4 → 01.mp4 |
| `^(\d+)\.mp4`                  | `S02E\1.mp4`            | 01.mp4 → S02E01.mp4             |
| `TV_REGEX`                          | <br />                  | 魔法匹配剧集文件                                  |
| `^(\d+)\.mp4`                  | `{TASKNAME}.S02E\1.mp4` | 01.mp4 → 任务名.S02E01.mp4                            |

**默认规则**：在已配置TMDB后，留空则增加兜底智能匹配。

更多正则使用说明：[正则处理教程](https://github.com/ozoo0/cloud-auto-save-x/wiki/正则处理教程)

> \[!TIP]
>
> **魔法匹配和魔法变量**：在正则处理中，我们定义了一些“魔法匹配”模式，如果 表达式 的值以 $ 开头且 替换式 留空，程序将自动使用预设的正则表达式进行匹配和替换。
>
> 更多说明请看[魔法匹配和魔法变量](https://github.com/ozoo0/cloud-auto-save-x/wiki/魔法匹配和魔法变量)

### 刷新媒体库

在有新转存时，可触发完成相应功能，如自动刷新媒体库、生成 .strm 文件等。配置指南：[插件配置](https://github.com/ozoo0/cloud-auto-save-x/wiki/插件配置)

媒体库模块以插件的方式的集成，如果你有兴趣请参考[插件开发指南](https://github.com/ozoo0/cloud-auto-save-x/tree/main/plugins)。

### 更多使用技巧

请参考 Wiki ：[使用技巧集锦](https://github.com/ozoo0/cloud-auto-save-x/wiki/使用技巧集锦)


### 声明

本项目基于个人兴趣开发并开源，仅供学习与交流使用，不包含任何破解行为，只是对网盘官方 API 的封装与调用，所有数据均来源于各大网盘官方，本人不对网盘内容及官方 API 变更所导致的任何后果负责。

### 致谢

感谢 [Cp0204](https://github.com/Cp0204) 的开源贡献。
感谢 [OzoO0](https://github.com/OzoO0) 的开源贡献。
---
## ❤️ 支持项目

如果觉得这个项目对你有帮助，你可以通过以下方式支持我：

1. ⭐ 给项目点个 Star，让更多的人看到
2. 📢 分享给更多有需要的朋友