# 文件名：stripchat.py by https://t.me/stripol
# 2026年8月25日更新 (适配 Streamlink 8 - 修正直链及全链路 pkey 白名单兜底)
from __future__ import annotations
import logging
import re
import base64
import random
import string
import hashlib
import functools
from streamlink.plugin import Plugin, pluginmatcher
from streamlink.stream.hls import HLSStream, HLSStreamWorker, HLSStreamReader
from streamlink.exceptions import StreamError

log = logging.getLogger(__name__)

# ====================== 统一 KEY 映射 ======================
KEY_MAP = {
  "Zokee2OhPh9kugh4": "Quean4cai9boJa5a",
  "Zeechoej4aleeshi": "ubahjae7goPoodi6",
  "Ook7quaiNgiyuhai": "EQueeGh2kaewa3ch",
  "Fq6m2TO2ZeBkRPm9": "xb6di1NF9EFXHUwb",
  "GrRncsoByZmsiT6L": "NigHYyOD9l4rvAEb",
  "1Dzcc6OjP73LKbtI": "Y64UVwX5RrIWnOLp",
  "N2oLovTIXb0o28Uj": "ABE7Sj8jh3oPM2ae",
  "NTK9aqcLmNFMWrpQ": "tOcYOap4Ty1l9Jzb",
  "7uUnbD0jMCB9GH32": "lzCQ6QBTnLpB0zMF",
  "Ohi7eTRBpkAuML0l": "kExe29N2sLFrHGqu",
  "OLzu7QlySkG2fVRn": "CsovScFH9VirSJ4Z"
}
DEFAULT_PKEY = "Zokee2OhPh9kugh4"
DEFAULT_KEY = KEY_MAP[DEFAULT_PKEY]

# V2 专属兜底配置
FALLBACK_PKEY_V2 = "Fq6m2TO2ZeBkRPm9"

# ====================== 解密核心 (带详细日志) ======================
class MouflonDecryptor:
    @staticmethod
    def get_pkey(text: str) -> str:
        m = re.search(r"#EXT-X-MOUFLON:PSCH:(?:v1|v2):([^\s,]+)", text)
        pkey = m.group(1) if m else DEFAULT_PKEY
        return pkey if pkey in KEY_MAP else DEFAULT_PKEY

    @staticmethod
    def decode_v1(enc: str, key: str) -> str:
        enc += "=" * ((4 - len(enc) % 4) % 4)
        data = base64.b64decode(enc)
        kh = hashlib.sha256(key.encode()).digest()
        decrypted = bytes(b ^ kh[i % 32] for i, b in enumerate(data)).decode("utf-8", errors="ignore")
        log.debug(f"[v1] 解密内容: {enc[:20]}... -> {decrypted}")
        return decrypted

class MouflonV2Decryptor:
    @classmethod
    @functools.lru_cache(maxsize=256)
    def decode(cls, encrypted: str, key_v2: str) -> str:
        try:
            # v2 核心逻辑：翻转 -> Base64 -> XOR
            reversed_token = encrypted[::-1]
            reversed_token += "=" * ((4 - len(reversed_token) % 4) % 4)
            data = base64.b64decode(reversed_token)
            key_hash = hashlib.sha256(key_v2.encode("utf-8")).digest()
            decrypted_bytes = bytearray(b ^ key_hash[i % 32] for i, b in enumerate(data))
            decrypted = decrypted_bytes.decode("utf-8", errors="replace")
            log.debug(f"[v2] Token解密: {encrypted} -> {decrypted}")
            return decrypted
        except Exception as e:
            log.error(f"[v2] 解密核心失败: {e}")
            return encrypted

# ====================== 流处理类 (v1) ======================
class DecryptWorker(HLSStreamWorker):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.current_pkey = DEFAULT_PKEY
        self.current_key = DEFAULT_KEY
        log.info("[plugin] 已启动 v1/Mouflon 解密器")

    def _fetch_playlist(self):
        res = self.session.http.get(self.stream.url, exception=StreamError, **self.reader.request_params)
        res.encoding = "utf-8"
        text = res.text
        
        # 动态更新 Key
        new_pkey = MouflonDecryptor.get_pkey(text)
        if new_pkey != self.current_pkey:
            self.current_pkey = new_pkey
            self.current_key = KEY_MAP.get(new_pkey, DEFAULT_KEY)
            log.info(f"[v1] 密钥切换为: {new_pkey}")

        lines = text.splitlines()
        new_lines = []
        i = 0
        while i < len(lines):
            if lines[i].startswith("#EXT-X-MOUFLON:FILE:"):
                enc = lines[i].split(":", 2)[2]
                real = MouflonDecryptor.decode_v1(enc, self.current_key)
                new_lines.append("#DECRYPTED")
                if i + 1 < len(lines):
                    new_lines.append(real)
                i += 2
                continue
            new_lines.append(lines[i])
            i += 1
        res._content = "\n".join(new_lines).encode("utf-8")
        return res

