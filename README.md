# SDU-IPTV-Mock
山东联通华为平台IPTV模拟鉴权认证
# 山东联通华为平台IPTV认证与频道列表获取

> 一次从抓包分析到完整认证流程实现的探索之旅

***

## 前言

之前有很多大神在这方面已经有过研究，并且有完整且成熟的流程，但由于地区与运营商的差别，不能百分百套用，所以想折腾一下家里的IPTV，看看能否不通过机顶盒直接获取频道列表。经过抓包分析，最终成功实现了从认证到获取频道信息的完整流程。

**注意**：本文内容仅供学习研究之用，可能不适用于其他地区、运营商或品牌。

***

## 机顶盒型号
ZXV10 B862AV3.2-U

## 抓包环境搭建

### 网络拓扑

采用双网卡桥接的方式进行抓包，让机顶盒流量经过电脑

<br />

**具体连接方式**：

1. **电脑自带网卡**（有线）：连接光猫IPTV口
2. **USB网卡**：连接机顶盒
3. **网桥配置**：在Windows网络设置中，将两个网卡桥接，使机顶盒流量经过电脑

**优势**：

- 无需购买专业抓包设备
- 无需路由器支持端口镜像功能
- 可以完整捕获机顶盒的所有进出流量

### 抓包工具

- **Wireshark**：用于捕获和分析网络数据包
- **捕获接口**：选择桥接后的虚拟网卡或USB网卡接口

***

## 认证流程分析

通过抓包分析，发现IPTV认证流程分为以下几个步骤：

### 步骤1：访问AuthenticationURL

机顶盒首先向EDS服务器发起认证请求：

```
GET /EDS/jsp/AuthenticationURL?UserID=<UserID>&Action=Login&FCCSupport=1 HTTP/1.1
Host: 27.xxx.xxx.xxx:8082
User-Agent: B700-V2A|Mozilla|5.0|ztebw(Chrome)|1.2.0
```

服务器返回302重定向，并设置Cookie：

```
HTTP/1.1 302 Found
Set-Cookie: EPGIP_PORT="123.xxx.xxx.xxx:33200"; Version=1; Max-Age=86400
Location: http://123.xxx.xxx.xxx:33200/EPG/jsp/AuthenticationURL?UserID=<UserID>&Action=Login
```

**关键发现**：

- EDS服务器负责初始认证和EPG服务器分配
- 通过Cookie下发实际的EPG服务器地址

### 步骤2：获取EncryptToken

跟随重定向后，向EPG服务器提交authLogin请求：

```
POST /EPG/jsp/authLoginHWCU.jsp HTTP/1.1
Host: 123.xxx.xxx.xxx:33200

UserID=<UserID>&VIP=
```

返回HTML中包含`EncryptToken`：

```html
<script>
var EncryptToken = "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx";
</script>
```

### 步骤3：生成Authenticator并验证

这是最关键的一步。前人早已经研究，其使用**3DES加密**（实际退化为DES），明文格式为：

```
{Random}${EncryptToken}${UserID}${STBID}${IP}${MAC}$Reserved$CTC
```

例如：

```
22295825$977C790C5E3FEF5798D998CBF6C70B69$05xxxxxxxxxx$DExxxxxxxxxxxxxxxxxxxxxx$10.xxx.xxx.xxx$C0:xx:xx:xx:xx:xx$$CTC
```

注意：

之前看过很多教程，大多都是电信运营商，明文末尾是CTC，我就想当然认为联通是CU，踩了坑

### 密钥破解

密钥是一个8位数字。编写穷举脚本进行暴力破解，最终找到有效密钥：**`04260600`**

总共可以穷举出256个等效密钥，值得注意的是，其中一个是IPTV的密码

### 步骤4：获取频道列表

认证成功后，使用获取到的`UserToken`和`stbid`请求频道列表：

```
POST /EPG/jsp/getchannellistHWCU.jsp HTTP/1.1
Host: 123.xxx.xxx.xxx:33200

conntype=dhcp&UserToken=xxxxxxxx&stbid=xxxxxxxx&SupportHD=1&UserID=<UserID>&Lang=1
```

返回的HTML中包含频道信息：

```html
<script>
var iRet = Authentication.CTCSetConfig('Channel','ChannelID="xxx",ChannelName="CCTV-1高清",UserChannelID="1",ChannelURL="igmp://xxx.xxx.xxx.xxx:xxxx",...');
</script>
```

***

## 完整鉴权认证流程图

