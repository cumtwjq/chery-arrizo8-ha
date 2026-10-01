# 艾瑞泽8 → Home Assistant（研究阶段）

公开发布包在本仓库的 **Releases** 页面：HA 集成使用 `chery_arrizo8-experimental.zip`；Windows 本地抓取工具使用 `arrizo8-local-capture.zip`。请先阅读 [安装说明](INSTALL.md)和[本地抓取说明](local_tool/本地抓取说明.md)。压缩包均不含车主的令牌、VIN 或抓包内容；每位车主需从自己的奇瑞汽车 App 导入只读车况请求。

目标：将国内版「奇瑞汽车」App 中，22 款艾瑞泽8雅的车况以**只读实体**接入 Home Assistant／冬瓜 HAOS。已验证车况接口，并制作了可手动导入已签名请求的[实验版集成](INSTALL.md)。0.2.0 增加车辆位置实体及[仪表板示例](DASHBOARD.md)；0.3.0 为测量实体添加单位；0.4.0 固定高德坐标校准，将「配置」改为更新抓包请求，并按实际响应添加更多车况传感器。0.5.0 根据真实抓包字段补齐中文名称，将设备页精简到常用车况，并逐字段显示已确认的状态代码。0.5.1 修复文字状态被误判成数字导致“不可用”的问题。0.5.2 给设备页实体名称添加排序编号。0.6.0 新增凭证到期修复提醒、明确鉴权失败时重新认证和 HA 上次成功读取时间。手机号登录和自动续期仍在研究。



## 下一步需要的数据

当前抓到的 `access_token` 是有到期时间的 JWT。两次在 iPhone 上退出并使用手机号密码重新登录后，车况请求仍使用同一个令牌，到期时间没有延长；第二次测试还关闭了该 App 的蜂窝数据。随后使用短信验证码登录，车况请求仍使用旧令牌，且短信发送前需要滑动拼图。代理未捕获到可复现的登录请求。需要确认服务端如何生成请求签名，以及令牌到期后的登录／续期方式，才能实现手机号密码自动登录。实验版 0.1.1 增加“登录凭证到期时间”实体，方便提前发现到期；到期后仍需重新抓取只读请求，并通过集成的“配置”导入。

补充验证：开启全域名请求摘要记录后，再次关闭 App 蜂窝数据、通过电脑热点代理使用手机号密码登录。代理能看到 App 的车况请求及同一个旧令牌，仍未出现可辨认的登录接口。`/cheryAppData/DKtrans/business` 有十六进制参数，具体用途尚未确认；不能据此推断它可用于登录或续期。

## 本机 `omoda9`（Chery Connect 1.14.0-beta.13）源码对照

- 其“Chery — Europe”预设使用 `https://eu-chery.cheryinternational.com/api`，车况经欧洲 `tspconsole-eu.cheryinternational.com`；本车实测接口在 `cloudrivechery.mychery.com/cheryAppData/vehicleRealtimeData/...`，不是改一个地区参数就能调用的同一路由。
- 欧洲版密码登录调用 BFF `/auth/oauth2/token`，通过 `refresh_token` 再调用同一路由续期。当前国内版车况 JWT 的 `client_id` 为 `ntsp-app`，而源码的 BFF 应用凭据是 `legendApp`；不能把欧洲版的登录令牌直接当作国内车况令牌。
- `core/tsp_sign.py` 的签名输出与国内抓包一样长 44 字符，且都为大写 Base64 风格。用它的欧洲密钥、实际国内请求正文和时间戳离线计算，**未匹配**抓到的签名；这只能说明欧洲实现不能原样复用，不能排除签名规则相似而密钥或字段不同。
- `certs/store.json` 所列 MQTT 区域没有中国大陆的生产服务器。其车况推送链路不能直接替换本车已验证的只读接口。

## 不等到令牌到期的登录研究线索

2026-10-01 在本机 Windows 安卓子系统 2407.40000.4.0（Android 13）中验证：ADB 已授权，官方 APK 安装成功，系统支持 ARM64 转译；但 `com.digitalmall.chery` 启动后一直停在奇瑞 Logo，未进入登录页。强制停止后重启仍相同，主进程持续占用约一个 CPU 核心，日志没有明确的网络或 Java 崩溃原因。因此目前不能靠此 WSA 实例抓到登录调用，也不能据此断定实体安卓手机必然有同样问题。

可能的原因之一是 WSA 的 ARM 转译层 Houdini：[上游问题报告](https://github.com/casualsnek/waydroid_script/issues/285)记录了 2026 年 9 月起旧 WSA Houdini 构建运行 ARM 应用时卡在启动画面的现象，与本机表现相似。这还不是对本机根因的确认；不应修改电脑系统时间或随意替换转译库来作为集成方案。

国内官方安卓 APK 的 Flutter `libapp.so` 中出现 `LoginApiService`、`refreshTokenApi`、`api/v1/uaa/oauth/refresh-token`、`api/v1/uaa/mobile/mobile-code-login` 和 `api/v1/uaa/mobile/token/secret/app`。这些只是静态字符串，可能属于 App 的社区账号模块；尚不能证明它们能换发车况所用 `client_id=ntsp-app` 的令牌。下一步应定位调用链，并在不提交用户密码的条件下验证令牌类型。不要把这些候选路径直接加入 HA 集成。

不要发送手机号、验证码、Token、Cookie、VIN、车牌、位置坐标或未脱敏的完整 HAR。`research/inspect_har.py` 只输出域名、脱敏路径、HTTP 方法与 JSON 字段名，可先用它生成研究摘要。字段名也可能包含个人信息，分享前仍应人工检查。

有了可复现的只读请求后，再实现 HA 的配置流程、会话续期、车辆发现、状态传感器和合理的刷新间隔。第一版不实现开锁、启动、空调等远程控制。
