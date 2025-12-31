import requests
import json
import warnings
import urllib3
import os
from bs4 import BeautifulSoup
from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

# 禁用SSL警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
warnings.filterwarnings('ignore', category=UserWarning)

# 初始化FastAPI + 前端模板（核心：支持HTML页面）
app = FastAPI(title="CRM手机号查询工具", version="1.0")
templates = Jinja2Templates(directory="templates")  # 模板目录（代码内联HTML，无需实际文件夹）

# 核心登录类（保留原有逻辑，新增步骤日志）
class CrmLogin:
    def __init__(self):
        self.session = requests.Session()
        self.authorization = None
        self.cookie = ""
        self.step_logs = []  # 存储每一步操作日志
        self.headers_template = {
            'Host': "crmbackend.offcn.com:6443",
            'User-Agent': "Mozilla/5.0",
            'Content-Type': "application/json",
            'Accept': "application/json",
        }

    def add_log(self, step, content):
        """添加操作步骤日志"""
        self.step_logs.append(f"【{step}】{content}")
        print(f"【{step}】{content}")

    def login(self):
        """登录CRM，返回步骤日志和授权信息"""
        self.step_logs = []  # 清空历史日志
        try:
            # 1. 读取环境变量
            self.add_log("1. 读取配置", "开始读取MIS账号密码环境变量")
            MIS_USERNAME = os.getenv("MIS_USERNAME") or "你的MIS账号"  # 本地测试替换
            MIS_PASSWORD = os.getenv("MIS_PASSWORD") or "你的MIS密码"  # 本地测试替换
            CRM_PASSWORD = os.getenv("CRM_PASSWORD") or "你的CRM加密密码"

            if not MIS_USERNAME or not MIS_PASSWORD:
                raise Exception("未配置MIS账号/密码环境变量")
            self.add_log("1. 读取配置", "✅ 账号密码配置读取成功")

            # 2. 登录MIS系统
            self.add_log("2. MIS登录", "开始请求MIS登录接口：http://mis.offcn.com/index/login")
            mis_login_url = "http://mis.offcn.com/index/login"
            mis_payload = {
                '_csrf': "QThtT292SUkmYl86Fz4zfwBpIx8GQCs6LU0BNgUuISZ3ZyM2FykxIA==",
                'username': MIS_USERNAME,
                'password': MIS_PASSWORD,
                'submit': "Log In"
            }
            mis_headers = {'User-Agent': "Mozilla/5.0", 'Referer': "http://mis.offcn.com/index/login"}
            
            mis_response = self.session.post(
                mis_login_url, data=mis_payload, headers=mis_headers, timeout=20, allow_redirects=False
            )
            
            if mis_response.status_code not in [200, 302] or "登录成功" not in mis_response.text:
                raise Exception(f"状态码{mis_response.status_code}，响应：{mis_response.text[:100]}")
            self.add_log("2. MIS登录", "✅ MIS登录成功")

            # 3. 提取MIS信息
            self.add_log("3. 提取MIS信息", "开始提取Cookie和misCode")
            self.cookie = "; ".join([f"{k}={v}" for k, v in self.session.cookies.items()])
            mis_home = self.session.get("http://mis.offcn.com", timeout=20)
            soup = BeautifulSoup(mis_home.text, 'html.parser')
            mis_code_span = soup.find('span', {'id': 'misCode'})
            if not mis_code_span:
                raise Exception("未找到id为misCode的元素")
            mis_code = mis_code_span.text.strip()
            self.add_log("3. 提取MIS信息", f"✅ Cookie提取成功，misCode：{mis_code}")

            # 4. 获取CRM authcode
            self.add_log("4. CRM授权", "开始请求CRM CAS接口获取authcode")
            crm_cas_url = "https://crmbackend.offcn.com:6443/xtgl/cas"
            cas_payload = {
                "username": MIS_USERNAME, "password": CRM_PASSWORD, 
                "misCode": mis_code, "sign": "", "request-client": "crm"
            }
            cas_response = requests.post(
                crm_cas_url, json=cas_payload, headers=self.headers_template, verify=False, timeout=20
            )
            if cas_response.status_code != 200:
                raise Exception(f"状态码{cas_response.status_code}")
            authcode = cas_response.json().get("authcode")
            if not authcode:
                raise Exception("响应中无authcode字段")
            self.add_log("4. CRM授权", f"✅ authcode获取成功：{authcode[:10]}...")

            # 5. 最终登录CRM
            self.add_log("5. CRM登录", "开始请求CRM登录接口获取Authorization")
            crm_login_url = "https://crmbackend.offcn.com:6443/xtgl/login/submit"
            login_response = requests.post(
                crm_login_url, json={"authcode": authcode}, headers=self.headers_template, verify=False, timeout=20
            )
            if login_response.status_code != 200:
                raise Exception(f"状态码{login_response.status_code}")
            self.authorization = login_response.json().get("Authorization")
            if not self.authorization:
                raise Exception("响应中无Authorization字段")
            self.add_log("5. CRM登录", f"✅ Authorization获取成功：{self.authorization[:20]}...")

            # 更新请求头
            self.headers_template['authorization'] = self.authorization
            self.headers_template['Cookie'] = self.cookie
            self.add_log("登录完成", "✅ CRM登录全流程完成，准备查询客户信息")
            return True

        except Exception as e:
            self.add_log("错误", f"❌ {str(e)}")
            raise Exception(f"登录失败：{str(e)}")