```
步骤1: 初始认证请求
┌──────────┐                    ┌──────────┐
│ 机顶盒    │ ───GET──────────>  │ EDS服务器 │
│          │ /EDS/jsp/AuthenticationURL    │27.223.126.136:8082
│          │ ?UserID=xxx&Action=Login      │
└──────────┘                    └──────────┘
     │                                │
     │                                │ 302重定向
     │                                │ Location: EPG服务器
     │                                ↓
     │                         ┌──────────┐
     └─────────────────────────│ EPG服务器 │
                               │123.133.95.40:33200
                               └──────────┘

步骤2: 获取认证表单
┌──────────┐                    ┌──────────┐
│ 机顶盒    │ ───GET──────────>  │ EPG服务器 │
│          │ /EPG/jsp/AuthenticationURL    │
└──────────┘                    └──────────┘
     │                                │
     │                                │ 返回HTML表单
     │ <──────────────────────────────┘
     │    <form action="authLoginHWCU.jsp">
     │    <input name="UserID" value="xxx">
     │    <input name="VIP" value="">

步骤3: 提交登录信息
┌──────────┐                    ┌──────────┐
│ 机顶盒    │ ───POST─────────>  │ EPG服务器 │
│          │ /EPG/jsp/authLoginHWCU.jsp    │
│          │ UserID=xxx                    │
│          │ VIP=                          │
└──────────┘                    └──────────┘
     │                                │
     │                                │ 返回EncryptToken和userToken
     │ <──────────────────────────────┘
     │    EncryptToken = "xxx"
     │    userToken = "xxx"

步骤4: 提交认证信息（关键步骤）
┌──────────┐                   ┌───────────┐
│ 机顶盒    │ ───POST─────────> │ EPG服务器  │
│          │ /EPG/jsp/ValidAuthenticationHWCU.jsp
│          │ UserID=xxx                    │
│          │ Authenticator=加密字符串        │ ← 3DES加密
│          │ STBType=xxx                   │
│          │ STBID=xxx                     │
│          │ mac=xxx                       │
└──────────┘                    └──────────┘
     │                                │
     │                                │ 验证成功，返回Session
     │ <──────────────────────────────┘
     │    JSESSIONID = "xxx"
     │    UserToken = "xxx"
     │    stbid = "xxx"

步骤5: 获取频道列表
┌──────────┐                   ┌────────────┐
│ 机顶盒    │ ───POST─────────> │ EPG服务器   │
│          │ /EPG/jsp/getchannellistHWCU.jsp│
│          │ UserToken=xxx                  │
│          │ tempKey=xxx                    │
│          │ stbid=xxx                      │
│          │ Cookie: JSESSIONID=xxx         │
└──────────┘                    └───────────┘
     │                                │
     │                                │ 返回频道列表
     │ <──────────────────────────────┘
```

***

## 完整鉴权认证流程

#### 接口1: 初始认证入口

```
URL: http://{EDS服务器}:8082/EDS/jsp/AuthenticationURL
方法: GET
参数:
  - UserID: {用户业务账号}
  - Action: Login
  - FCCSupport: 1

响应: 302重定向到EPG服务器
Location: http://{EPG服务器IP}:33200/EPG/jsp/AuthenticationURL?UserID={xxx}&Action=Login&FCCSupport=1
```

#### 接口2: 获取认证表单

```
URL: http://{EPG服务器IP}:33200/EPG/jsp/AuthenticationURL
方法: GET
参数:
  - UserID: {用户业务账号}
  - Action: Login
  - FCCSupport: 1

响应: HTML页面，包含表单
<form action="authLoginHWCU.jsp" name="authform" method="post">
  <input type="hidden" name="UserID" value="{用户业务账号}">
  <input type="hidden" name="VIP" value="">
</form>
```

#### 接口3: 提交登录信息

```
URL: http://{EPG服务器IP}:33200/EPG/jsp/authLoginHWCU.jsp
方法: POST
Content-Type: application/x-www-form-urlencoded
参数:
  - UserID: {用户业务账号}
  - VIP: (空)

响应: HTML页面，包含JavaScript变量
var EncryptToken = "{加密令牌}";
var userToken = "{用户令牌}";
```

#### 接口4: 提交认证信息（核心接口）

```
URL: http://{EPG服务器IP}:33200/EPG/jsp/ValidAuthenticationHWCU.jsp
方法: POST
Content-Type: application/x-www-form-urlencoded
参数:
  - UserID: {用户业务账号}
  - Lang: 0
  - SupportHD: 1
  - NetUserID: {运营商认证账号}
  - Authenticator: {3DES加密串}
  - STBType: {机顶盒型号}
  - STBVersion: {机顶盒版本}
  - conntype: dhcp
  - STBID: {设备唯一标识}
  - templateName: (空)
  - areaId: (空)
  - userToken: (从步骤3获取)
  - userGroupId: (空)
  - productPackageId: (空)
  - mac: {MAC地址}
  - UserField: (空)
  - SoftwareVersion: (空)
  - IsSmartStb: undefined
  - desktopId: undefined
  - stbmaker: (空)
  - VIP: (空)

响应: HTML页面，包含
  - Set-Cookie: JSESSIONID={会话ID}
  - UserToken = "{用户令牌}"
  - stbid = "{设备ID}"
```

#### 接口5: 获取频道列表

