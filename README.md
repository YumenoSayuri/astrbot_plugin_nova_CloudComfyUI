# Nova 梦羽绘图插件

## 简介

Nova 梦羽绘图插件默认通过 Node undici 桥接或 Cloudflare Worker 中转调用梦羽 AI 绘图接口，支持：

- AI 主动文生图
- AI 主动改图
- `/sexdraw` 手动命令生图/改图
- 自动从消息或引用消息中提取图片 URL
- prompt 内解析并删除 `modelX`
- prompt 内解析并删除 `cfgX`
- prompt 内解析并删除 `stepsX`
- prompt 内解析并删除 `seedX`
- prompt 末尾解析分辨率
- 本地生成随机 seed
- 命令链路与 AI 主动链路统一参数构造
- 命令命中后显式 stop_event，避免失败后继续唤起主 AI
- 命令成功时默认只发图，成功摘要写日志

---

## 本次版本关键行为

### 统一请求链路
现在以下两种方式，都会走同一套参数处理逻辑：

- [`nova_draw_image()`](AstrBot/data/plugins/astrbot_plugin_nova_sexdraw/main.py:575)
- [`sexdraw_command()`](AstrBot/data/plugins/astrbot_plugin_nova_sexdraw/main.py:672)

统一经过：

- [`_run_draw_request()`](AstrBot/data/plugins/astrbot_plugin_nova_sexdraw/main.py:503)
- [`_inject_quality_tags()`](AstrBot/data/plugins/astrbot_plugin_nova_sexdraw/main.py:542)
- [`_normalize_seed()`](AstrBot/data/plugins/astrbot_plugin_nova_sexdraw/main.py:227)
- [`_call_generate_api()`](AstrBot/data/plugins/astrbot_plugin_nova_sexdraw/main.py:385)

这意味着手动输入和 AI 主动调用，不再各自手搓 payload。

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

日志中会看到：

```text
extracted_model=...
extracted_cfg=...
extracted_steps=...
extracted_seed=...
extracted_resolution=...
```

如果没有识别到，就显示：

```text
none
```

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

不会自动补：

```text
cute
1girl
solo
```

这类会改变主体语义的词。

### 命令停止传播
[`sexdraw_command()`](AstrBot/data/plugins/astrbot_plugin_nova_sexdraw/main.py:672) 在以下场景会显式 stop_event：

- 参数缺失
- 防抖拦截
- 正在处理中
- 成功返回
- 失败返回

这样即使梦羽接口失败，也不会继续把同一条命令喂给后续主 AI 流程。

### 命令成功返回策略
为避免某些平台链路在“先发图再发成功文本”时产生二次异常，当前命令成功时默认：

- 群内只发图片
- 成功摘要写日志
- 失败时才返回错误文本

---

## 给 AI 的使用说明

### 文生图工具
对应 [`nova_draw_image()`](AstrBot/data/plugins/astrbot_plugin_nova_sexdraw/main.py:575)

触发条件：

- 只有用户明确提到“用comfyui生图”“用comfyui画图”“画个色图”“涩图”时才调用

Prompt 要求：

- 文生图 prompt 必须使用详细英文 tag 串
- 不要用中文自然语言当文生图 prompt
- prompt 应尽量包含：主体、发色、服装、姿势、场景、光照、画风、镜头等英文标签

必填参数：

- `prompt`

其他规则：

- `steps`、`cfg`、`negative_prompt` 由插件内部和面板默认值处理
- 需要指定模型时，把 `model10`、`model19` 或其他 `modelX` 直接写进 prompt
- 需要指定 CFG 时，把 `cfg3.5` 这类标记写进 prompt
- 需要指定步数时，把 `steps28` 这类标记写进 prompt
- 需要指定 seed 时，把 `seed123456` 这类标记写进 prompt
- 需要指定分辨率时，把 `1216x832`、`1216-832`、`portrait` 这类尺寸或预设直接写进 prompt
- 未指定 seed 时自动随机
- 文生图默认模型为 `10`

示例：

```text
prompt="Nahida, Genshin Impact, dendro archon, green hair, green eyes, white dress, mystical, forest background, anime style, model10, cfg3.5, steps28, seed123456, 1216x832"
```

---

### 图编辑工具
对应 [`nova_edit_image()`](AstrBot/data/plugins/astrbot_plugin_nova_sexdraw/main.py:617)

触发条件：

- 只有用户明确提到“用comfyui改一下这张图”“用comfyui把这张图改成...”时才优先调用
- 或者用户明确要求修改色图/涩图时调用

Prompt 要求：

- edit 的 prompt 可以直接使用中文自然语言
- 直接描述要改什么即可

必填参数：

- `prompt`

原图来源必须二选一：

- `use_message_images=true`
- `image_source="图片URL"`

默认值：

- `model_index=19`
- `19` 即 `Qwen Image Edit2511版`

额外规则：

- edit 模型不会发送 `steps`
- edit 模型不会发送 `cfg`
- edit 模型没有图片时会尝试从当前消息或引用消息中取图

示例：

```text
prompt="把头发改成黑发，保持人物脸部、服装和构图不变"
use_message_images=true
```

---

## 命令说明

### 基础命令

```text
/sexdraw <提示词>
```

### 示例

```text
/sexdraw 1girl, silver hair, red eyes, portrait
/sexdraw Nahida, Genshin Impact, forest background, model10, cfg3.5, steps28, 1216x832
/sexdraw 把这张图头发改成黑发 model19
/sexdraw 把这张图背景改成海边 model18 --image_source=https://example.com/a.png
```

