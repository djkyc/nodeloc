#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NodeLoc 快速升级脚本 - Selenium 版本（用户名密码登录）
功能: 自动签到 + 浏览主题 + 阅读帖子 + 点赞 + 回复
目标: 快速满足 TL0 → TL1 → TL2 升级条件
适配青龙面板 ARM Docker 环境
作者: djkyc
版本: 3.0
"""

import os
import time
import random
import traceback
from loguru import logger
from curl_cffi import requests
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

HOME_URL = "https://www.nodeloc.com"
LOGIN_URL = "https://www.nodeloc.com/login"
SESSION_URL = "https://www.nodeloc.com/session"
CSRF_URL = "https://www.nodeloc.com/session/csrf"

DEBUG_HTML = "/ql/data/scripts/nodeloc_upgrade_debug.html"
DEBUG_PNG = "/ql/data/scripts/nodeloc_upgrade_debug.png"

# ================== 升级配置 ==================
# 每日任务配置（避免过度操作被封号）
DAILY_TASKS = {
    "topics_to_browse": 20,        # 每日浏览主题数
    "posts_to_read": 50,           # 每日阅读帖子数
    "likes_to_give": 10,           # 每日点赞数
    "replies_to_post": 3,          # 每日回复数（谨慎设置）
}

# 回复内容池（避免重复）
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


def tg_notify(text: str):
    """TG 推送"""
    token = os.environ.get("TG_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TG_CHAT_ID", "").strip()
    if not token or not chat_id:
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "disable_web_page_preview": True}
    try:
        r = requests.post(url, json=payload, timeout=15, impersonate="chrome136")
        if r.status_code != 200:
            logger.warning(f"TG 推送失败 HTTP={r.status_code}")
    except Exception as e:
        logger.warning(f"TG 推送异常:{e}")


class NodeLocUpgrade:
    def __init__(self, username: str, password: str):
        self.username = username
        self.password = password

        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "Accept-Language": "zh-CN,zh;q=0.9",
            }
        )

        self.driver = None
        self.stats = {
            'topics_browsed': 0,
            'posts_read': 0,
            'likes_given': 0,
            'replies_posted': 0,
        }

    # ---------------- Debug ----------------
    def _save_debug(self, reason: str):
        try:
            html = self.driver.page_source
            with open(DEBUG_HTML, "w", encoding="utf-8", errors="ignore") as f:
                f.write(html)
            logger.warning(f"[DEBUG] {reason}:已保存 HTML -> {DEBUG_HTML}")
        except Exception as e:
            logger.warning(f"[DEBUG] 保存 HTML 失败:{e}")

        try:
            self.driver.save_screenshot(DEBUG_PNG)
            logger.warning(f"[DEBUG] {reason}:已保存截图 -> {DEBUG_PNG}")
        except Exception as e:
            logger.warning(f"[DEBUG] 截图失败:{e}")

    # ---------------- Login (API) ----------------
    def login(self) -> bool:
        """API 登录获取 Cookie"""
        logger.info("NodeLoc:开始登录(API)")
        headers = {"X-Requested-With": "XMLHttpRequest", "Referer": LOGIN_URL}

        r = self.session.get(CSRF_URL, headers=headers, impersonate="chrome136")
        j = r.json() if r is not None else {}
        csrf = (j or {}).get("csrf")
        if not csrf:
            logger.error(f"NodeLoc:获取 CSRF 失败,返回={str(j)[:300]}")
            return False

        headers.update(
            {
                "X-CSRF-Token": csrf,
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "Origin": HOME_URL,
            }
        )

        data = {"login": self.username, "password": self.password, "timezone": "Asia/Shanghai"}
        r = self.session.post(SESSION_URL, data=data, headers=headers, impersonate="chrome136")

        if r.status_code != 200:
            logger.error(f"NodeLoc:登录失败 HTTP={r.status_code}")
            logger.error((r.text or "")[:500])
            return False

        j = r.json() or {}
        if j.get("error"):
            logger.error(f"NodeLoc:登录失败 error={j.get('error')}")
            return False

        logger.success("NodeLoc:登录成功")
        return True

    # ---------------- Browser (Selenium) ----------------
    def start_browser(self):
        """启动 Chrome 浏览器"""
        logger.info("NodeLoc:启动 Chrome")

        options = Options()
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--disable-web-security")
        options.add_argument("--lang=zh-CN")
        options.add_argument("--blink-settings=imagesEnabled=false")
        
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)
        
        # ARM64 修复:手动指定 chromium 路径
        chrome_candidates = [
            "/usr/bin/chromium",
            "/usr/bin/chromium-browser",
            "/usr/bin/google-chrome",
            "/usr/bin/google-chrome-stable",
        ]
        
        chrome_path = None
        for path in chrome_candidates:
            if os.path.exists(path):
                chrome_path = path
                break
        
        if not chrome_path:
            logger.error("未找到 Chrome/Chromium 可执行文件")
            raise RuntimeError("未找到 Chrome/Chromium")
        
        logger.info(f"使用 Chrome 路径:{chrome_path}")
        options.binary_location = chrome_path

        try:
            from selenium.webdriver.chrome.service import Service
            
            chromedriver_candidates = [
                "/usr/bin/chromedriver",
                "/usr/local/bin/chromedriver",
            ]
            
            chromedriver_path = None
            for path in chromedriver_candidates:
                if os.path.exists(path):
                    chromedriver_path = path
                    break
            
            if chromedriver_path:
                logger.info(f"使用 ChromeDriver 路径:{chromedriver_path}")
                service = Service(executable_path=chromedriver_path)
                self.driver = webdriver.Chrome(service=service, options=options)
            else:
                logger.warning("未找到 chromedriver,尝试自动查找")
                self.driver = webdriver.Chrome(options=options)
            
            logger.success("NodeLoc:Chrome 启动成功")
        except Exception as e:
            logger.error(f"Chrome 启动失败:{e}")
            raise

        # 移除 webdriver 标识
        try:
            self.driver.execute_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
            )
        except Exception:
            pass

    def sync_cookie_to_browser(self):
        """同步 Cookie 到浏览器"""
        logger.info("NodeLoc:同步 Cookie 到浏览器")
        
        try:
            self.driver.get(HOME_URL)
            time.sleep(2)
        except Exception as e:
            logger.error(f"访问主页失败:{e}")
            self._save_debug("访问主页失败")
            raise
        
        # 设置 Cookie
        for k, v in self.session.cookies.get_dict().items():
            try:
                self.driver.add_cookie({"name": k, "value": v, "domain": ".nodeloc.com"})
            except Exception as e:
                logger.warning(f"设置 Cookie {k} 失败:{e}")
        
        logger.info(f"已设置 {len(self.session.cookies)} 个 Cookie")

    def _wait_discourse_ready(self, timeout: int = 60):
        """等待 Discourse SPA 启动完成"""
        logger.info("等待 Discourse 应用启动...")
        
        for i in range(timeout):
            try:
                splash = self.driver.find_elements(By.CSS_SELECTOR, "#d-splash")
                if not splash:
                    logger.info(f"Discourse 启动完成(耗时 {i}秒)")
                    return True
                
                if splash[0].value_of_css_property("display") == "none":
                    logger.info(f"Discourse 启动完成(耗时 {i}秒)")
                    return True
                    
            except Exception:
                logger.info(f"Discourse 启动完成(耗时 {i}秒)")
                return True
            
            time.sleep(1)
        
        logger.warning(f"等待 {timeout}秒后 Discourse 仍未完全启动")
        return False

    # ---------------- Sign ----------------
    def do_checkin(self) -> bool:
        """执行签到"""
        logger.info("NodeLoc:开始签到")

        try:
            self.driver.get(HOME_URL)
            self._wait_discourse_ready(timeout=60)
            time.sleep(3)
            
            # 查找签到按钮
            buttons = self.driver.find_elements(By.CSS_SELECTOR, "button.checkin-button")
            if not buttons:
                logger.warning("未找到签到按钮")
                return False
            
            button = buttons[0]
            logger.info("找到签到按钮,准备点击")
            button.click()
            time.sleep(3)

            # 检查点击后的状态
            try:
                title_after = button.get_attribute("title") or ""
                aria_after = button.get_attribute("aria-label") or ""
                text_after = f"{title_after} {aria_after}".lower()
                
                if "已经签到过了" in text_after:
                    logger.success("NodeLoc:今天已签到 ✅")
                    return True
                
                if "签✓" in text_after or "已签到" in text_after:
                    logger.success("NodeLoc:签到成功 ✅")
                    return True
            except Exception:
                pass

            logger.success("NodeLoc:签到完成 ✅")
            return True
            
        except Exception as e:
            logger.error(f"签到失败:{e}")
            return False

    # ---------------- Upgrade Tasks ----------------
    def get_latest_topics(self, limit: int = 20) -> list:
        """获取最新主题列表"""
        try:
            self.driver.get(f"{HOME_URL}/latest")
            self._wait_discourse_ready(timeout=30)
            time.sleep(3)
            
            topics = []
            selectors = [
                ".topic-list-item",
                ".topic-list tbody tr",
                "tr.topic-list-item",
            ]
            
            topic_elements = []
            for selector in selectors:
                topic_elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                if topic_elements:
                    logger.info(f"使用选择器 '{selector}' 找到 {len(topic_elements)} 个主题")
                    break
            
            if not topic_elements:
                logger.warning("未找到主题列表")
                return []
            
            for elem in topic_elements[:limit]:
                try:
                    # 查找标题链接
                    title_elem = None
                    title_selectors = [".title a", "a.title", ".main-link a"]
                    
                    for ts in title_selectors:
                        try:
                            title_elem = elem.find_element(By.CSS_SELECTOR, ts)
                            if title_elem:
                                break
                        except Exception:
                            continue
                    
                    if not title_elem:
                        continue
                    
                    title = title_elem.text.strip()
                    url = title_elem.get_attribute("href")
                    
                    if title and url:
                        topics.append({"title": title, "url": url})
                        
                except Exception as e:
                    logger.debug(f"解析主题失败:{e}")
                    continue
            
            logger.info(f"共找到 {len(topics)} 个主题")
            return topics
            
        except Exception as e:
            logger.error(f"获取主题列表失败:{e}")
            return []

    def browse_topic(self, topic: dict) -> bool:
        """浏览单个主题"""
        try:
            logger.info(f"浏览主题: {topic['title'][:40]}...")
            self.driver.get(topic["url"])
            self._wait_discourse_ready(timeout=30)
            
            # 模拟阅读时间
            read_time = random.uniform(3, 8)
            time.sleep(read_time)
            
            self.stats['topics_browsed'] += 1
            self.stats['posts_read'] += 1
            
            return True
        except Exception as e:
            logger.debug(f"浏览主题失败:{e}")
            return False

    def like_posts_in_topic(self, max_likes: int = 2) -> int:
        """在当前主题中点赞帖子"""
        liked_count = 0
        try:
            # 等待页面加载完成
            time.sleep(2)
            
            # 方法1: 尝试点击 discourse-reactions-reaction-button (实际的反应按钮容器)
            reaction_buttons = self.driver.find_elements(By.CSS_SELECTOR, ".discourse-reactions-reaction-button")
            
            if reaction_buttons:
                logger.debug(f"找到 {len(reaction_buttons)} 个反应按钮容器")
                
                for btn in reaction_buttons[:max_likes]:
                    try:
                        # 检查是否已点赞
                        classes = btn.get_attribute("class") or ""
                        if "has-reaction" in classes.lower() or "reacted" in classes.lower():
                            logger.debug("该帖子已点赞，跳过")
                            continue
                        
                        # 滚动到按钮可见
                        self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn)
                        time.sleep(0.5)
                        
                        # 使用 JavaScript 点击（避免被遮挡）
                        self.driver.execute_script("arguments[0].click();", btn)
                        time.sleep(random.uniform(1, 2))
                        liked_count += 1
                        self.stats['likes_given'] += 1
                        logger.info(f"👍 点赞成功 ({self.stats['likes_given']})")
                        
                        if self.stats['likes_given'] >= DAILY_TASKS['likes_to_give']:
                            break
                            
                    except Exception as e:
                        logger.debug(f"点赞反应按钮失败:{e}")
                        continue
                
                return liked_count
            
            # 方法2: 如果没有找到反应按钮，尝试传统点赞按钮
            like_selectors = [
                "button[title*='赞']",
                "button.like-button",
                "button.toggle-like",
                ".post-controls button.like"
            ]
            
            like_buttons = []
            for selector in like_selectors:
                like_buttons = self.driver.find_elements(By.CSS_SELECTOR, selector)
                if like_buttons:
                    logger.debug(f"使用选择器 '{selector}' 找到 {len(like_buttons)} 个点赞按钮")
                    break
            
            if not like_buttons:
                logger.debug("未找到点赞按钮")
                return 0
            
            for btn in like_buttons[:max_likes]:
                try:
                    # 检查是否已点赞
                    classes = btn.get_attribute("class") or ""
                    if "liked" in classes.lower() or "has-like" in classes.lower():
                        logger.debug("该帖子已点赞，跳过")
                        continue
                    
                    # 滚动到按钮可见
                    self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn)
                    time.sleep(0.5)
                    
                    # 使用 JavaScript 点击
                    self.driver.execute_script("arguments[0].click();", btn)
                    time.sleep(random.uniform(1, 2))
                    liked_count += 1
                    self.stats['likes_given'] += 1
                    logger.info(f"👍 点赞成功 ({self.stats['likes_given']})")
                    
                    if self.stats['likes_given'] >= DAILY_TASKS['likes_to_give']:
                        break
                        
                except Exception as e:
                    logger.debug(f"点赞单个按钮失败:{e}")
                    continue
            
            return liked_count
        except Exception as e:
            logger.debug(f"点赞功能异常:{e}")
            return 0

    def reply_to_topic(self, topic: dict) -> bool:
        """回复主题"""
        try:
            logger.info(f"回复主题: {topic['title'][:40]}...")
            
            # 等待页面完全加载
            time.sleep(3)
            
            # 查找回复按钮（尝试多种选择器）
            reply_btn = None
            reply_selectors = [
                "button.reply.create",
                "button.reply",
                ".topic-footer-main-buttons button.reply",
                "button[title*='回复']"
            ]
            
            for selector in reply_selectors:
                try:
                    buttons = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    if buttons:
                        reply_btn = buttons[0]
                        logger.debug(f"使用选择器 '{selector}' 找到回复按钮")
                        break
                except Exception:
                    continue
            
            if not reply_btn:
                logger.warning("未找到回复按钮")
                return False
            
            # 滚动到回复按钮可见
            try:
                self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", reply_btn)
                time.sleep(1)
                
                # 使用 JavaScript 点击（避免被遮挡）
                self.driver.execute_script("arguments[0].click();", reply_btn)
                time.sleep(3)
            except Exception as e:
                logger.error(f"点击回复按钮失败:{e}")
                return False
            
            # 查找编辑器
            try:
                # 等待编辑器出现
                wait = WebDriverWait(self.driver, 10)
                editor = wait.until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, ".d-editor-input"))
                )
                
                # 滚动到编辑器
                self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", editor)
                time.sleep(1)
                
                # 输入回复内容
                reply_text = random.choice(REPLY_TEMPLATES)
                editor.clear()
                editor.send_keys(reply_text)
                time.sleep(2)
                
                # 查找提交按钮
                submit_btn = self.driver.find_element(By.CSS_SELECTOR, "button.create")
                
                # 滚动到提交按钮
                self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", submit_btn)
                time.sleep(1)
                
                # 使用 JavaScript 点击提交按钮
                self.driver.execute_script("arguments[0].click();", submit_btn)
                time.sleep(3)
                
                self.stats['replies_posted'] += 1
                logger.success(f"回复成功: {reply_text}")
                return True
                
            except Exception as e:
                logger.error(f"回复输入失败:{e}")
                return False
                
        except Exception as e:
            logger.error(f"回复主题失败:{e}")
            return False

    def auto_upgrade_tasks(self):
        """执行自动升级任务"""
        logger.info(f"\n{'='*50}")
        logger.info(f"🚀 开始执行升级任务")
        logger.info(f"{'='*50}")
        
        # 1. 获取主题列表
        logger.info("📋 获取最新主题列表...")
        topics = self.get_latest_topics(DAILY_TASKS['topics_to_browse'])
        
        if not topics:
            logger.warning("未找到主题,跳过升级任务")
            return
        
        # 2. 浏览主题并点赞
        for i, topic in enumerate(topics, 1):
            try:
                logger.info(f"[{i}/{len(topics)}] 处理主题...")
                
                # 浏览主题
                if self.browse_topic(topic):
                    # 点赞（控制频率）
                    if self.stats['likes_given'] < DAILY_TASKS['likes_to_give']:
                        liked = self.like_posts_in_topic(max_likes=2)
                        if liked > 0:
                            logger.info(f"👍 点赞 {liked} 次 (总计:{self.stats['likes_given']})")
                    
                    # 回复（控制频率）
                    if self.stats['replies_posted'] < DAILY_TASKS['replies_to_post']:
                        # 只回复部分主题（随机选择）
                        if random.random() < 0.3:  # 30% 概率回复
                            if self.reply_to_topic(topic):
                                logger.info(f"💬 回复成功 (总计:{self.stats['replies_posted']})")
                
                # 随机延迟
                if i < len(topics):
                    delay = random.uniform(5, 10)
                    time.sleep(delay)
                
            except Exception as e:
                logger.warning(f"处理主题时出错: {e}")
                continue
        
        # 3. 输出统计
        logger.info(f"\n{'='*50}")
        logger.info("📊 今日任务完成统计:")
        logger.info(f"  - 浏览主题: {self.stats['topics_browsed']}")
        logger.info(f"  - 阅读帖子: {self.stats['posts_read']}")
        logger.info(f"  - 给出点赞: {self.stats['likes_given']}")
        logger.info(f"  - 发布回复: {self.stats['replies_posted']}")
        logger.info(f"{'='*50}\n")

    # ---------------- Run ----------------
    def run(self) -> int:
        try:
            logger.info("==== NodeLoc 快速升级脚本开始 ====")

            # 1. 登录
            if not self.login():
                logger.error("NodeLoc:登录失败 ❌")
                tg_notify("NodeLoc:登录失败 ❌")
                return 2

            # 2. 启动浏览器
            self.start_browser()
            self.sync_cookie_to_browser()

            # 3. 签到
            self.do_checkin()
            
            # 4. 执行升级任务
            self.auto_upgrade_tasks()

            # 5. 发送通知
            summary = (
                f"NodeLoc 升级任务完成 ✅\n"
                f"浏览主题: {self.stats['topics_browsed']}\n"
                f"阅读帖子: {self.stats['posts_read']}\n"
                f"给出点赞: {self.stats['likes_given']}\n"
                f"发布回复: {self.stats['replies_posted']}"
            )
            tg_notify(summary)
            logger.success(summary)
            
            logger.info("==== NodeLoc 快速升级脚本结束 ====")
            return 0

        except Exception:
            logger.error("NodeLoc:脚本异常 ❌")
            traceback.print_exc()
            tg_notify("NodeLoc:脚本异常 ❌")
            return 9

        finally:
            try:
                if self.driver:
                    self.driver.quit()
            except Exception:
                pass


if __name__ == "__main__":
    username = os.environ.get("NODELOC_USERNAME")
    password = os.environ.get("NODELOC_PASSWORD")

    if not username or not password:
        logger.error("请设置 NODELOC_USERNAME / NODELOC_PASSWORD")
        tg_notify("NodeLoc:未设置环境变量 ❌")
        raise SystemExit(1)

    raise SystemExit(NodeLocUpgrade(username, password).run())