```
URL: http://{EPG服务器IP}:33200/EPG/jsp/getchannellistHWCU.jsp
方法: POST
Content-Type: application/x-www-form-urlencoded
Cookie: JSESSIONID={会话ID}
参数:
  - conntype: dhcp
  - UserToken: {用户令牌}
  - tempKey: {临时密钥}
  - stbid: {短设备ID}
  - SupportHD: 1
  - UserID: {用户业务账号}
  - Lang: 1

响应: 频道列表
```

***

## 参考文献与致谢

本文的完成离不开以下前辈和开源项目的分享与贡献：

### 技术博客与文章

1. **[RouterOS 抓包 IPTV & 实现 IPTV 的认证和频道列表获取](https://xyx.moe/018-RouterOS-IPTV-packet-capture-and-authentication-implementation.html)**
   - 提供了完整的RouterOS抓包方案和认证流程分析，是本文的重要参考
2. **[CSDN - IPTV认证相关资料](https://bbs.csdn.net/topics/390079170)**
   - 社区讨论，提供了Authenticator生成和密钥相关的思路
3. **[获取IPTV播放列表](https://github.com/supzhang/get_iptv_channels)**
   - GitHub项目，提供了IPTV频道获取的Python实现参考
4. **[cnblogs - IPTV技术笔记](https://www.cnblogs.com/leokale-zz/p/13272694.html)**
   - 技术博客，分享了IPTV认证过程中的踩坑经验
5. **[广东电信IPTV认证与播放列表获取](https://mozz.ie/posts/gdct-iptv-auth-and-fetch-playlist/)**
   - 详细分析了广东电信IPTV的认证流程，虽然运营商不同但技术原理相通
6. **[IPTV广东地区研究](https://lovesykun.cn/archives/iptv-gd.html)**
   - 分享了广东地区IPTV的抓包和认证分析
7. **[恩山论坛 - IPTV认证讨论](https://www.right.com.cn/forum/thread-4059959-1-1.html)**
   - 论坛讨论帖，提供了密钥穷举和DES加密的实现思路

### 特别致谢

**[iptv-tool](https://github.com/super321/iptv-tool)**

特别感谢开源项目 `iptv-tool` 的作者，该项目提供了完整的IPTV工具实现，包括：

- 认证流程的完整封装
- 密钥破解的实现方法
- 频道列表解析功能

本项目在开发过程中参考了该项目的架构设计和实现思路，特此致谢！

***

## ⚠️ 免责声明

**重要提示：请仔细阅读以下声明**

### 一、使用目的声明

1. **本项目的所有内容仅供学习研究和技术交流使用**
2. 本项目旨在帮助用户了解IPTV认证协议和网络通信原理
3. 禁止将本项目用于任何商业用途或非法用途

### 二、法律责任声明

1. **用户在使用本项目时，必须遵守所在国家/地区的法律法规**
2. 用户不得利用本项目从事任何侵犯他人合法权益的行为
3. 用户不得利用本项目绕过运营商的安全机制或访问未授权内容
4. 用户不得将本项目获取的任何数据用于非法传播或商业盈利

### 三、知识产权声明

1. IPTV相关技术、协议及内容的知识产权归 respective 运营商所有
2. 本项目仅提供技术实现参考，不主张任何知识产权
3. 如本项目涉及任何第三方知识产权，请联系删除

### 四、风险提示

1. **使用本项目可能导致以下风险**：
   - 运营商账号被封禁
   - 违反服务协议导致的法律责任
   - 网络安全隐患
   - 设备损坏或数据丢失

2. **作者不对以下情况承担任何责任**：
   - 因使用本项目导致的任何直接或间接损失
   - 因违反法律法规导致的法律后果
   - 因操作不当导致的设备损坏
   - 第三方利用本项目从事的违法行为

### 五、使用限制

**严禁以下行为**：
- ❌ 未经授权访问他人IPTV账号
- ❌ 非法抓取、存储、传播受版权保护的内容
- ❌ 破解、反编译运营商专有系统和软件
- ❌ 利用本项目从事任何违法活动
- ❌ 将本项目用于商业盈利目的
- ❌ 删除或修改本免责声明

### 六、合规使用建议

1. 仅供个人学习研究，在自己的设备和账号上测试
2. 遵守运营商的服务条款和使用协议
3. 不得将获取的数据用于公开传播或共享
4. 如发现本项目存在侵权内容，请立即停止使用并联系作者删除

### 七、其他声明

1. 本项目按"现状"提供，不提供任何形式的担保
2. 作者保留随时修改、删除本项目的权利
3. 使用本项目即表示您已阅读并同意本免责声明的所有条款
4. 如不同意本声明，请立即停止使用并删除本项目

---

**再次强调：本项目仅供学习研究，请合法合规使用！**

**任何因违反本声明或法律法规导致的后果，由使用者自行承担！**

***

*探索于 2026年4月*
