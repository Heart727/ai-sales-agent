"""
认证模块：密码加密 + 登录令牌，供 main.py 的登录接口使用。

三个核心概念（大白话版）：
1. 密码哈希：密码不能明文存数据库（万一数据库泄露，密码直接曝光）。
   做法是把密码"搅碎"成一段看不懂的哈希值存起来，登录时把输入的密码
   再搅碎一次，对比两段哈希是否相同——相同就说明密码对了。
2. 盐（salt）：每个用户随机生成一串字符，掺进密码里一起搅碎。
   没有盐的话，两个密码相同的人哈希值也一样，容易被"彩虹表"批量破解。
3. 令牌（token）：登录成功后，服务器发一串随机字符给浏览器存起来
   （cookie），之后浏览器每次请求自动带上，服务器靠它认出你是谁。
"""
import hashlib
import hmac
import secrets

# 只用了 Python 自带的标准库，不需要安装任何新依赖

# 哈希算法重复次数：次数越多越难暴力破解，但登录时计算也越慢。
# 10 万次是常用的安全值（每个用户还会随机加盐，更安全）。
PBKDF2_ITERATIONS = 100_000


def new_salt() -> str:
    """生成随机盐：16 字节的随机数转成 32 个十六进制字符"""
    return secrets.token_hex(16)


def hash_password(password: str, salt: str) -> str:
    """
    把"密码 + 盐"搅碎成哈希值。

    PBKDF2 的原理：把密码和盐反复哈希 10 万次。
    攻击者想暴力破解时，每猜一个密码也要算 10 万次，成本极高。
    """
    digest = hashlib.pbkdf2_hmac(
        "sha256",              # 哈希算法
        password.encode(),     # 密码原文转成字节
        salt.encode(),         # 盐转成字节
        PBKDF2_ITERATIONS,     # 重复 10 万次
    )
    return digest.hex()        # 转成十六进制字符串存储


def verify_password(password: str, salt: str, stored_hash: str) -> bool:
    """
    校验密码：把输入的密码用同样的盐搅碎，和数据库里存的哈希对比。
    用 hmac.compare_digest 对比（常量时间比较），防止时序攻击。
    """
    candidate = hash_password(password, salt)
    return hmac.compare_digest(candidate, stored_hash)


def generate_token() -> str:
    """生成登录令牌：32 字节随机数（64 个十六进制字符），无法猜中"""
    return secrets.token_hex(32)
