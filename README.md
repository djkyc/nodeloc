# nodeloc
docker 青龙定时升级L3
# NodeLoc 快速升级脚本使用指南（Selenium 版本）

## 📋 版本说明

这是 **Selenium 版本**，使用 **用户名和密码** 登录，适合青龙面板 ARM Docker 环境。

### 与 Cookie 版本的区别

| 特性 | Selenium 版本 | Cookie 版本 |
|------|--------------|-------------|
| 登录方式 | 用户名 + 密码 | Cookie |
| 依赖 | Selenium + Chrome | requests + BeautifulSoup |
| 资源占用 | 较高（需要浏览器） | 较低 |
| 稳定性 | 更稳定（真实浏览器） | 依赖 Cookie 有效期 |
| 适用场景 | 青龙面板 | 轻量级环境 |

## 🚀 快速开始

### 1. 安装依赖

在青龙面板终端ssh 执行：



```bash
# 安装 Python 依赖
pip3 install loguru curl-cffi selenium

# 安装 Chrome/Chromium 和 ChromeDriver
# ARM64 Docker 通常已预装，如果没有：
apk-get update
apk-get install -y chromium chromium-driver
```

### 2. 配置环境变量

在青龙面板 **环境变量** 中添加：

| 变量名 | 说明 | 示例 |
|--------|------|------|
| `NODELOC_USERNAME` | NodeLoc 用户名 | `your_username` |
| `NODELOC_PASSWORD` | NodeLoc 密码 | `your_password` |
| `TG_BOT_TOKEN` | Telegram Bot Token（可选） | `123456:ABC...` |
| `TG_CHAT_ID` | Telegram Chat ID（可选） | `123456789` |

### 3. 上传脚本

将 `nodeloc_upgrade_selenium.py` 上传到青龙面板的 `/ql/scripts/` 目录

### 4. 添加定时任务

在青龙面板 **定时任务** 中添加：

- **名称**：NodeLoc 快速升级（Selenium）
- **命令**：`task /ql/data/scripts/nodeloc_upgrade_selenium.py`
- **定时规则**：`0 9 * * *`（每天早上 9 点）
---
青龙面板使用
注意：如果是docker容器创建的青龙，请使用whyour/qinglong:debian镜像，latest（alpine）版本可能无法安装部分依赖

依赖安装

## 第二种方法：安装Python依赖

进入青龙面板 -> 依赖管理 -> 安装依赖
依赖类型选择python3
自动拆分选择 是

名称填写
`loguru curl-cffi selenium`

点击确定

## 安装 linux chromium 依赖

青龙面板 -> 依赖管理 -> 安装Linux依赖

名称填`chromium`

若安装失败，可能需要执行apt update更新索引（若使用docker则需进入docker容器执行）
添加仓库

## 进入青龙面板 -> 订阅管理 -> 创建订阅

依次在对应的字段填入内容（未提及的不填）：

名称：nodeloc签到升级

类型：公开仓库

链接：https://github.com/doveppp/linuxdo-checkin.git

分支：main

定时类型：crontab

定时规则(拉取上游代码的时间，一天二次，可以自由调整频率): 0 9 * * * /0 21 * * *    #-早晚上一次

配置环境变量

进入青龙面板 -> 环境变量 -> 创建变量

需要配置以下变量：

`NODELOC_USERNAME` #不是登陆用户名---可进网站查你取的名字。

`NODELOC_PASSWORD` 登陆密码

---
## ⚙️ 配置调整

### 每日任务量配置

编辑脚本中的 `DAILY_TASKS` 配置：

```python
DAILY_TASKS = {
    "topics_to_browse": 20,    # 每日浏览主题数（建议 10-30）
    "posts_to_read": 50,       # 每日阅读帖子数（建议 30-100）
    "likes_to_give": 10,       # 每日点赞数（建议 5-15）
    "replies_to_post": 3,      # 每日回复数（建议 0-5，谨慎设置）
}
```

### 回复内容自定义

修改 `REPLY_TEMPLATES` 列表：

```python
REPLY_TEMPLATES = [
    "感谢分享！",
    "学习了，很有帮助",
    "支持一下",
    # 添加更多个性化回复...
]
```

## 📊 运行效果

