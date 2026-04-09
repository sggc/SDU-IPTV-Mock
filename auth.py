import sys
import random
import re
import time
import socket
import uuid
from Crypto.Cipher import DES
from Crypto.Util.Padding import pad
import urllib.request
import urllib.parse
from http.cookiejar import CookieJar

CONFIG = {
    # 破解得到的密钥
    'key': '',
    'user_id': '',
    'stb_id': '',
    'mac': '',
    'ip': None,  # 自动获取
    'stb_type': '',
    'stb_version': '',
    # 服务器地址
    'eds_server': '', 
    'platform': 'CTC', 
    'interface_suffix': 'CU', 
}

def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        local_ip = s.getsockname()[0]
        s.close()
        return local_ip
    except:
        pass
    try:
        hostname = socket.gethostname()
        return socket.gethostbyname(hostname)
    except:
        pass
    return None


def auto_detect_config():
    print("=" * 60)
    print("配置信息")
    print("=" * 60)
    print()
    # 检测IP
    if CONFIG['ip'] is None:
        print("检测IP地址...")
        local_ip = get_local_ip()
        if local_ip:
            CONFIG['ip'] = local_ip
            print(f" [OK] 使用本机IP: {local_ip}")
            if local_ip.startswith('10.'):
                print(f" [OK] 在IPTV网段 (10.x.x.x)")
            else:
                print(f" [!] 不在IPTV网段，可能需要配置IPTV接口")
        else:
            print(" [X] 无法获取IP地址")
            return False
    print()
    print("最终配置:")
    print(f" IP: {CONFIG['ip']} (自动获取)")
    print(f" MAC: {CONFIG['mac']} (固定配置)")
    print(f" 平台标识: {CONFIG['platform']} (用于明文)")
    print(f" 接口后缀: HW{CONFIG['interface_suffix']} (用于URL)")
    print()
    return True