class DecryptHLSStreamReader(HLSStreamReader):
    __worker__ = DecryptWorker

class DecryptHLSStream(HLSStream):
    __reader__ = DecryptHLSStreamReader

# ====================== 流处理类 (v2) ======================
class DecryptWorkerV2(HLSStreamWorker):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.current_key_v2 = KEY_MAP[FALLBACK_PKEY_V2]
        log.info("[plugin] 已启动 v2/Mouflon 解密器")

    def _fetch_playlist(self):
        res = self.session.http.get(self.stream.url, exception=StreamError, **self.reader.request_params)
        res.encoding = "utf-8"
        text = res.text

        # 1. 优先从 M3U8 文本中校验 pkey
        extracted_pkey = None
        m = re.search(r"#EXT-X-MOUFLON:PSCH:v2:([^\s,]+)", text)
        if m:
            extracted_pkey = m.group(1)
        else:
            # 2. 从 URL 参数中提取 pkey
            url_match = re.search(r"[?&]pkey=([^&]+)", self.stream.url)
            if url_match:
                extracted_pkey = url_match.group(1)

        # 3. 统一做白名单校验：不在 KEY_MAP 中则强行替换为兜底 KEY
        if extracted_pkey and extracted_pkey in KEY_MAP:
            active_pkey = extracted_pkey
        else:
            if extracted_pkey:
                log.warning(f"[v2] 检测到未知 pkey '{extracted_pkey}'，触发强制兜底 -> {FALLBACK_PKEY_V2}")
            else:
                log.info(f"[v2] 未检测到 pkey，使用默认兜底 -> {FALLBACK_PKEY_V2}")
            active_pkey = FALLBACK_PKEY_V2

        self.current_key_v2 = KEY_MAP[active_pkey]

        lines = text.splitlines()
        new_lines = []
        i = 0
        while i < len(lines):
            line = lines[i]
            if line.startswith("#EXT-X-MOUFLON:URI:"):
                mouflon_uri = line.split(":", 2)[2]
                # 增强正则提取 token
                match = re.search(r'_([A-Za-z0-9+/=]{10,})', mouflon_uri)
                if match:
                    token = match.group(1)
                    # 使用确定的 active_pkey 对应的 key 进行解密
                    decrypted = MouflonV2Decryptor.decode(token, self.current_key_v2)
                    real_uri = mouflon_uri.replace(token, decrypted)
                    log.debug(f"[v2] 最终 URI: {real_uri}")
                    new_lines.append(real_uri)
                    i += 2 
                    continue
            new_lines.append(line)
            i += 1
        res._content = "\n".join(new_lines).encode("utf-8")
        return res

class DecryptHLSStreamReaderV2(HLSStreamReader):
    __worker__ = DecryptWorkerV2

class DecryptHLSStreamV2(HLSStream):
    __reader__ = DecryptHLSStreamReaderV2

