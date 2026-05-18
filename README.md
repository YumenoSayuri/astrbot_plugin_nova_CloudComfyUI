# Nova 梦羽绘图插件

## 简介

Nova 梦羽绘图插件默认通过 Node undici 桥接调用梦羽 AI 绘图接口，并优先使用同一条 Node 出网链路下载返回图片，适合云服务器无法直接访问返回图地址的场景。

支持能力：

- AI 主动文生图
- AI 主动改图
- `/mengyudraw` 手动命令生图/改图
- 命令开始时先发送“正在使用comfyui画图，请稍后...”
- 自动从消息或引用消息中提取图片 URL
- prompt 内解析并删除 `modelX`
- prompt 内解析并删除 `cfgX`
- prompt 内解析并删除 `stepsX`
- prompt 内解析并删除 `seedX`
- prompt 末尾解析分辨率
- 本地生成随机 seed
- 命令链路与 AI 主动链路统一参数构造
- 命令命中后显式 `stop_event`，避免失败后继续唤起主 AI
- 命令成功时默认只发图，成功摘要写日志
- Cloudflare Worker 中转兼容

---

## v1.3.1 修复说明

### 模型优先级修复

已修复 AI 主动文生图链路里，prompt 中明明写了 `model1`，最终却仍然使用默认模型 `10` 的问题。

修复前的根因是：

- [`nova_draw_image()`](AstrBot/data/plugins/astrbot_plugin_nova_mengyudraw/main.py:714) 会给 [`_run_draw_request()`](AstrBot/data/plugins/astrbot_plugin_nova_mengyudraw/main.py:628) 传入默认 `model_index`
- [`_run_draw_request()`](AstrBot/data/plugins/astrbot_plugin_nova_mengyudraw/main.py:654) 原先优先采用入口传入值
- 于是 prompt 中提取出的 `modelX` 会被默认模型覆盖

现在模型优先级已调整为：

```text
prompt里的modelX > 入口显式传入model_index > 面板default_model_index
```

这意味着：

- 如果 prompt 里写了 `model1`，就会实际使用模型 `1`
- 如果 prompt 没写 `modelX`，就会继续回落到面板默认模型
- 命令入口和 AI 主动入口在模型解析行为上保持一致

---

## 本次版本关键行为

### 统一请求与下载链路

现在以下两种方式，都会走统一的请求和下载流程：

- [`nova_draw_image()`](AstrBot/data/plugins/astrbot_plugin_nova_mengyudraw/main.py:714)
- [`mengyudraw_command()`](AstrBot/data/plugins/astrbot_plugin_nova_mengyudraw/main.py:812)

统一经过：

- [`_run_draw_request()`](AstrBot/data/plugins/astrbot_plugin_nova_mengyudraw/main.py:628)
- [`_call_generate_api()`](AstrBot/data/plugins/astrbot_plugin_nova_mengyudraw/main.py:386)
- [`_download_image()`](AstrBot/data/plugins/astrbot_plugin_nova_mengyudraw/main.py:540)
- [`_download_image_via_undici()`](AstrBot/data/plugins/astrbot_plugin_nova_mengyudraw/main.py:470)

也就是说，不只是“请求生成”走 Node 桥，连“下载返回图片”也会优先走 Node 桥。

### 云服务器连不上返回图地址时怎么解决

你遇到的典型问题是：

1. 梦羽接口本身可请求成功
2. 返回了 `image_url`
3. 但云服务器直连这个返回图地址失败
4. Python 下载阶段报连接错误

现在插件的下载策略是：

```text
优先 Node undici 下载 -> 失败再回退 HTTPX 下载
```

这能解决很多“接口能通，但返回图地址不通”的服务器环境问题。

### 开始提示行为

以下入口在真正开始处理前，会先发送提示文本：

- [`nova_draw_image()`](AstrBot/data/plugins/astrbot_plugin_nova_mengyudraw/main.py:714)
- [`nova_edit_image()`](AstrBot/data/plugins/astrbot_plugin_nova_mengyudraw/main.py:757)
- [`mengyudraw_command()`](AstrBot/data/plugins/astrbot_plugin_nova_mengyudraw/main.py:812)

提示内容固定为：

```text
正在使用comfyui画图，请稍后...
```

### prompt 内控制参数提取

当前支持直接在 prompt 中写入并自动提取删除：

```text
model8
model10
model18
model19
cfg3.5
steps28
seed123456
1216x832
portrait
landscape
square
1024
```

插件会自动：

- 从 prompt 中提取这些控制参数
- 从 clean prompt 中删除它们
- 把真正的画面描述发送给梦羽
- 在日志中打印解析结果

### 随机 Seed 逻辑

- 文生图未指定 seed 时，由插件本地随机生成正整数
- 编辑模型默认仍允许 `-1`
- 请求日志会打印实际 seed
- 如主动或命令路径成功，结果内会保留实际 seed

### 自动质量词

当前自动补齐的通用质量词只有：

```text
masterpiece
best quality
high quality
```

不会自动补会改变主体语义的词。

### 命令停止传播

[`mengyudraw_command()`](AstrBot/data/plugins/astrbot_plugin_nova_mengyudraw/main.py:812) 在以下场景会显式 `stop_event`：

- 参数缺失
- 防抖拦截
- 正在处理中
- 成功返回
- 失败返回

---

## 给 AI 的使用说明

### 文生图工具

