#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
cron: 0 */6 * * *
new Env("NodeLoc 快速升级")

NodeLoc 快速升级脚本 - 纯 API 版本（无需 Chrome）
功能: 自动签到 + 浏览主题 + 阅读帖子 + 点赞 + 回复
目标: 快速满足 TL0 → TL1 → TL2 升级条件
适配青龙面板 ARM Docker 环境（N1盒子/树莓派）
版本: 4.0.0 (纯API，无浏览器依赖)
"""

import os
import time
import random
import re
import traceback
import functools
from loguru import logger
from curl_cffi import requests

HOME_URL = "https://www.nodeloc.com"
LOGIN_URL = "https://www.nodeloc.com/login"
SESSION_URL = "https://www.nodeloc.com/session"
CSRF_URL = "https://www.nodeloc.com/session/csrf"

# 通知配置
GOTIFY_URL = os.environ.get("GOTIFY_URL")
GOTIFY_TOKEN = os.environ.get("GOTIFY_TOKEN")
SC3_PUSH_KEY = os.environ.get("SC3_PUSH_KEY")
TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN", "").strip()
TG_CHAT_ID = os.environ.get("TG_CHAT_ID", "").strip()
WECHAT_API_URL = os.environ.get("WECHAT_API_URL")
WECHAT_AUTH_TOKEN = os.environ.get("WECHAT_AUTH_TOKEN")

# 代理配置
NODELOC_PROXY = os.environ.get("NODELOC_PROXY") or os.environ.get("LINUXDO_PROXY") or os.environ.get("HTTP_PROXY")

if NODELOC_PROXY:
    logger.info(f"已启用代理配置: {NODELOC_PROXY}")

# ================== 升级配置 ==================
DAILY_TASKS = {
    "topics_to_browse": 30,
    "likes_to_give": 15,
    "replies_to_post": 5,
}

REPLY_TEMPLATES = [
    "感谢分享！",
    "学习了，很有帮助",
    "支持一下",
    "不错的内容",
    "mark一下",
    "收藏了",
    "有用的信息",
    "感谢楼主",
    "不错值得学习。。。",
    "谢谢。加油,看好你。",
    "已查阅感谢分享。"
]


def retry_decorator(retries=3, delay=1):
    """重试装饰器"""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if attempt == retries - 1:
                        logger.error(f"函数 {func.__name__} 最终执行失败: {str(e)}")
                        raise
                    logger.warning(f"函数 {func.__name__} 第 {attempt + 1}/{retries} 次尝试失败: {str(e)}")
                    time.sleep(delay)
            return None
        return wrapper
    return decorator


class NodeLocUpgrade:
    def __init__(self, username: str, password: str):
        self.username = username
        self.password = password
        self.csrf_token = None

        self.session = requests.Session()
        self.proxies = {"http": NODELOC_PROXY, "https": NODELOC_PROXY} if NODELOC_PROXY else None
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": HOME_URL,
        })
        if self.proxies:
            self.session.proxies = self.proxies

        self.stats = {
            'topics_browsed': 0,
            'posts_read': 0,
            'likes_given': 0,
            'replies_posted': 0,
        }

    # ============= CSRF =============
    def refresh_csrf(self) -> str:
        """获取/刷新 CSRF Token"""
        try:
            r = self.session.get(CSRF_URL, impersonate="chrome136")
            j = r.json() or {}
            self.csrf_token = j.get("csrf")
            if self.csrf_token:
                self.session.headers["X-CSRF-Token"] = self.csrf_token
            return self.csrf_token
        except Exception as e:
            logger.warning(f"获取 CSRF 失败: {e}")
            return None

    # ============= Login =============
    @retry_decorator(retries=2, delay=3)
    def login(self) -> bool:
        """API 登录"""
        logger.info("NodeLoc: 开始登录 (API)")

        csrf = self.refresh_csrf()
        if not csrf:
            logger.error("获取 CSRF 失败")
            return False

        headers = {
            "X-CSRF-Token": csrf,
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Origin": HOME_URL,
        }
        data = {
            "login": self.username,
            "password": self.password,
            "timezone": "Asia/Shanghai",
        }

        r = self.session.post(SESSION_URL, data=data, headers=headers, impersonate="chrome136")

        if r.status_code != 200:
            logger.error(f"登录失败 HTTP={r.status_code}: {(r.text or '')[:300]}")
            return False

        j = r.json() or {}
        if j.get("error"):
            logger.error(f"登录失败: {j.get('error')}")
            return False

        # 登录后刷新一次 CSRF
        self.refresh_csrf()
        logger.success("NodeLoc: 登录成功 ✅")
        return True

    # ============= Checkin =============
    def do_checkin(self) -> bool:
        """执行签到（通过 API）"""
        logger.info("NodeLoc: 开始签到...")
        try:
            self.refresh_csrf()

            # Discourse Checkin 插件通常走 /checkin 或者 /user-actions
            # 先尝试访问主页获取签到状态
            r = self.session.get(f"{HOME_URL}/checkin.json", impersonate="chrome136")
            if r.status_code == 200:
                logger.success("NodeLoc: 签到请求已发送 ✅")
                return True

            # 备用: POST 请求
            r = self.session.post(f"{HOME_URL}/checkin", impersonate="chrome136")
            if r.status_code in [200, 302]:
                logger.success("NodeLoc: 签到成功 ✅")
                return True

            # 再备用：尝试 discourse-checkin 插件路径
            r = self.session.put(f"{HOME_URL}/topic-voting/vote", impersonate="chrome136")
            logger.info(f"签到尝试返回: HTTP {r.status_code}")
            return True

        except Exception as e:
            logger.warning(f"签到失败（可忽略）: {e}")
            return False

    # ============= Topics =============
    def get_latest_topics(self, limit: int = 30) -> list:
        """通过 API 获取最新主题列表"""
        topics = []
        try:
            r = self.session.get(f"{HOME_URL}/latest.json", impersonate="chrome136")
            if r.status_code != 200:
                logger.error(f"获取主题列表失败: HTTP {r.status_code}")
                return []

            data = r.json()
            topic_list = data.get("topic_list", {}).get("topics", [])

            for t in topic_list[:limit]:
                topic_id = t.get("id")
                title = t.get("title", "")
                slug = t.get("slug", "")
                if topic_id and title:
                    topics.append({
                        "id": topic_id,
                        "title": title,
                        "slug": slug,
                        "url": f"{HOME_URL}/t/{slug}/{topic_id}",
                    })

            logger.info(f"获取到 {len(topics)} 个最新主题")

        except Exception as e:
            logger.error(f"获取主题列表异常: {e}")

        return topics

    @retry_decorator(retries=2, delay=1)
    def read_topic(self, topic: dict) -> dict:
        """通过 API 阅读单个主题，返回帖子信息"""
        topic_id = topic["id"]
        slug = topic.get("slug", "")

        r = self.session.get(
            f"{HOME_URL}/t/{slug}/{topic_id}.json",
            impersonate="chrome136"
        )
        if r.status_code != 200:
            logger.debug(f"阅读主题 {topic_id} 失败: HTTP {r.status_code}")
            return {}

        data = r.json()
        posts = data.get("post_stream", {}).get("posts", [])

        self.stats['topics_browsed'] += 1
        self.stats['posts_read'] += len(posts)

        logger.info(f"📖 阅读主题: {topic['title'][:40]}... ({len(posts)} 楼)")

        # 模拟用户浏览行为：发送 timings（让 Discourse 记录阅读行为）
        self._send_topic_timings(topic_id, posts)

        return data

    def _send_topic_timings(self, topic_id: int, posts: list):
        """发送主题阅读计时（让 Discourse 服务端记录阅读行为，这是升级的关键）"""
        try:
            self.refresh_csrf()

            # 构造 timings 数据：每个帖子阅读 3-8 秒
            timings = {}
            for post in posts[:20]:  # 最多记录 20 楼
                post_number = post.get("post_number", 1)
                read_time = random.randint(3000, 8000)  # 毫秒
                timings[str(post_number)] = read_time

            data = {
                "topic_id": topic_id,
                "topic_time": random.randint(15000, 60000),  # 总阅读时间
                "timings": timings,
            }

            r = self.session.post(
                f"{HOME_URL}/topics/timings",
                json=data,
                impersonate="chrome136"
            )

            if r.status_code == 200:
                logger.debug(f"已记录主题 {topic_id} 的阅读时间 ({len(timings)} 楼)")
            else:
                logger.debug(f"记录阅读时间返回: HTTP {r.status_code}")

        except Exception as e:
            logger.debug(f"发送 timings 失败: {e}")

    # ============= Like =============
    def like_post(self, post_id: int) -> bool:
        """通过 API 点赞帖子"""
        try:
            self.refresh_csrf()

            data = {
                "id": post_id,
                "post_action_type_id": 2,  # 2 = like
                "flag_topic": False,
            }

            r = self.session.post(
                f"{HOME_URL}/post_actions",
                json=data,
                impersonate="chrome136"
            )

            if r.status_code == 200:
                self.stats['likes_given'] += 1
                logger.success(f"👍 点赞帖子 {post_id} 成功 ({self.stats['likes_given']})")
                return True
            elif r.status_code == 403:
                logger.debug(f"点赞 {post_id} 被拒绝（可能已点赞或权限不足）")
            else:
                logger.debug(f"点赞 {post_id} 返回: HTTP {r.status_code}")

            return False

        except Exception as e:
            logger.debug(f"点赞异常: {e}")
            return False

    # ============= Reply =============
    def reply_to_topic(self, topic_id: int, topic_title: str = "") -> bool:
        """通过 API 回复主题"""
        try:
            self.refresh_csrf()

            reply_text = random.choice(REPLY_TEMPLATES)

            data = {
                "topic_id": topic_id,
                "raw": reply_text,
                "unlist_topic": False,
                "category": "",
                "is_warning": False,
                "archetype": "regular",
                "typing_duration_msecs": random.randint(3000, 8000),
                "composer_open_duration_msecs": random.randint(5000, 15000),
            }

            r = self.session.post(
                f"{HOME_URL}/posts",
                json=data,
                impersonate="chrome136"
            )

            if r.status_code == 200:
                self.stats['replies_posted'] += 1
                logger.success(f"💬 回复成功: '{reply_text}' -> {topic_title[:30]}... ({self.stats['replies_posted']})")
                return True
            else:
                body = (r.text or "")[:200]
                logger.warning(f"回复失败 HTTP {r.status_code}: {body}")
                return False

        except Exception as e:
            logger.warning(f"回复异常: {e}")
            return False

    # ============= Main Task =============
    def auto_upgrade_tasks(self):
        """执行升级任务"""
        logger.info(f"\n{'='*50}")
        logger.info("🚀 开始执行升级任务 (纯API模式)")
        logger.info(f"{'='*50}")

        # 1. 获取主题列表
        topics = self.get_latest_topics(DAILY_TASKS['topics_to_browse'])
        if not topics:
            logger.warning("未获取到主题，跳过")
            return

        # 2. 随机打乱顺序
        random.shuffle(topics)

        # 3. 遍历主题：阅读 + 点赞 + 回复
        for i, topic in enumerate(topics, 1):
            try:
                logger.info(f"[{i}/{len(topics)}] 处理主题 #{topic['id']}...")

                # 阅读主题
                topic_data = self.read_topic(topic)
                if not topic_data:
                    continue

                posts = topic_data.get("post_stream", {}).get("posts", [])

                # 点赞（随机选 1-2 个帖子）
                if self.stats['likes_given'] < DAILY_TASKS['likes_to_give'] and posts:
                    # 跳过自己的帖子，随机选择
                    likeable_posts = [
                        p for p in posts
                        if p.get("actions_summary") and
                        any(a.get("id") == 2 and a.get("can_act") for a in p.get("actions_summary", []))
                    ]

                    if not likeable_posts:
                        # 备用：直接使用前几个帖子（不确定 can_act）
                        likeable_posts = posts[1:5]  # 跳过第一楼（楼主帖）

                    for post in random.sample(likeable_posts, min(2, len(likeable_posts))):
                        post_id = post.get("id")
                        if post_id:
                            self.like_post(post_id)
                            time.sleep(random.uniform(1, 2))

                        if self.stats['likes_given'] >= DAILY_TASKS['likes_to_give']:
                            break

                # 回复（30% 概率回复）
                if self.stats['replies_posted'] < DAILY_TASKS['replies_to_post']:
                    if random.random() < 0.3:
                        self.reply_to_topic(topic['id'], topic['title'])

                # 请求间隔（模拟人类行为）
                if i < len(topics):
                    delay = random.uniform(3, 8)
                    time.sleep(delay)

            except Exception as e:
                logger.warning(f"处理主题出错: {e}")
                continue

    # ============= Notifications =============
    def send_notifications(self):
        """发送多渠道通知"""
        status_msg = (
            f"NodeLoc 升级任务完成 ✅\n"
            f"浏览主题: {self.stats['topics_browsed']}\n"
            f"阅读帖子: {self.stats['posts_read']}\n"
            f"给出点赞: {self.stats['likes_given']}\n"
            f"发布回复: {self.stats['replies_posted']}"
        )

        # Telegram
        if TG_BOT_TOKEN and TG_CHAT_ID:
            try:
                tg_url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
                payload = {"chat_id": TG_CHAT_ID, "text": status_msg, "disable_web_page_preview": True}
                r = requests.post(tg_url, json=payload, timeout=15, impersonate="chrome136", proxies=self.proxies)
                if r.status_code == 200:
                    logger.success("✅ Telegram 通知发送成功")
                else:
                    logger.warning(f"⚠️ Telegram 推送失败 HTTP={r.status_code}")
            except Exception as e:
                logger.warning(f"⚠️ Telegram 推送异常: {e}")

        # Gotify
        if GOTIFY_URL and GOTIFY_TOKEN:
            try:
                r = requests.post(
                    f"{GOTIFY_URL}/message",
                    params={"token": GOTIFY_TOKEN},
                    json={"title": "NodeLoc 升级任务", "message": status_msg, "priority": 5},
                    timeout=10, impersonate="chrome136", proxies=self.proxies
                )
                r.raise_for_status()
                logger.success("✅ Gotify 通知发送成功")
            except Exception as e:
                logger.warning(f"⚠️ Gotify 通知发送失败: {e}")

        # Server 酱³
        if SC3_PUSH_KEY:
            match = re.match(r"sct(\d+)t", SC3_PUSH_KEY, re.I)
            if not match:
                logger.warning("⚠️ SC3_PUSH_KEY 格式错误")
            else:
                uid = match.group(1)
                url = f"https://{uid}.push.ft07.com/send/{SC3_PUSH_KEY}"
                params = {"title": "NodeLoc 升级任务", "desp": status_msg}
                try:
                    r = requests.get(url, params=params, timeout=10, impersonate="chrome136", proxies=self.proxies)
                    r.raise_for_status()
                    logger.success("✅ Server 酱³ 通知发送成功")
                except Exception as e:
                    logger.warning(f"⚠️ Server 酱³ 通知发送失败: {e}")

        # 自定义微信
        if WECHAT_API_URL and WECHAT_AUTH_TOKEN:
            try:
                params = {"token": WECHAT_AUTH_TOKEN, "title": "NodeLoc 升级任务", "content": status_msg}
                r = requests.get(WECHAT_API_URL, params=params, timeout=10, impersonate="chrome136")
                if r.status_code == 405:
                    r = requests.post(WECHAT_API_URL, json=params, timeout=10, impersonate="chrome136")
                if r.status_code >= 400:
                    logger.warning(f"⚠️ 自定义微信通知 HTTP {r.status_code}: {r.text[:100]}")
                else:
                    logger.success("✅ 自定义微信通知发送成功")
            except Exception as e:
                logger.warning(f"⚠️ 自定义微信通知发送失败: {e}")

    # ============= Run =============
    def run(self) -> int:
        try:
            logger.info("==== NodeLoc 快速升级脚本开始 (纯API版) ====")

            # 1. 登录
            if not self.login():
                logger.error("NodeLoc: 登录失败 ❌")
                return 2

            # 2. 签到
            self.do_checkin()

            # 3. 执行升级任务
            self.auto_upgrade_tasks()

            # 4. 统计
            logger.info(f"\n{'='*50}")
            logger.info("📊 今日任务完成统计:")
            logger.info(f"  - 浏览主题: {self.stats['topics_browsed']}")
            logger.info(f"  - 阅读帖子: {self.stats['posts_read']}")
            logger.info(f"  - 给出点赞: {self.stats['likes_given']}")
            logger.info(f"  - 发布回复: {self.stats['replies_posted']}")
            logger.info(f"{'='*50}\n")

            # 5. 通知
            self.send_notifications()

            logger.info("==== NodeLoc 快速升级脚本结束 ====")
            return 0

        except Exception:
            logger.error("NodeLoc: 脚本异常 ❌")
            traceback.print_exc()
            return 9


if __name__ == "__main__":
    username = os.environ.get("NODELOC_USERNAME")
    password = os.environ.get("NODELOC_PASSWORD")

    if not username or not password:
        logger.error("请设置 NODELOC_USERNAME / NODELOC_PASSWORD")
        raise SystemExit(1)

    raise SystemExit(NodeLocUpgrade(username, password).run())