```
==== NodeLoc 快速升级脚本开始 ====
NodeLoc:开始登录(API)
NodeLoc:登录成功
NodeLoc:启动 Chrome
使用 Chrome 路径:/usr/bin/chromium
NodeLoc:Chrome 启动成功
NodeLoc:同步 Cookie 到浏览器
已设置 3 个 Cookie
NodeLoc:开始签到
找到签到按钮,准备点击
NodeLoc:签到成功 ✅

==================================================
🚀 开始执行升级任务
==================================================
📋 获取最新主题列表...
使用选择器 '.topic-list-item' 找到 25 个主题
共找到 20 个主题
[1/20] 处理主题...
浏览主题: 关于服务器配置的讨论...
👍 点赞 2 次 (总计:2)
[2/20] 处理主题...
浏览主题: VPS 推荐分享...
👍 点赞 1 次 (总计:3)
💬 回复成功 (总计:1)
...

==================================================
📊 今日任务完成统计:
  - 浏览主题: 20
  - 阅读帖子: 20
  - 给出点赞: 10
  - 发布回复: 3
==================================================

NodeLoc 升级任务完成 ✅
浏览主题: 20
阅读帖子: 20
给出点赞: 10
发布回复: 3
==== NodeLoc 快速升级脚本结束 ====
```

## 🔧 故障排查

### 1. Chrome 启动失败

**症状**：`未找到 Chrome/Chromium 可执行文件`

**解决方法**：
```bash
# 安装 Chromium
apt-get update
apt-get install -y chromium chromium-driver

# 或者手动指定路径
which chromium
```

### 2. ChromeDriver 版本不匹配

**症状**：`session not created: This version of ChromeDriver only supports Chrome version XX`

**解决方法**：
```bash
# 检查 Chrome 版本
chromium --version

# 安装匹配的 ChromeDriver
apt-get install -y chromium-driver
```

### 3. 登录失败

**症状**：`NodeLoc:登录失败 error=...`

**解决方法**：
1. 检查用户名和密码是否正确
2. 确认环境变量 `NODELOC_USERNAME` 和 `NODELOC_PASSWORD` 已设置
3. 检查账号是否被封禁

### 4. 未找到签到按钮

**症状**：`未找到签到按钮`

**解决方法**：
- 检查 `/ql/data/scripts/nodeloc_upgrade_debug.html` 和 `.png` 文件
- 可能是网站结构变化，需要更新选择器

## 📈 升级策略

### 快速升级到 TL1（1-2 周）

```bash
# 定时规则：每天一次
0 9 * * *
```

配置：
```python
DAILY_TASKS = {
    "topics_to_browse": 15,
    "posts_to_read": 50,
    "likes_to_give": 5,
    "replies_to_post": 0,  # 不自动回复
}
```

### 稳定升级到 TL2（1-2 个月）

```bash
# 定时规则：每天两次
0 9,21 * * *
```

配置：
```python
DAILY_TASKS = {
    "topics_to_browse": 20,
    "posts_to_read": 50,
    "likes_to_give": 10,
    "replies_to_post": 3,  # 少量回复
}
```

> [!IMPORTANT]
> **访问天数** 是 TL2 的硬性要求，必须至少连续访问 30 天

## 🔒 安全提示

1. **不要分享账号密码**
2. **控制任务频率**：避免过度自动化
3. **谨慎使用回复功能**：重复内容可能被标记为垃圾
4. **配合真实使用**：不要完全依赖脚本

## 📝 与原版脚本的区别

| 功能 | 原版 `nodeloc_selenium.py` | 升级版 `nodeloc_upgrade_selenium.py` |
|------|---------------------------|-------------------------------------|
| 签到 | ✅ | ✅ |
| 自动回复 | ✅ 3-5 个主题 | ✅ 可配置（默认 3 个） |
| 浏览主题 | ❌ | ✅ 20 个主题 |
| 自动点赞 | ❌ | ✅ 10 次点赞 |
| 统计数据 | ❌ | ✅ 详细统计 |
| 升级导向 | ❌ | ✅ 针对 TL1/TL2 优化 |

## ❓ 常见问题

**Q: 为什么使用 Selenium 而不是 requests？**  
A: Selenium 模拟真实浏览器，更稳定，不容易被检测为机器人。

**Q: 可以同时运行多个账号吗？**  
A: 可以，但需要为每个账号创建单独的定时任务和环境变量。

**Q: 脚本会被封号吗？**  
A: 已加入随机延迟和行为模拟，但仍需控制任务量。

**Q: 为什么回复功能默认只回复 30% 的主题？**  
A: 为了避免过度回复被识别为机器人，脚本随机选择部分主题回复。

---

**作者**：djkyc
**版本**：3.0  仅提供技术逻辑交流
**更新时间**：2026-01-24