# ====================== 插件主体 ======================
@pluginmatcher(re.compile(r"https?://(?:[\w-]+\.)?(?:stripchat\.com|stripol\.com)/([^/?#]+)", re.I))
@pluginmatcher(re.compile(r"https?://[^\?]*\.doppiocdn\.(?:com|org|live|net|media)/.*\.m3u8", re.I))
class Stripchat(Plugin):
    def _sanitize_url_pkey(self, url: str) -> str:
        """辅助函数：检查并清理 URL 中的 pkey 参数，不在白名单就替换为兜底 pkey"""
        m = re.search(r"([?&]pkey=)([^&]+)", url)
        if m:
            pkey_val = m.group(2)
            if pkey_val not in KEY_MAP:
                log.warning(f"[plugin] 直链 URL 包含未知 pkey: {pkey_val}, 正在重写为: {FALLBACK_PKEY_V2}")
                url = url.replace(f"pkey={pkey_val}", f"pkey={FALLBACK_PKEY_V2}")
        return url

    def _get_streams(self):
        # 1. 直链模式
        if "doppiocdn" in self.url:
            log.info("[plugin] 正在检测直链加密版本...")
            
            # 清理 URL 中未知的 pkey 参数
            target_url = self._sanitize_url_pkey(self.url)

            text = self.session.http.get(target_url).text
            if "#EXT-X-STREAM-INF" in text:
                log.info("[plugin] 检测到直链为 Master Playlist，正在探测子码率...")
                streams = HLSStream.parse_variant_playlist(self.session, target_url)
                final = {}
                for name, s in streams.items():
                    sub_url = self._sanitize_url_pkey(s.url)
                    txt = self.session.http.get(sub_url).text
                    if "#EXT-X-MOUFLON:URI:" in txt:
                        final[name] = DecryptHLSStreamV2(self.session, sub_url)
                    else:
                        final[name] = DecryptHLSStream(self.session, sub_url)
                return final

            if "#EXT-X-MOUFLON:URI:" in text:
                return {"live": DecryptHLSStreamV2(self.session, target_url)}
            return {"live": DecryptHLSStream(self.session, target_url)}

        # 2. 直播间模式
        username = self.match.group(1)
        log.info(f"[plugin] 正在查询主播: {username}")
        base_url="https://zh.stripchat.com"
        headers = {
            "Referer": self.url,
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "x-device-info": '{"t":"webMobile","v":"1.0","ui":24631221}'
        }
        uniq = ''.join(random.choices(string.ascii_lowercase + string.digits, k=16))
        # 先通过用户名获取 ID
        user_id_response = self.session.http.get(f"{base_url}/api/front/users/user-ids/{username}?{uniq}", headers=headers, timeout=15)
        if user_id_response.status_code != 200:
            logger.error(f"获取主播ID失败: {anchor_name} 响应码 {user_id_response.status_code}")
            return {"status": "error", "msg": f"获取主播ID失败 HTTP {user_id_response.status_code}"}
    
        user_id_data = user_id_response.json()
        model_id = user_id_data.get("id")
        if not model_id:
            logger.error(f"未获取到主播ID: {anchor_name}, 响应: {user_id_data}")
            return {"status": "error", "msg": f"未获取到主播ID: {anchor_name}"}
    
        # 使用 ID 获取主播信息
        
        api = f"{base_url}/api/front/v2/models/{model_id}/cam?timezoneOffset=0&triggerRequest=loadCam&uniq={uniq}"
        
        #api = f"{base_url}/api/front/v2/models/username/{username}/cam"
        
        try:
            res = self.session.http.get(api, headers=headers, timeout=15)
            data = res.json()
            cam = data.get("cam", {})
            user_data = data.get("user", {})
            uid = user_data.get("user", {}).get("id") or user_data.get("id")
            
            if not uid or cam.get("show") or not cam.get("isCamAvailable", False):
                log.info(f"主播 {username} 当前不在线或不可观测")
                return {}

            log.info(f"[plugin] 主播在线 (UID: {uid})，准备探测变体流...")
            
            auto = f"https://edge-hls.doppiocdn.com/hls/{uid}/master/{uid}_auto.m3u8"
            text = self.session.http.get(auto).text
            
            m = re.search(r"#EXT-X-MOUFLON:PSCH:v2:([^\s]+)", text)
            pkey = m.group(1) if m else DEFAULT_PKEY
            
            if pkey not in KEY_MAP:
                log.warning(f"[plugin] 探测到未知的 pkey: {pkey}, 已强制兜底切换至: {FALLBACK_PKEY_V2}")
                pkey = FALLBACK_PKEY_V2
            
            master = f"{auto}?psch=v2&pkey={pkey}&_HLS_msn=1&_HLS_part=0"
            streams = HLSStream.parse_variant_playlist(self.session, master)
            
            final = {}
            for name, s in streams.items():
                txt = self.session.http.get(s.url).text
                if "#EXT-X-MOUFLON:URI:" in txt:
                    log.info(f"[plugin] 码率 {name} 匹配为 v2 解密")
                    final[name] = DecryptHLSStreamV2(self.session, s.url)
                else:
                    log.info(f"[plugin] 码率 {name} 匹配为 v1 解密")
                    final[name] = DecryptHLSStream(self.session, s.url)
            return final
            
        except Exception as e:
            log.error(f"[plugin] 解析过程异常: {e}")

__plugin__ = Stripchat