对应 [`nova_draw_image()`](AstrBot/data/plugins/astrbot_plugin_nova_mengyudraw/main.py:714)

触发条件：

- 只有用户明确提到“用comfyui生图”“用comfyui画图”“画个色图”“涩图”时才调用

Prompt 要求：

- 文生图 prompt 必须使用详细英文 tag 串
- 不要用中文自然语言当文生图 prompt
- prompt 应尽量包含主体、发色、服装、姿势、场景、光照、画风、镜头等英文标签

示例：

```text
prompt="Nahida, Genshin Impact, dendro archon, green hair, green eyes, white dress, mystical, forest background, anime style, model10, cfg3.5, steps28, seed123456, 1216x832"
```

### 图编辑工具

对应 [`nova_edit_image()`](AstrBot/data/plugins/astrbot_plugin_nova_mengyudraw/main.py:757)

触发条件：

- 只有用户明确提到“用comfyui改一下这张图”“用comfyui把这张图改成...”时才优先调用
- 或者用户明确要求修改色图/涩图时调用

Prompt 要求：

- edit prompt 可以直接使用中文自然语言
- 直接描述要改什么即可

原图来源必须二选一：

- `use_message_images=true`
- `image_source="图片URL"`

示例：

```text
prompt="把头发改成黑发，保持人物脸部、服装和构图不变"
use_message_images=true
```

---

## 命令说明

### 基础命令

```text
/mengyudraw <提示词>
```

### 示例

```text
/mengyudraw 1girl, silver hair, red eyes, portrait
/mengyudraw Nahida, Genshin Impact, forest background, model10, cfg3.5, steps28, 1216x832
/mengyudraw 把这张图头发改成黑发 model19
/mengyudraw 把这张图背景改成海边 model18 --image_source=https://example.com/a.png
```

### 模型写法

命令里支持直接写：

```text
model8
model10
model18
model19
```

### CFG / 步数 / Seed 写法

命令里支持直接写：

```text
cfg3.5
steps28
seed123456
```

### 分辨率写法

支持以下分隔符：

```text
x
X
*
×
-
```

例如：

```text
1216x832
1216X832
1216*832
1216×832
1216-832
```

### 图片编辑说明

如果当前消息或引用消息里带图，且模型是 `18/19`，插件会自动提取该图 URL 作为 `image_source`。

---

## Cloudflare Worker 代理部署

当云端 AstrBot 直连梦羽接口或返回图片地址仍不稳定时，可以改用插件目录中的 [`cf_worker_proxy.js`](AstrBot/data/plugins/astrbot_plugin_nova_mengyudraw/cf_worker_proxy.js:1) 作为中转层。

### 方案说明

推荐搭配方式：

- 插件面板中的 [`base_url`](AstrBot/data/plugins/astrbot_plugin_nova_mengyudraw/_conf_schema.json:2) 改成你的 Worker 域名
- 插件仍继续传 `api_key`
- Worker 负责把 `POST /api/v1/generate_image` 转发到 `https://sd.exacg.cc/api/v1/generate_image`
- 插件收到返回 JSON 后，继续优先用 Node 桥去下载 `image_url`

### Worker 脚本

文件位置：

- [`cf_worker_proxy.js`](AstrBot/data/plugins/astrbot_plugin_nova_mengyudraw/cf_worker_proxy.js:1)

它提供两个路由：

- `GET /health`
- `POST /api/v1/generate_image`

### 部署步骤

1. 登录 Cloudflare Dashboard
2. 打开 Workers & Pages
3. 新建一个 Worker
4. 把 [`cf_worker_proxy.js`](AstrBot/data/plugins/astrbot_plugin_nova_mengyudraw/cf_worker_proxy.js:1) 全部内容粘贴进去
5. 部署后拿到一个域名，例如：

```text
https://nova-mengyudraw-proxy.your-subdomain.workers.dev
```

### 插件面板怎么填

把 [`base_url`](AstrBot/data/plugins/astrbot_plugin_nova_mengyudraw/_conf_schema.json:2) 从：

```text
https://sd.exacg.cc
```

改成：

```text
https://nova-mengyudraw-proxy.your-subdomain.workers.dev
```

例如你当前验证过可用的是：

```text
https://mengyu.huibaobao.xyz
```

建议：

- `api_key`：继续填梦羽的 key
- `proxy_url`：优先留空，减少变量；如果你的服务器本身需要代理，再填
- 其他默认参数照旧

### 健康检查

部署后可先访问：

```text
https://你的worker域名/health
```

预期返回：

```json
{
  "success": true,
  "service": "nova-mengyudraw-cf-worker-proxy",
  "upstream": "https://sd.exacg.cc"
}
```

### 已验证情况

- Node `fetch` 通过 Worker 可成功生图
- Worker 能返回梦羽标准 JSON
- 返回图地址可由插件的 Node 下载桥处理
- 你的域名 [`mengyu.huibaobao.xyz`](https://mengyu.huibaobao.xyz) 已验证可正常走 Worker 链路

---

## 面板默认值

这些值主要由插件面板配置控制：

- 默认文生图模型：`10`
- 默认步数：`28`
- 默认 CFG：`7`
- 默认编辑模型：`19`
- 默认 negative_prompt：使用面板配置
- 默认代理：按面板配置
- 默认 base_url：`https://sd.exacg.cc`

---

## 版本

当前版本：[`v1.3.1`](AstrBot/data/plugins/astrbot_plugin_nova_mengyudraw/metadata.yaml:4)