# 核心1：前端页面（访问域名直接显示）
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    # 内联HTML页面（无需额外文件）
    html_content = """
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
        <meta charset="UTF-8">
        <title>CRM手机号查询工具</title>
        <style>
            body { font-family: Arial, sans-serif; max-width: 1000px; margin: 20px auto; padding: 0 20px; }
            .container { border: 1px solid #ddd; padding: 20px; border-radius: 8px; background: #f9f9f9; }
            .input-group { margin-bottom: 20px; }
            input { padding: 10px; width: 300px; font-size: 16px; border: 1px solid #ddd; border-radius: 4px; }
            button { padding: 10px 20px; font-size: 16px; background: #007bff; color: white; border: none; border-radius: 4px; cursor: pointer; }
            button:hover { background: #0056b3; }
            .logs { margin-top: 20px; padding: 10px; background: white; border: 1px solid #ddd; border-radius: 4px; min-height: 200px; font-size: 14px; line-height: 1.6; }
            .result { margin-top: 20px; padding: 10px; background: #e8f4f8; border: 1px solid #b3d9e8; border-radius: 4px; display: none; }
            .error { color: #dc3545; }
            .success { color: #28a745; }
            .step { margin: 5px 0; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>CRM手机号查询工具</h1>
            <div class="input-group">
                <input type="text" id="mobile" placeholder="请输入明文手机号（如13605130847）" required>
                <button onclick="queryCust()">开始查询</button>
            </div>
            <div class="logs" id="logs">
                📢 请输入手机号并点击「开始查询」，这里会显示每一步操作日志...
            </div>
            <div class="result" id="result">
                <h3>查询结果：</h3>
                <pre id="resultContent"></pre>
            </div>
        </div>

        <script>
            // 显示操作日志
            function addLog(content, isError=false) {
                const logsDiv = document.getElementById('logs');
                const stepDiv = document.createElement('div');
                stepDiv.className = isError ? 'step error' : 'step';
                stepDiv.textContent = content;
                logsDiv.appendChild(stepDiv);
                // 滚动到最新日志
                logsDiv.scrollTop = logsDiv.scrollHeight;
            }

            // 核心查询函数
            async function queryCust() {
                const mobile = document.getElementById('mobile').trim();
                if (!mobile) {
                    alert('请输入手机号！');
                    return;
                }

                // 清空历史记录
                document.getElementById('logs').innerHTML = '';
                document.getElementById('result').style.display = 'none';
                addLog(`📢 开始查询手机号：${mobile}`);

                try {
                    // 调用API接口
                    addLog('🔄 开始登录CRM并执行查询...');
                    const response = await fetch(`/query_cust?mobile=${encodeURIComponent(mobile)}`);
                    const result = await response.json();

                    // 显示步骤日志
                    if (result.step_logs) {
                        result.step_logs.forEach(log => addLog(log));
                    }

                    // 显示查询结果
                    const resultDiv = document.getElementById('result');
                    const resultContent = document.getElementById('resultContent');
                    resultContent.textContent = JSON.stringify(result, null, 2);
                    resultDiv.style.display = 'block';

                    // 结果状态提示
                    if (result.code === 0) {
                        addLog('✅ 查询完成：操作成功！', false);
                    } else {
                        addLog(`❌ 查询完成：${result.message}`, true);
                    }

                } catch (error) {
                    addLog(`💥 网络/系统异常：${error.message}`, true);
                }
            }
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

# 核心2：查询接口（返回日志+结果）
@app.get("/query_cust")
async def query_cust_by_mobile(mobile: str = Query(..., description="明文手机号")):
    result = {
        "code": -1,
        "message": "",
        "step_logs": [],  # 返回每一步操作日志
        "data": None
    }
    try:
        # 1. 登录CRM并获取步骤日志
        crm = CrmLogin()
        crm.login()
        result["step_logs"] = crm.step_logs  # 传递操作日志到前端
        result["step_logs"].append(f"6. 开始查询手机号：{mobile}")

        # 2. 调用查询API
        query_url = "https://crmbackend.offcn.com:6443/cust/cust/querycust"
        query_payload = {"mobile": mobile, "weixin": None}
        response = requests.post(
            query_url, json=query_payload, headers=crm.headers_template, verify=False, timeout=20
        )

        # 3. 解析结果
        if response.status_code == 200:
            crm_result = response.json()
            result["code"] = crm_result.get("code", 0)
            result["message"] = crm_result.get("message", "查询成功")
            result["data"] = crm_result
            result["step_logs"].append(f"✅ 查询API响应成功：{result['message']}")
        else:
            result["code"] = response.status_code
            result["message"] = f"查询API失败：状态码{response.status_code}"
            result["step_logs"].append(f"❌ {result['message']}")

    except Exception as e:
        result["code"] = -2
        result["message"] = f"执行异常：{str(e)}"
        if 'crm' in locals():
            result["step_logs"] = crm.step_logs  # 即使异常也返回已执行的日志
        result["step_logs"].append(f"❌ {result['message']}")
    
    return JSONResponse(content=result)

# Vercel适配Handler
def handler(event, context):
    try:
        from mangum import Mangum
        return Mangum(app)(event, context)
    except Exception as e:
        return {
            "statusCode": 500,
            "body": json.dumps({"code": -3, "message": f"Handler异常：{str(e)}"})
        }

# 本地测试入口
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
