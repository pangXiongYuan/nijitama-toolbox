# -*- coding: utf-8 -*-
"""
version.py —— 版本号的唯一来源

规则：主版本.次版本.修订号
  主版本：界面/用法大改，或需要重新登录
  次版本：新增功能
  修订号：修 bug、调样式、改文案

改版本号只改这里，界面和标题栏会自动跟着变。
每次改完记得在 CHANGELOG.md 里记一条。
"""

APP_NAME = "にじたま 工具箱"
VERSION = "1.6.3"
BUILD_DATE = "2026-11-14"

__version__ = VERSION