class IPTVAuthenticator:
    """IPTV认证器"""
    def __init__(self, config):
        self.config = config
        self.cookie_jar = CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.cookie_jar)
        )
        self.epg_host = None
        self.user_token = None
        self.jsession_id = None
        self.stbid = None

    def log(self, msg):
        """日志输出"""
        try:
            print(f"[{time.strftime('%H:%M:%S')}] {msg}")
        except:
            print(f"[{time.strftime('%H:%M:%S')}] {msg.encode('gbk', errors='ignore').decode('gbk')}")

    def generate_authenticator(self, encrypt_token):
        """生成Authenticator"""
        # 生成8位随机数
        random_num = random.randint(10000000, 99999999)
        # 组装明文 - 关键修改：用"Reserved"代替空，使用CTC平台标识
        plaintext = f"{random_num}${encrypt_token}${self.config['user_id']}${self.config['stb_id']}${self.config['ip']}${self.config['mac']}$Reserved$CTC"
        # DES加密（3DES退化为DES）
        key = self.config['key'].encode('ascii')
        cipher = DES.new(key, DES.MODE_ECB)
        padded = pad(plaintext.encode('ascii'), 8)
        authenticator = cipher.encrypt(padded).hex().upper()
        self.log(f"生成Authenticator成功 (Random: {random_num})")
        self.log(f"明文格式: {plaintext}")
        return authenticator

    def step1_authentication_url(self):
        """步骤1: 访问AuthenticationURL获取EPG服务器"""
        self.log("=" * 60)
        self.log("步骤1: 访问AuthenticationURL")
        self.log("=" * 60)
        url = f"http://{self.config['eds_server']}/EDS/jsp/AuthenticationURL"
        params = {
            'UserID': self.config['user_id'],
            'Action': 'Login',
            'FCCSupport': '1'
        }
        full_url = f"{url}?{urllib.parse.urlencode(params)}"
        self.log(f"请求: {full_url}")
        try:
            req = urllib.request.Request(full_url)
            req.add_header('User-Agent', 'B700-V2A|Mozilla|5.0|ztebw(Chrome)|1.2.0')
            response = self.opener.open(req, timeout=10)
            final_url = response.geturl()
            # 提取EPG服务器地址
            self.epg_host = urllib.parse.urlparse(final_url).netloc
            self.log(f"[OK] EPG服务器: {self.epg_host}")
            return True
        except Exception as e:
            self.log(f"[X] 失败: {e}")
            return False

    def step2_auth_login(self):
        """步骤2: 提交authLogin获取EncryptToken"""
        self.log("=" * 60)
        self.log("步骤2: 提交authLogin")
        self.log("=" * 60)
        url = f"http://{self.epg_host}/EPG/jsp/authLoginHW{self.config['interface_suffix']}.jsp"
        data = urllib.parse.urlencode({
            'UserID': self.config['user_id'],
            'VIP': ''
        }).encode('ascii')
        self.log(f"请求: {url}")
        try:
            req = urllib.request.Request(url, data=data)
            req.add_header('User-Agent', 'B700-V2A|Mozilla|5.0|ztebw(Chrome)|1.2.0')
            req.add_header('Content-Type', 'application/x-www-form-urlencoded')
            response = self.opener.open(req, timeout=10)
            html = response.read().decode('utf-8', errors='ignore')
            # 提取EncryptToken
            match = re.search(r'EncryptToken\s*=\s*"([^"]+)"', html)
            if match:
                encrypt_token = match.group(1)
                self.log(f"[OK] EncryptToken: {encrypt_token}")
                return encrypt_token
            else:
                self.log("[X] 未找到EncryptToken")
                return None
        except Exception as e:
            self.log(f"[X] 失败: {e}")
            return None

    def step3_valid_authentication(self, encrypt_token):
        """步骤3: 提交ValidAuthentication获取Session"""
        self.log("=" * 60)
        self.log("步骤3: 提交ValidAuthentication")
        self.log("=" * 60)
        url = f"http://{self.epg_host}/EPG/jsp/ValidAuthenticationHW{self.config['interface_suffix']}.jsp"
        # 生成Authenticator
        authenticator = self.generate_authenticator(encrypt_token)
        data = {
            'UserID': self.config['user_id'],
            'Lang': '0',
            'SupportHD': '1',
            'NetUserID': 'SDIPTVPPPOE@sdiptv',
            'Authenticator': authenticator,
            'STBType': self.config['stb_type'],
            'STBVersion': self.config['stb_version'],
            'conntype': 'dhcp',
            'STBID': self.config['stb_id'],
            'templateName': '',
            'areaId': '',
            'userToken': encrypt_token,
            'userGroupId': '',
            'productPackageId': '',
            'mac': self.config['mac'],
            'UserField': '',
            'SoftwareVersion': self.config['stb_version'],
            'IsSmartStb': 'undefined',
            'desktopId': 'undefined',
            'stbmaker': '',
            'VIP': ''
        }
        post_data = urllib.parse.urlencode(data).encode('ascii')
        self.log(f"请求: {url}")
        try:
            req = urllib.request.Request(url, data=post_data)
            req.add_header('User-Agent', 'B700-V2A|Mozilla|5.0|ztebw(Chrome)|1.2.0')
            req.add_header('Content-Type', 'application/x-www-form-urlencoded')
            response = self.opener.open(req, timeout=10)
            html = response.read().decode('utf-8', errors='ignore')
            
            # 提取JSESSIONID
            for cookie in self.cookie_jar:
                if cookie.name == 'JSESSIONID':
                    self.jsession_id = cookie.value
                    self.log(f"[OK] JSESSIONID: {self.jsession_id}")
                    break
            # 提取UserToken和stbid
            match = re.search(r'"UserToken"\s+value="([^"]+)"', html)
            if match:
                self.user_token = match.group(1)
                self.log(f"[OK] UserToken: {self.user_token}")

            match = re.search(r'"stbid"\s+value="([^"]+)"', html)
            if match:
                self.stbid = match.group(1)
                self.log(f"[OK] stbid: {self.stbid}")

            if self.jsession_id and self.user_token:
                return True
            else:
                self.log("[X] 未获取到Session信息")
                return False
        except Exception as e:
            self.log(f"[X] 失败: {e}")
            return False

    def step4_get_channel_list(self):
        """步骤4: 获取频道列表"""
        self.log("=" * 60)
        self.log("步骤4: 获取频道列表")
        self.log("=" * 60)
        url = f"http://{self.epg_host}/EPG/jsp/getchannellistHW{self.config['interface_suffix']}.jsp"
        data = {
            'conntype': 'dhcp',
            'UserToken': self.user_token,
            'stbid': self.stbid,
            'SupportHD': '1',
            'UserID': self.config['user_id'],
            'Lang': '1'
        }
        post_data = urllib.parse.urlencode(data).encode('ascii')
        self.log(f"请求: {url}")
        try:
            req = urllib.request.Request(url, data=post_data)
            req.add_header('User-Agent', 'B700-V2A|Mozilla|5.0|ztebw(Chrome)|1.2.0')
            req.add_header('Content-Type', 'application/x-www-form-urlencoded')
            response = self.opener.open(req, timeout=30)
            html = response.read().decode('utf-8', errors='ignore')
            
            # 仅保存原始响应到文件
            with open('getchannellistHWCU_raw.jsp', 'w', encoding='utf-8') as f:
                f.write(html)
            self.log(f"[OK] 原始响应已保存到 getchannellistHWCU_raw.jsp")

            # 仅解析数量用于提示，不做其他保存和打印
            pattern = r'ChannelID="([^"]+)",ChannelName="([^"]+)",UserChannelID="([^"]+)",ChannelURL="([^"]+)"'
            matches = re.findall(pattern, html)
            return len(matches)
        except Exception as e:
            self.log(f"[X] 失败: {e}")
            return None

    def run(self):
        """运行完整认证流程"""
        print()
        print("=" * 60)
        print("山东联通华为IPTV认证流程")
        print("=" * 60)
        print(f"用户ID: {self.config['user_id']}")
        print(f"密钥: {self.config['key']}")
        print(f"平台标识: {self.config['platform']} (明文)")
        print(f"接口后缀: HW{self.config['interface_suffix']} (URL)")
        print(f"IP: {self.config['ip']}")
        print(f"MAC: {self.config['mac']}")
        print("=" * 60)
        print()

        # 步骤1
        if not self.step1_authentication_url():
            return False

        # 步骤2
        encrypt_token = self.step2_auth_login()
        if not encrypt_token:
            return False

        # 步骤3
        if not self.step3_valid_authentication(encrypt_token):
            return False

        # 步骤4
        channel_count = self.step4_get_channel_list()
        if not channel_count:
            return False

        # 输出结果
        print()
        print("=" * 60)
        print(f"[OK] 认证完成，频道数量: {channel_count}")
        print(f"[OK] 原始响应已保存到: getchannellistHWCU_raw.jsp")
        print("=" * 60)
        print()
        return True

def main():
    """主函数"""
    print()
    # 自动检测配置
    if not auto_detect_config():
        print("配置检测失败，请手动配置")
        print()
        print("手动配置方法:")
        print(" 编辑脚本，设置CONFIG['ip']和CONFIG['mac']")
        print()
        input("按回车键退出...")
        return

    try:
        auth = IPTVAuthenticator(CONFIG)
        success = auth.run()
        if success:
            print("按回车键退出...")
            input()
            sys.exit(0)
        else:
            print()
            print("认证失败!")
            print("按回车键退出...")
            input()
            sys.exit(1)
    except Exception as e:
        print(f"\n错误: {e}")
        print("按回车键退出...")
        input()
        sys.exit(1)

if __name__ == "__main__":
    main()
