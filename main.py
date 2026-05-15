"""
Nova SexDraw - 梦羽 AI 绘图插件
默认通过 Node undici 桥接请求梦羽接口，Python 路径仅保留作兼容/兜底逻辑
"""

import json
import re
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any

import httpx

from astrbot.api.message_components import Image as AstrImageComponent
from astrbot.api.message_components import Reply

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.message_components import Image
from astrbot.api.star import Context, Star, StarTools


class NovaSexDraw(Star):
    """Nova SexDraw - 梦羽 AI 绘图接口生成图片"""

    RESOLUTION_PRESETS = {
        "square": "512x512",
        "landscape": "768x512",
        "portrait": "512x768",
        "1024": "1024x1024",
    }

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

    EDIT_MODEL_INDEXES = {18, 19}
    VIDEO_MODEL_INDEXES = {20, 21, 22}

    def __init__(self, context: Context, config: dict):
        super().__init__(context)
        self.config = config
        self.data_dir = StarTools.get_data_dir()
        self.plugin_dir = Path(__file__).resolve().parent
        self.image_dir = Path(self.data_dir) / "images"
        self.image_dir.mkdir(parents=True, exist_ok=True)

        self._user_last_request: dict[str, float] = {}
        self._processing_users: set[str] = set()
        self._client: httpx.AsyncClient | None = None
        self._base_url: str = ""
        self._api_key: str = ""
        self._proxy_url: str = ""
        self._enable_undici_fallback: bool = True

    async def initialize(self):
        """初始化插件"""
        timeout = httpx.Timeout(self.config.get("timeout", 180))
        proxy_url = str(self.config.get("proxy_url", "") or "").strip()
        transport = httpx.AsyncHTTPTransport(proxy=proxy_url) if proxy_url else None

        self._client = httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            transport=transport,
        )

        self._base_url = self.config.get("base_url", "https://sd.exacg.cc").strip().rstrip("/")
        self._api_key = self.config.get("api_key", "").strip()
        self._proxy_url = proxy_url
        self._enable_undici_fallback = bool(self.config.get("enable_undici_fallback", True))

        logger.info(f"[NovaSexDraw] API Base URL: {self._base_url}")
        logger.info(f"[NovaSexDraw] Proxy: {self._proxy_url or 'disabled'}")
        logger.info(f"[NovaSexDraw] Undici fallback: {self._enable_undici_fallback}")
        logger.info("[NovaSexDraw] 插件初始化完成")

    async def terminate(self):
        """清理资源"""
        if self._client:
            await self._client.aclose()
            self._client = None
        logger.info("[NovaSexDraw] 插件已终止")

    def _parse_resolution(self, resolution: str | None) -> tuple[int, int]:
        """解析分辨率字符串，返回 width, height"""
        if not resolution:
            resolution = self.config.get("default_resolution", "512x768")

        res = str(resolution).strip().lower()
        if res in self.RESOLUTION_PRESETS:
            res = self.RESOLUTION_PRESETS[res]

        normalized = (
            res.replace("×", "x")
            .replace("✕", "x")
            .replace("✖", "x")
            .replace("*", "x")
            .replace("X", "x")
            .replace("-", "x")
        )
        match = re.match(r"(\d+)\s*x\s*(\d+)", normalized)
        if match:
            width = max(64, min(2048, int(match.group(1))))
            height = max(64, min(2048, int(match.group(2))))
            return width, height

        fallback = self.config.get("default_resolution", "512x768")
        return self._parse_resolution(fallback if fallback != resolution else "512x768")

    def _check_debounce(self, user_id: str) -> bool:
        """检查防抖，返回 True 表示需要拒绝"""
        interval = self.config.get("debounce_interval", 15)
        if interval <= 0:
            return False

        now = time.time()
        last = self._user_last_request.get(user_id, 0)
        if now - last < interval:
            return True

        self._user_last_request[user_id] = now
        return False

    def _normalize_steps(self, steps: str | int | None, model_index: int) -> int:
        try:
            value = int(steps) if steps not in ("", None) else 0
        except (TypeError, ValueError):
            value = 0

        if value <= 0:
            value = int(self.config.get("default_steps", 20))

        if model_index in self.EDIT_MODEL_INDEXES:
            return value

        return max(1, min(50, value))

    def _normalize_cfg(self, cfg: str | float | None, model_index: int) -> float:
        try:
            value = float(cfg) if cfg not in ("", None) else 0.0
        except (TypeError, ValueError):
            value = 0.0

        if value <= 0:
            value = float(self.config.get("default_cfg", 7.0))

        if model_index in self.EDIT_MODEL_INDEXES:
            return value

        return max(1.0, min(10.0, value))

    def _normalize_model_index(self, model_index: str | int | None) -> int:
        try:
            value = int(model_index) if model_index not in ("", None) else -1
        except (TypeError, ValueError):
            value = -1

        if value < 0:
            value = int(self.config.get("default_model_index", 10))
        return value

    def _normalize_seed(self, seed: str | int | None) -> int:
        try:
            return int(seed) if seed not in ("", None) else -1
        except (TypeError, ValueError):
            return -1

    def _build_request_payload(
        self,
        prompt: str,
        negative_prompt: str,
        width: int,
        height: int,
        steps: int,
        cfg: float,
        model_index: int,
        seed: int,
        image_source: str = "",
    ) -> dict[str, Any]:
        if model_index in self.VIDEO_MODEL_INDEXES:
            raise RuntimeError("当前插件暂不支持视频模型，请改用图片模型")

        if model_index in self.EDIT_MODEL_INDEXES:
            if not image_source:
                raise RuntimeError("图片编辑模型必须提供 image_source 原图地址")
            return {
                "prompt": prompt,
                "model_index": model_index,
                "image_source": image_source,
            }

        return {
            "prompt": prompt,
            "negative_prompt": negative_prompt,
            "width": width,
            "height": height,
            "steps": steps,
            "cfg": cfg,
            "model_index": model_index,
            "seed": seed,
        }

    def _is_cloudflare_block_response(self, status_code: int, content_type: str, text: str) -> bool:
        lowered = (text or "").lower()
        ctype = (content_type or "").lower()
        return status_code == 403 and (
            "just a moment" in lowered
            or "cloudflare" in lowered
            or "text/html" in ctype
        )

    async def _call_generate_api_httpx(
        self,
        payload: dict[str, Any],
        headers: dict[str, str],
    ) -> dict[str, Any]:
        url = f"{self._base_url}/api/v1/generate_image"
        logger.info(f"[NovaSexDraw] HTTPX 请求梦羽接口: {url}")

        try:
            response = await self._client.post(url, headers=headers, json=payload)
        except httpx.TimeoutException as exc:
            raise RuntimeError("梦羽接口请求超时，请稍后重试") from exc

        content_type = response.headers.get("content-type", "")
        response_text = response.text

        if self._is_cloudflare_block_response(response.status_code, content_type, response_text):
            raise RuntimeError("CLOUDFLARE_BLOCKED")

        if response.status_code != 200:
            try:
                error_json = response.json()
                error_message = error_json.get("error") or error_json.get("message") or str(error_json)
            except Exception:
                error_message = response_text[:500]
            raise RuntimeError(f"梦羽接口请求失败 ({response.status_code}): {error_message}")

        try:
            return response.json()
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"梦羽接口响应解析失败: {exc}") from exc

    async def _call_generate_api_undici(
        self,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        bridge_path = self.plugin_dir / "undici_bridge.mjs"
        if not bridge_path.exists():
            raise RuntimeError("undici_bridge.mjs 不存在，无法使用 Node 桥接")

        command = [
            "node",
            str(bridge_path),
            "--url",
            f"{self._base_url}/api/v1/generate_image",
            "--method",
            "POST",
            "--api-key",
            self._api_key,
            "--data",
            json.dumps(payload, ensure_ascii=False),
        ]

        if self._proxy_url:
            command.extend(["--proxy", self._proxy_url])

        logger.info("[NovaSexDraw] 使用 undici 桥接请求梦羽接口")
        result = subprocess.run(
            command,
            cwd=str(self.plugin_dir),
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=int(self.config.get("timeout", 180)) + 10,
            check=False,
        )

        stdout = (result.stdout or "").strip()
        stderr = (result.stderr or "").strip()
        if result.returncode != 0:
            raise RuntimeError(f"undici 桥接执行失败: {stderr or stdout or '未知错误'}")

        try:
            bridge_result = json.loads(stdout)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"undici 桥接响应解析失败: {stdout[:500]}") from exc

        if "error" in bridge_result:
            raise RuntimeError(f"undici 桥接错误: {bridge_result.get('error')}")

        status_code = int(bridge_result.get("status", 0) or 0)
        headers = bridge_result.get("headers") or {}
        body = bridge_result.get("body")
        body_text = body if isinstance(body, str) else json.dumps(body, ensure_ascii=False)

        if self._is_cloudflare_block_response(status_code, headers.get("content-type", ""), body_text):
            raise RuntimeError("undici 桥接后仍被 Cloudflare 拦截")

        if status_code != 200:
            if isinstance(body, dict):
                error_message = body.get("error") or body.get("message") or json.dumps(body, ensure_ascii=False)
            else:
                error_message = body_text[:500]
            raise RuntimeError(f"梦羽接口请求失败 ({status_code}): {error_message}")

        if not isinstance(body, dict):
            raise RuntimeError("undici 桥接返回的 body 不是 JSON 对象")

        return body

    async def _call_generate_api(
        self,
        prompt: str,
        negative_prompt: str,
        width: int,
        height: int,
        steps: int,
        cfg: float,
        model_index: int,
        seed: int,
        image_source: str = "",
    ) -> dict[str, Any]:
        if not self._api_key:
            raise RuntimeError("未配置 api_key，无法调用梦羽绘图接口")

        payload = self._build_request_payload(
            prompt=prompt,
            negative_prompt=negative_prompt,
            width=width,
            height=height,
            steps=steps,
            cfg=cfg,
            model_index=model_index,
            seed=seed,
            image_source=image_source,
        )

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        logger.debug(f"[NovaSexDraw] 请求体: {json.dumps(payload, ensure_ascii=False)}")

        try:
            result = await self._call_generate_api_undici(payload)
        except RuntimeError as exc:
            if self._enable_undici_fallback:
                logger.warning(f"[NovaSexDraw] Node 桥接失败，尝试 Python 兼容路径: {exc}")
                result = await self._call_generate_api_httpx(payload, headers)
            else:
                raise

        if not result.get("success"):
            raise RuntimeError(result.get("error") or result.get("message") or "梦羽接口返回失败")

        data = result.get("data") or {}
        image_url = data.get("image_url")
        if not image_url:
            raise RuntimeError("接口返回成功，但缺少 image_url")

        return {
            "image_url": image_url,
            "image_id": data.get("image_id", ""),
            "model_name": data.get("model_name") or self.MODEL_CHOICES.get(model_index, f"模型{model_index}"),
            "points_used": data.get("points_used", "?"),
            "remaining_points": data.get("remaining_points", "?"),
            "raw_response": result,
        }

    async def _extract_image_url_from_event(self, event: AstrMessageEvent) -> str:
        """从消息或回复链中提取第一张图片 URL"""
        try:
            for seg in event.message_obj.message:
                if isinstance(seg, Reply) and getattr(seg, "chain", None):
                    for reply_seg in seg.chain:
                        if isinstance(reply_seg, AstrImageComponent) and getattr(reply_seg, "url", ""):
                            return reply_seg.url
            for seg in event.message_obj.message:
                if isinstance(seg, AstrImageComponent) and getattr(seg, "url", ""):
                    return seg.url
        except Exception as e:
            logger.warning(f"[NovaSexDraw] 提取消息图片失败: {e}")
        return ""

    async def _download_image(self, image_url: str) -> Path:
        logger.info(f"[NovaSexDraw] 下载图片: {image_url[:120]}...")
        response = await self._client.get(image_url)

        if response.status_code != 200:
            raise RuntimeError(f"下载图片失败: HTTP {response.status_code}")

        content_type = response.headers.get("content-type", "image/jpeg")
        ext = content_type.split("/")[-1].split(";")[0].lower()
        if ext not in ("png", "jpg", "jpeg", "webp", "gif"):
            ext = "jpg"

        filename = f"{uuid.uuid4()}.{ext}"
        filepath = self.image_dir / filename
        filepath.write_bytes(response.content)
        logger.info(f"[NovaSexDraw] 图片已保存: {filepath}")
        return filepath

    async def _run_draw_request(
        self,
        event: AstrMessageEvent,
        prompt: str,
        *,
        negative_prompt: str = "",
        resolution: str = "",
        steps: str | int = "",
        cfg: str | float = "",
        model_index: str | int | None = "",
        seed: str | int = "",
        image_source: str = "",
        force_edit: bool = False,
        auto_send: bool = True,
    ) -> dict[str, Any]:
        if not prompt:
            raise RuntimeError("请提供 prompt 提示词")

        actual_model = self._normalize_model_index(model_index)
        if force_edit and actual_model not in self.EDIT_MODEL_INDEXES:
            actual_model = 19

        width, height = self._parse_resolution(resolution or None)
        actual_steps = self._normalize_steps(steps, actual_model)
        actual_cfg = self._normalize_cfg(cfg, actual_model)
        actual_seed = self._normalize_seed(seed)
        actual_neg = negative_prompt or self.config.get("default_negative_prompt", "")
        actual_image_source = image_source.strip()

        if actual_model in self.EDIT_MODEL_INDEXES and not actual_image_source:
            actual_image_source = await self._extract_image_url_from_event(event)

        result = await self._call_generate_api(
            prompt=prompt,
            negative_prompt=actual_neg,
            width=width,
            height=height,
            steps=actual_steps,
            cfg=actual_cfg,
            model_index=actual_model,
            seed=actual_seed,
            image_source=actual_image_source,
        )

        image_path = await self._download_image(result["image_url"])
        if auto_send:
            await event.send(event.chain_result([Image.fromFileSystem(str(image_path))]))

        result["image_path"] = str(image_path)
        result["width"] = width
        result["height"] = height
        result["actual_model"] = actual_model
        result["actual_image_source"] = actual_image_source
        return result

    @filter.llm_tool()
    async def nova_draw_image(
        self,
        event: AstrMessageEvent,
        prompt: str,
        resolution: str = "",
        negative_prompt: str = "",
        model_index: str = "",
        steps: str = "",
        cfg: str = "",
        seed: str = "",
    ):
        """梦羽 ComfyUI 文生图工具。

        只有当用户明确表达以下意图之一时，才优先调用本工具：
        - 明确说“用comfyui生图”“用comfyui画图”
        - 明确要求“画个色图”“来张色图”“涩图”
        - 明确要求使用本插件这一类偏 ComfyUI / 梦羽 的画图能力

        不应触发本工具的场景：
        - 用户只是泛泛说“画图”“生成图片”，但没有提到 comfyui、色图、涩图等强信号
        - 用户其实是在要求修改一张已有图片，此时应改用 nova_edit_image

        参数建议：
        - resolution 支持 portrait、landscape、square、1024 或 WxH，如 1216x832、832x1216
        - 普通文生图默认模型为 10（wai16）
        - 如果用户没提负面词，可留空，插件会自动使用默认 negative prompt
        - 调用成功后图片会自动发送给用户
        """
        user_id = event.get_sender_id()
        request_id = f"sexdraw_{user_id}"

        if self._check_debounce(user_id):
            interval = self.config.get("debounce_interval", 15)
            return f"请等待 {interval} 秒后再试"

        if request_id in self._processing_users:
            return "您有正在进行的生图任务，请稍候..."

        self._processing_users.add(request_id)

        try:
            result = await self._run_draw_request(
                event=event,
                prompt=prompt,
                negative_prompt=negative_prompt,
                resolution=resolution,
                steps=steps,
                cfg=cfg,
                model_index=model_index or "10",
                seed=seed,
            )
            return (
                f"图片生成完成！\n"
                f"- 模型: {result.get('model_name', '未知')}\n"
                f"- 尺寸: {result.get('width')}x{result.get('height')}\n"
                f"- 消耗/剩余积分: {result.get('points_used', '?')}/{result.get('remaining_points', '?')}"
            )
        except Exception as e:
            logger.error(f"[NovaSexDraw] 主动文生图失败: {e}")
            return f"生成图片失败: {str(e)}"
        finally:
            self._processing_users.discard(request_id)

    @filter.llm_tool()
    async def nova_edit_image(
        self,
        event: AstrMessageEvent,
        prompt: str,
        use_message_images: bool = True,
        model_index: str = "19",
        image_source: str = "",
    ):
        """梦羽 ComfyUI 图片编辑工具。

        当用户发送了图片或引用了图片，并且明确表达以下意图之一时，优先调用本工具：
        - “用comfyui改一下这张图”
        - “用comfyui把这张图改成...”
        - “把这张色图改一下”“把这张图P一下”“把这张图修一下”
        - 明确要求基于当前图片做修改、换发色、换衣服、换背景、修细节、重绘局部

        获取原图方式：
        - use_message_images=true（默认）：自动从当前消息或引用消息中提取图片
        - image_source：如果用户明确给了可访问图片 URL，也可以直接传

        重要提示：
        - 只要是“用 comfyui 改这张图”这一类表达，默认优先使用 2511，也就是 model_index=19
        - QQ 临时图片、回复里的图片，优先依靠 use_message_images=true 自动提取
        - 18/19 都属于纯编辑模型，但默认首选 19
        - 调用成功后图片会自动发送给用户

        Args:
            prompt(string): 修改指令，例如“把头发改成黑发”“背景改成海边黄昏”“换成白色连衣裙”
            use_message_images(boolean): 是否自动提取当前消息或引用消息中的图片，默认 true
            model_index(string): 编辑模型索引，默认 19，可选 18 或 19
            image_source(string): 可直接访问的原图 URL。若为空则尝试自动从消息图片中提取
        """
        user_id = event.get_sender_id()
        request_id = f"sexdraw_{user_id}"

        if self._check_debounce(user_id):
            interval = self.config.get("debounce_interval", 15)
            return f"请等待 {interval} 秒后再试"

        if request_id in self._processing_users:
            return "您有正在进行的改图任务，请稍候..."

        self._processing_users.add(request_id)

        try:
            actual_image_source = image_source.strip()
            if use_message_images and not actual_image_source:
                actual_image_source = await self._extract_image_url_from_event(event)

            if not actual_image_source:
                return "请先发送图片，或回复一张图片后再告诉我怎么修改。"

            result = await self._run_draw_request(
                event=event,
                prompt=prompt,
                model_index=model_index or "19",
                image_source=actual_image_source,
                force_edit=True,
            )
            return (
                f"图片编辑完成！\n"
                f"- 模型: {result.get('model_name', '未知')}\n"
                f"- 尺寸: {result.get('width')}x{result.get('height')}\n"
                f"- 消耗/剩余积分: {result.get('points_used', '?')}/{result.get('remaining_points', '?')}"
            )
        except Exception as e:
            logger.error(f"[NovaSexDraw] 主动图编辑失败: {e}")
            return f"编辑图片失败: {str(e)}"
        finally:
            self._processing_users.discard(request_id)

    @filter.llm_tool()
    async def draw_seximage(
        self,
        event: AstrMessageEvent,
        prompt: str,
        negative_prompt: str = "",
        resolution: str = "",
        steps: str = "",
        cfg: str = "",
        model_index: str = "",
        seed: str = "",
        image_source: str = "",
    ):
        """兼容旧版的梦羽绘图工具。

        - 文生图时可直接调用，但更推荐优先使用 nova_draw_image
        - 图像编辑时如有原图可传 image_source，但更推荐优先使用 nova_edit_image
        - 如果语义是“用comfyui改一下这张图”，默认应走编辑模型 19
        - resolution 支持 portrait、landscape、square、1024 或 WxH
        """
        user_id = event.get_sender_id()
        request_id = f"sexdraw_{user_id}"

        if self._check_debounce(user_id):
            interval = self.config.get("debounce_interval", 15)
            return f"请等待 {interval} 秒后再试"

        if request_id in self._processing_users:
            return "您有正在进行的生图任务，请稍候..."

        self._processing_users.add(request_id)

        try:
            result = await self._run_draw_request(
                event=event,
                prompt=prompt,
                negative_prompt=negative_prompt,
                resolution=resolution,
                steps=steps,
                cfg=cfg,
                model_index=model_index,
                seed=seed,
                image_source=image_source,
            )
            mode_text = (
                "图片编辑"
                if result.get("actual_model") in self.EDIT_MODEL_INDEXES
                else "图片生成"
            )
            return (
                f"{mode_text}完成！\n"
                f"- 模型: {result.get('model_name', '未知')}\n"
                f"- 尺寸: {result.get('width')}x{result.get('height')}\n"
                f"- 消耗/剩余积分: {result.get('points_used', '?')}/{result.get('remaining_points', '?')}"
            )
        except Exception as e:
            logger.error(f"[NovaSexDraw] 生图失败: {e}")
            return f"生成图片失败: {str(e)}"
        finally:
            self._processing_users.discard(request_id)

    @filter.command("sexdraw", alias={"色图", "涩图", "画图"})
    async def sexdraw_command(self, event: AstrMessageEvent, prompt: str = ""):
        """生成图片指令

        用法示例：
        - /sexdraw 1girl, silver hair, red eyes portrait
        - /sexdraw 1girl, city night 1216x832
        - /sexdraw 把这张图头发改成黑发 --model=19
        - /sexdraw 把这张图背景改成海边 --model=18 --image_source=https://example.com/a.png

        说明：
        - 直接在提示词最后写分辨率即可，如 portrait、landscape、square、1024、1216x832
        - 如果消息里带图，且模型是 18/19，插件会自动提取该图 URL 作为 image_source
        """
        arg = event.message_str.partition(" ")[2].strip()
        if not arg:
            yield event.plain_result(
                "请提供提示词！\n"
                "用法: /sexdraw <提示词> [分辨率]\n"
                "示例1: /sexdraw 1girl, cute, silver hair portrait\n"
                "示例2: /sexdraw make hair black --model=18 --image_source=https://example.com/a.jpg"
            )
            return

        resolution = ""
        image_source = ""
        explicit_model: int | None = None

        model_match = re.search(r"\bmodel\s*(\d{1,2})\b", arg, re.IGNORECASE)
        if model_match:
            explicit_model = int(model_match.group(1))
            arg = re.sub(r"\bmodel\s*\d{1,2}\b", "", arg, flags=re.IGNORECASE).strip()

        image_source_match = re.search(r"--image_source=(\S+)", arg, re.IGNORECASE)
        if image_source_match:
            image_source = image_source_match.group(1).strip()
            arg = re.sub(r"\s*--image_source=\S+", "", arg, flags=re.IGNORECASE).strip()

        parts = arg.rsplit(maxsplit=1)
        if len(parts) == 2:
            possible_prompt, suffix = parts
            suffix_lower = suffix.lower()
            if suffix_lower in self.RESOLUTION_PRESETS or re.match(r"\d+\s*[x×*X-]\s*\d+", suffix_lower):
                prompt = possible_prompt
                resolution = suffix_lower
            else:
                prompt = arg
        else:
            prompt = arg

        user_id = event.get_sender_id()
        request_id = f"sexdraw_{user_id}"

        if self._check_debounce(user_id):
            interval = self.config.get("debounce_interval", 15)
            yield event.plain_result(f"请等待 {interval} 秒后再试")
            return

        if request_id in self._processing_users:
            yield event.plain_result("您有正在进行的生图任务，请稍候...")
            return

        self._processing_users.add(request_id)

        try:
            actual_model = explicit_model if explicit_model is not None else self._normalize_model_index(None)
            width, height = self._parse_resolution(resolution or None)
            if actual_model in self.EDIT_MODEL_INDEXES and not image_source:
                image_source = await self._extract_image_url_from_event(event)

            result = await self._call_generate_api(
                prompt=prompt,
                negative_prompt=self.config.get("default_negative_prompt", ""),
                width=width,
                height=height,
                steps=self._normalize_steps(None, actual_model),
                cfg=self._normalize_cfg(None, actual_model),
                model_index=actual_model,
                seed=-1,
                image_source=image_source,
            )

            image_path = await self._download_image(result["image_url"])
            yield event.chain_result([Image.fromFileSystem(str(image_path))])
            yield event.plain_result(
                f"生成完成：{result.get('model_name', '未知')} | {width}x{height} | "
                f"消耗/剩余积分 {result.get('points_used', '?')}/{result.get('remaining_points', '?')}"
            )

        except Exception as e:
            logger.error(f"[NovaSexDraw] 指令生图失败: {e}")
            yield event.plain_result(f"生成图片失败: {str(e)}")

        finally:
            self._processing_users.discard(request_id)