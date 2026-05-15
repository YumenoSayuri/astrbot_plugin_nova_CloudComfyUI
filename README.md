# Nova 梦羽绘图插件

## 给 AI 的使用说明

### 文生图工具
对应 [`nova_draw_image()`](AstrBot/data/plugins/astrbot_plugin_nova_sexdraw/main.py:485)

触发条件：
- 只有用户明确提到“用comfyui生图”“用comfyui画图”“画个色图”“涩图”时才调用

Prompt要求：
- 文生图 prompt 必须使用详细英文 tag 串
- 不要用中文自然语言当文生图 prompt
- prompt 应尽量包含：主体、发色、服装、姿势、场景、光照、画风、镜头等英文标签

必填参数：
- `prompt`

其他参数：
- `resolution`、`model`、`steps`、`cfg`、`negative_prompt` 都由插件内部解析或走面板默认值
- 需要指定模型时，把 `model10` 直接写进 prompt
- 需要指定分辨率时，把 `1216x832`、`1216-832` 这类尺寸直接写进 prompt

默认值：
- `model_index=10`
- `steps=28`
- `cfg=5`
- `negative_prompt` 使用面板内置默认值

示例：

```text
prompt="1girl, black hair, long hair, red eyes, white dress, outdoors, night, city lights, cinematic lighting, masterpiece, best quality, model10, 1216x832"
```

---

### 图编辑工具
对应 [`nova_edit_image()`](AstrBot/data/plugins/astrbot_plugin_nova_sexdraw/main.py:562)

触发条件：
- 只有用户明确提到“用comfyui改一下这张图”“用comfyui把这张图改成...”时才优先调用
- 或者用户明确要求修改色图/涩图时调用

Prompt要求：
- edit 的 prompt 可以直接使用中文自然语言
- 直接描述要改什么即可

必填参数：
- `prompt`
- 原图必须二选一提供：
  - `use_message_images=true`
  - `image_source="图片URL"`

可选参数：
- `image_source`

默认值：
- `model_index=19`
- `19` 就是 `Qwen Image Edit2511版`

额外规则：
- edit 模型不会发送 `steps`
- edit 模型不会发送 `cfg`
- “用comfyui改一下这张图”默认走 `model19`

示例：

```text
prompt="把头发改成黑发，保持人物脸部、服装和构图不变"
use_message_images=true
```

---

## 命令补充说明

### 模型写法
命令里支持直接写：

```text
model10
model19
```

插件会自动提取并从 prompt 删除。

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

---

## 面板默认值

这些值主要由插件面板配置控制：

- 默认文生图模型：`10`
- 默认步数：`28`
- 默认 CFG：`5`
- 默认编辑模型：`19`
- 默认 negative_prompt：内置

---

## 版本

当前版本：[`v1.2.1`](AstrBot/data/plugins/astrbot_plugin_nova_sexdraw/metadata.yaml:4)