# Nova 梦羽绘图插件

## 简介

Nova 梦羽绘图插件默认通过 Node undici 桥接调用梦羽 AI 绘图接口，支持：

- AI 主动文生图
- AI 主动改图
- `/sexdraw` 手动命令生图/改图
- 自动从消息或引用消息中提取图片 URL
- prompt 内解析 `model10`、`model19`
- prompt 末尾解析分辨率
- 本地生成随机 seed
- 命令链路与 AI 主动链路统一参数构造
- 命令命中后显式 stop_event，避免失败后继续唤起主 AI

---

## 本次版本关键行为

### 统一请求链路
现在以下两种方式，都会走同一套参数处理逻辑：

- [`nova_draw_image()`](AstrBot/data/plugins/astrbot_plugin_nova_sexdraw/main.py:575)
- [`sexdraw_command()`](AstrBot/data/plugins/astrbot_plugin_nova_sexdraw/main.py:672)

统一经过：

- [`_run_draw_request()`](AstrBot/data/plugins/astrbot_plugin_nova_sexdraw/main.py:503)
- [`_inject_quality_tags()`](AstrBot/data/plugins/astrbot_plugin_nova_sexdraw/main.py:490)
- [`_normalize_seed()`](AstrBot/data/plugins/astrbot_plugin_nova_sexdraw/main.py:227)
- [`_call_generate_api()`](AstrBot/data/plugins/astrbot_plugin_nova_sexdraw/main.py:385)

这意味着手动输入和 AI 主动调用，不再各自手搓 payload。

### 随机 Seed 逻辑
- 文生图未指定 seed 时，由插件本地随机生成正整数
- 编辑模型默认仍允许 `-1`
- 返回文案会带上实际 seed
- 日志会打印实际请求参数摘要

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
- 需要指定模型时，把 `model10`、`model19` 直接写进 prompt
- 需要指定分辨率时，把 `1216x832`、`1216-832` 这类尺寸直接写进 prompt
- 未指定 seed 时自动随机
- 文生图默认模型为 `10`

示例：

```text
prompt="Nahida, Genshin Impact, dendro archon, green hair, green eyes, white dress, mystical, forest background, anime style, 1216x832, model10"
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
/sexdraw Nahida, Genshin Impact, forest background, model10, 1216x832
/sexdraw 把这张图头发改成黑发 model19
/sexdraw 把这张图背景改成海边 --image_source=https://example.com/a.png model19
```

### 模型写法

命令里支持直接写：

```text
model10
model19
```

插件会自动提取并从 prompt 删除。

 MODEL_CHOICES = {
        0: "Miaomiao Harem vPred Dogma 1.1",
        1: "MiaoMiao Pixel 像素 1.0",
        2: "NoobAIXL V1.1",
        3: "illustrious_pencil 融合",
        4: "[全新模型]one_obsession",
        5: "[全新模型]MiaoMiao RealSkin EPS 1.3",
        6: "[全新模型]Newbie exp 0.1",
        7: "[全新模型-服务器2]Newbie exp 0.1",
        8: "[全新模型]MiaoMiao RealSkin vPred 1.1",
        9: "[新服开放]MiaoMiao RealSkin vPred 1.0",
        10: "[全新模型]Wainsfw illustrious v16",
        11: "[新服开放]Wainsfw illustrious v15",
        12: "[新服开放]MiaoMiao Harem 1.75",
        13: "[新服开放]MiaoMiao Harem 1.6G",
        14: "(testa)服务器1 Wainsfw Illustrious v13",
        15: "[维护]服务器2 Wainsfw Illustrious v13",
        16: "[维护]Wainsfw Illustrious v11",
        17: "(testa)真人模型Nsfw-Real",
        18: "Qwen Image Edit版",
        19: "Qwen Image Edit2511版",
        20: "视频生成模型服务器1 wan2.1-14B-fast(3秒视频)",
        21: "视频生成模型服务器2 wan2.2-14B-fast(5秒视频)(NSFW Lora)",
        22: "[新年贺庆版]视频生成模型服务器3 rpwan2.2-14B-fast(5秒视频)",
    }
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

当前版本：[`v1.2.2`](AstrBot/data/plugins/astrbot_plugin_nova_sexdraw/metadata.yaml:4)