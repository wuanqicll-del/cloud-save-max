<div align="center">

# Cloud Save Max

基于 [cloud-auto-save-x](https://github.com/OzoO0/cloud-auto-save-x) v1.0.9版本改造的网盘自动转存工具

当前版本：`26.7.2`

[![GitHub releases](https://img.shields.io/github/v/release/wuanqicll-del/cloud-save-max?logo=github)](https://github.com/wuanqicll-del/cloud-save-max)
[![Docker pulls](https://img.shields.io/docker/pulls/wuanqicll/cloud-save-max?logo=docker&logoColor=white)](https://hub.docker.com/r/wuanqicll/cloud-save-max)

</div>

## 项目简介

Cloud Save Max 是基于 [cloud-auto-save-x](https://github.com/OzoO0/cloud-auto-save-x) v1.0.9版本进行了大量改造的网盘自动转存工具，保留了原项目大部分功能，并新增了大量实用特性。

## 新增功能

### 搜索与筛选

- 🔍 **搜索筛选词/过滤词**：搜索结果支持关键词筛选和过滤，支持"包含所有"和"包含任意"两种模式
- 📅 **搜索时间过滤**：按发布时间过滤搜索结果
- 👤 **分享者黑白名单**：支持优选和屏蔽特定分享者，搜索结果可只看优选分享者

### 文件夹与文件过滤

- 📁 **文件夹筛选/过滤**：按文件夹名称筛选或过滤，支持"包含所有"和"包含任意"模式
- 📅 **文件夹时间过滤**：按文件夹创建时间过滤
- 📄 **文件关键词筛选/过滤**：按文件名关键词筛选或过滤，支持模式切换
- 📅 **文件时间过滤**：按文件创建时间过滤
- 📦 **最小文件大小**：过滤小于指定大小的文件
- 🔄 **自动更新文件时间过滤**：追剧进度追上最新集数时自动更新文件时间过滤

### 自动换链

- 🔗 **智能换链**：链接失效或当前集数不是最新时自动触发换链
- ✅ **换链验证**：自动验证链接有效性，优选分享者优先
- 🔤 **换链重命名**：换链后自动应用重命名规则

### 任务模板

- 📋 **模板保存**：将常用配置保存为模板，快速应用
- 🏷️ **模板管理**：支持创建、编辑、删除模板
- 🔧 **模板内容**：包含筛选词、过滤词、重命名规则、文件大小等配置

### 预览与操作

- 👁️ **预览窗优化**：显示文件筛选标记、分享者信息、文件时间
- ❌ **红叉标记**：清晰显示文件被过滤的原因
- 📊 **连贯性检查**：支持部分连贯，支持 zip 压缩包格式

### 重命名与变量

- 📝 **魔法变量扩展**：新增 `{E0}`、`{E2}` 变量
- 🎯 **内置规则选择**：支持从预设规则中选择重命名规则
- 📐 **正则替换**：支持自定义正则表达式重命名

### 其他增强

- 🗓️ **追剧面板**：支持直接创建同步任务，显示当前集数/最新集数
- 📡 **外部脚本触发**：支持通过外部脚本触发扫描
- 💾 **缓存优化**：搜索和验证结果缓存
- ⚙️ **系统设置重构**：更清晰的设置页面布局
- 🗜️ **自动解压**：解压后自动移动到保存目录并重命名
- 🎬 **TMDB 匹配**：名称匹配改为子串匹配

---

## 项目简介（原项目）

<div align="center">

![cloud-logo](img/icon.png)

# 网盘自动转存

网盘签到、自动转存、命名整理、发推送提醒、刷新媒体库一条龙，内置自动修复异常任务能力。

</div>

> ⛔️⛔️⛔️ 注意！资源不会每时每刻更新，**严禁设定过高的定时运行频率！** 以免账号风控和给网盘服务器造成不必要的压力。雪山崩塌，每一片雪花都有责任！

### 原项目简介

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

### 原项目自动转存功能

- 分享链接自动识别资源存放文件夹
- 转存任务文件智能重命名（需配置TMDB API密钥）
- 智能搜索资源并自动填充（集成 CloudSaver、PanSou，支持有效性检查、失效过滤）
- 支持自动修复异常任务（如分享链接失效、账号被限流等）
- 支持自动解压压缩包（仅限夸克高级会员）
- 支持一次性转存任务

### 原项目部署

#### Docker 部署

Docker 部署提供 WebUI 进行管理配置，部署命令：

```shell
docker run -d \
  --name cloud-save-max \
  -p 5115:5115 \
  -p 5225:5225 \
  -v ./cloud-save-max/data:/app/backend/data \
  -v ./cloud-save-max/media:/media \
  -v ./cloud-save-max/strm:/strm \
  -v ./cloud-save-max/nasfile:/app/backend/data/sync/nasfile \
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
      - 5115:5115
      - 5225:5225
    restart: unless-stopped
    volumes:
      - ./cloud-save-max/data:/app/backend/data
      - ./cloud-save-max/media:/media
      - ./cloud-save-max/strm:/strm
      - ./cloud-save-max/nasfile:/app/backend/data/sync/nasfile
```

管理地址：<http://yourhost:5115>

版本格式：`年.月.日`，例如 `26.7.2` 表示 2026年7月2日

| 标签 | 说明 |
|:---:|:---:|
| `latest` | 最新版本 |
| `26.7.2` | 指定版本 |

| 环境变量             | 默认         | 备注                           |
| ---------------- | ---------- | ---------------------------- |
| `PORT`           | `5115`     | 管理后台/302端口                       |
| `REVERSE_PORT`   | `5225`     | 反代端口                       |
| `DEBUG`          | `0`        | 开启调试模式，打印更多日志信息 |
| `DRAMA_RUNTIME_RETRY_MAX_ATTEMPTS`        | `0`        | 最大重试次数，默认3次，0表示不重试 |
| `DRAMA_RUNTIME_RETRY_BACKOFF_SECONDS`        | `1`        | 重试延迟时间，默认1秒 |
| `DRAMA_RUNTIME_RETRY_MAX_BACKOFF_SECONDS`        | `8`        | 最大重试延迟时间，默认8秒 |
| `DRAMA_RUNTIME_RETRY_JITTER_RATIO`        | `0.2`        | 重试延迟随机化比例，默认0.2 |

### 原项目正则处理示例

| pattern                        | replace                 | 效果                                                 |
| ------------------------------ | ----------------------- | -------------------------------------------------- |
| `.*`                           | <br />                  | 无脑转存所有文件，不整理                                       |
| `\.mp4$`                       | <br />                  | 转存所有 `.mp4` 后缀的文件                                  |
| `^【电影TT】花好月圆(\d+)\.(mp4\|mkv)` | `\1.\2`                 | 【电影TT】花好月圆01.mp4 → 01.mp4 |
| `^(\d+)\.mp4`                  | `S02E\1.mp4`            | 01.mp4 → S02E01.mp4             |
| `TV_REGEX`                          | <br />                  | 魔法匹配剧集文件                                  |
| `^(\d+)\.mp4`                  | `{TASKNAME}.S02E\1.mp4` | 01.mp4 → 任务名.S02E01.mp4                            |

**默认规则**：在已配置TMDB后，留空则增加兜底智能匹配。

> **魔法匹配和魔法变量**：在正则处理中，我们定义了一些"魔法匹配"模式，如果 表达式 的值以 $ 开头且 替换式 留空，程序将自动使用预设的正则表达式进行匹配和替换。

### 原项目刷新媒体库

在有新转存时，可触发完成相应功能，如自动刷新媒体库、生成 .strm 文件等。

### 原项目声明

本项目基于个人兴趣开发并开源，仅供学习与交流使用，不包含任何破解行为，只是对网盘官方 API 的封装与调用，所有数据均来源于各大网盘官方，本人不对网盘内容及官方 API 变更所导致的任何后果负责。

### 原项目致谢

本项目参考 [Cp0204/quark-auto-save](https://github.com/Cp0204/quark-auto-save/releases/tag/v0.8.4) 思路进行整体重构，感谢 [Cp0204](https://github.com/Cp0204) 的开源贡献。

---

## 致谢

感谢原项目作者 [OzoO0](https://github.com/OzoO0) 的开源贡献。

## 许可证

本项目基于 [AGPL-3.0](LICENSE) 许可证开源。