### 模型写法

命令里支持直接写：

```text
model8
model10
model18
model19
```

插件会自动提取并从 prompt 删除。

### CFG / 步数 / Seed 写法

命令里支持直接写：

```text
cfg3.5
steps28
seed123456
```

插件会自动提取并从 prompt 删除。

### 模型列表

```text
0  = Miaomiao Harem vPred Dogma 1.1
1  = MiaoMiao Pixel 像素 1.0
2  = NoobAIXL V1.1
3  = illustrious_pencil 融合
4  = [全新模型]one_obsession
5  = [全新模型]MiaoMiao RealSkin EPS 1.3
6  = [全新模型]Newbie exp 0.1
7  = [全新模型-服务器2]Newbie exp 0.1
8  = [全新模型]MiaoMiao RealSkin vPred 1.1
9  = [新服开放]MiaoMiao RealSkin vPred 1.0
10 = [全新模型]Wainsfw illustrious v16
11 = [新服开放]Wainsfw illustrious v15
12 = [新服开放]MiaoMiao Harem 1.75
13 = [新服开放]MiaoMiao Harem 1.6G
14 = (testa)服务器1 Wainsfw Illustrious v13
15 = [维护]服务器2 Wainsfw Illustrious v13
16 = [维护]Wainsfw Illustrious v11
17 = (testa)真人模型Nsfw-Real
18 = Qwen Image Edit版
19 = Qwen Image Edit2511版
20 = 视频生成模型服务器1 wan2.1-14B-fast(3秒视频)
21 = 视频生成模型服务器2 wan2.2-14B-fast(5秒视频)(NSFW Lora)
22 = [新年贺庆版]视频生成模型服务器3 rpwan2.2-14B-fast(5秒视频)
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

当云端 AstrBot 直连梦羽或 Node 桥接仍被 Cloudflare 拦截时，可以改用插件目录中的 [`cf_worker_proxy.js`](AstrBot/data/plugins/astrbot_plugin_nova_sexdraw/cf_worker_proxy.js:1) 作为最省事的中转层。

### 方案说明

当前采用的是最省事方案：

- AstrBot 插件继续照常传 `api_key`
- 插件面板中的 [`base_url`](AstrBot/data/plugins/astrbot_plugin_nova_sexdraw/_conf_schema.json:2) 改成你的 Worker 域名
- Worker 负责把 `POST /api/v1/generate_image` 转发到 `https://sd.exacg.cc/api/v1/generate_image`
- Worker 原样返回梦羽 JSON
- 插件继续按原逻辑下载 `image_url`、发图、显示积分和模型信息

### Worker 脚本

文件位置：

- [`cf_worker_proxy.js`](AstrBot/data/plugins/astrbot_plugin_nova_sexdraw/cf_worker_proxy.js:1)

它提供两个路由：

- `GET /health`
- `POST /api/v1/generate_image`

### 部署步骤

1. 登录 Cloudflare Dashboard
2. 打开 Workers & Pages
3. 新建一个 Worker
4. 把 [`cf_worker_proxy.js`](AstrBot/data/plugins/astrbot_plugin_nova_sexdraw/cf_worker_proxy.js:1) 全部内容粘贴进去
5. 部署后拿到一个域名，例如：

```text
https://nova-sexdraw-proxy.your-subdomain.workers.dev
```

### 插件面板怎么填

把 [`base_url`](AstrBot/data/plugins/astrbot_plugin_nova_sexdraw/_conf_schema.json:2) 从：

```text
https://sd.exacg.cc
```

改成：

```text
https://nova-sexdraw-proxy.your-subdomain.workers.dev
```

例如你当前验证过可用的是：

```text
https://mengyu.huibaobao.xyz
```

其他字段建议：

- `api_key`：继续填梦羽的 key
- `proxy_url`：建议先留空，避免多余变量
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
  "service": "nova-sexdraw-cf-worker-proxy",
  "upstream": "https://sd.exacg.cc"
}
```

### 已验证情况

Nova 已本地真实验证：

- Node `fetch` 通过 Worker 可成功生图
- Worker 能返回梦羽标准 JSON
- `image_url` 可成功下载
- 你的域名 [`mengyu.huibaobao.xyz`](https://mengyu.huibaobao.xyz) 已验证可正常走 Worker 链路

### 注意事项

- Worker 当前只转发 `/api/v1/generate_image`
- Worker 只是转发层，不替你保存梦羽 `api_key`
- 插件仍然会把 `Authorization: Bearer ...` 传给 Worker，再由 Worker 转发给梦羽
- 某些环境下 Python `requests` 到 Worker 可能被 TLS/连接层掐断，但 Node 链路已验证可通
- 当前插件主请求链本来就是 Node 桥接，所以 Worker 方案与插件实际请求路径是匹配的

---

## 面板默认值

这些值主要由插件面板配置控制：

- 默认文生图模型：`10`
- 默认步数：`28`
- 默认 CFG：`5`
- 默认编辑模型：`19`
- 默认 negative_prompt：使用面板配置
- 默认代理：按面板配置
- 默认 base_url：`https://sd.exacg.cc`

---

## 版本

当前版本：[`v1.2.3`](AstrBot/data/plugins/astrbot_plugin_nova_sexdraw/metadata.yaml:4)