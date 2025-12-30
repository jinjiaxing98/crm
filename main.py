import requests
import json
import warnings
import urllib3
import os  # 读取环境变量
from bs4 import BeautifulSoup
from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse

# 禁用SSL警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
warnings.filterwarnings('ignore', category=UserWarning)

# 初始化FastAPI应用
app = FastAPI(title="CRM手机号查询接口", version="1.0")

class CrmLogin:
    def __init__(self):
        self.session = requests.Session()
        self.authorization = None
        self.cookie = ""
        self.headers_template = {
            'Host': "crmbackend.offcn.com:6443",
            'User-Agent': "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36 Edg/142.0.0.0",
            'Accept': "application/json, text/plain, */*",
            'Accept-Encoding': "gzip, deflate, br, zstd",
            'Content-Type': "application/json",
            'sec-ch-ua-platform': "\"Windows\"",
            'sec-ch-ua': "\"Chromium\";v=\"142\", \"Microsoft Edge\";v=\"142\", \"Not_A Brand\";v=\"99\"",
            'sec-ch-ua-mobile': "?0",
            'dnt': "1",
            'version': "2.0.2",
            'origin': "https://crm.offcn.com",
            'sec-fetch-site': "same-site",
            'sec-fetch-mode': "cors",
            'sec-fetch-dest': "empty",
            'referer': "https://crm.offcn.com/",
            'accept-language': "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
            'priority': "u=1, i"
        }

    def login(self):
        """登录MIS→CRM，从环境变量读取敏感信息"""
        # 从Vercel环境变量读取账号密码（核心：无硬编码）
        MIS_USERNAME = os.getenv("MIS_USERNAME")  # 环境变量名
        MIS_PASSWORD = os.getenv("MIS_PASSWORD")
        CRM_PASSWORD = os.getenv("CRM_PASSWORD", "c7c70b6555dce9d057f2f9c30b5d0c6d")

        # 校验环境变量是否配置
        if not MIS_USERNAME or not MIS_PASSWORD:
            raise Exception("❌ 未配置MIS账号/密码环境变量")

        # 1. 登录MIS系统
        mis_login_url = "http://mis.offcn.com/index/login"
        mis_payload = {
            '_csrf': "QThtT292SUkmYl86Fz4zfwBpIx8GQCs6LU0BNgUuISZ3ZyM2FykxIA==",
            'username': MIS_USERNAME,  # 环境变量
            'password': MIS_PASSWORD,  # 环境变量
            'submit': "Log In"
        }
        mis_headers = {
            'User-Agent': "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36 Edg/138.0.0.0",
            'Accept': "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            'Origin': "http://mis.offcn.com",
            'Referer': "http://mis.offcn.com/index/login",
        }
        mis_response = self.session.post(mis_login_url, data=mis_payload, headers=mis_headers, timeout=30)
        if mis_response.status_code != 200 or "登录成功" not in mis_response.text:
            raise Exception(f"❌ MIS登录失败：状态码{mis_response.status_code}")
        
        # 提取MIS Cookie和代码
        self.cookie = "; ".join([f"{k}={v}" for k, v in self.session.cookies.items()])
        mis_home = self.session.get("http://mis.offcn.com", timeout=30)
        soup = BeautifulSoup(mis_home.text, 'html.parser')
        mis_code_span = soup.find('span', {'id': 'misCode'})
        if not mis_code_span:
            raise Exception("❌ 未获取到MIS代码")
        mis_code = mis_code_span.text.strip()

        # 2. 登录CRM系统
        crm_cas_url = "https://crmbackend.offcn.com:6443/xtgl/cas"
        cas_payload = {
            "username": MIS_USERNAME,
            "password": CRM_PASSWORD,
            "misCode": mis_code,
            "sign": "",
            "request-client": "crm"
        }
        cas_response = requests.post(crm_cas_url, json=cas_payload, headers=self.headers_template, verify=False, timeout=30)
        if cas_response.status_code != 200:
            raise Exception(f"❌ 获取authcode失败：状态码{cas_response.status_code}")
        authcode = cas_response.json().get("authcode")
        if not authcode:
            raise Exception("❌ 未获取到authcode")

        crm_login_url = "https://crmbackend.offcn.com:6443/xtgl/login/submit"
        login_response = requests.post(crm_login_url, json={"authcode": authcode}, headers=self.headers_template, verify=False, timeout=30)
        if login_response.status_code != 200:
            raise Exception(f"❌ CRM登录失败：状态码{login_response.status_code}")
        
        self.authorization = login_response.json().get("Authorization")
        if not self.authorization:
            raise Exception("❌ 未获取到CRM授权令牌")

        # 更新请求头（后续API复用）
        self.headers_template['authorization'] = self.authorization
        self.headers_template['Cookie'] = self.cookie
        return True

# 核心接口：支持传入明文手机号（如13605130847）
@app.get("/query_cust")
async def query_cust_by_mobile(
    mobile: str = Query(..., description="明文手机号，例如：13605130847")
):
    result = {
        "success": False,
        "data": None,
        "message": ""
    }
    try:
        # 自动登录CRM
        crm = CrmLogin()
        crm.login()
        
        # 核心调整：直接用明文手机号调用API
        query_url = "https://crmbackend.offcn.com:6443/cust/cust/querycust"
        query_payload = {"mobile": mobile, "weixin": None}  # mobile为明文
        response = requests.post(
            query_url,
            data=json.dumps(query_payload),
            headers=crm.headers_template,
            verify=False,
            timeout=30
        )

        # 处理响应结果
        if response.status_code == 200:
            result["success"] = True
            result["data"] = response.json()
            result["message"] = "✅ 查询成功（明文手机号）"
        else:
            result["message"] = f"❌ 查询失败：状态码{response.status_code}，响应：{response.text[:200]}"

    except Exception as e:
        result["message"] = f"❌ 执行失败：{str(e)}"
    
    return JSONResponse(content=result)

# Vercel Serverless适配（必须）
def handler(event, context):
    import mangum
    asgi_handler = mangum.Mangum(app)
    return asgi_handler(event, context)
