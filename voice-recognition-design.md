# 语音识别功能 — 完整设计方案

## 1. 现状分析

当前系统对消息的处理链路：

```
WCDB 数据库 → wcdb_api.dll (ctypes) → _standardize() → router → AI 总结
```

### 消息类型码 (localType)

| localType | 含义 | 当前处理 |
|-----------|------|----------|
| 1 | 文字 | 读真实内容 |
| 3 | 图片 | 替换为 `[图片]` |
| 34 | 语音 | 替换为 `[语音]` |
| 43 | 视频 | 替换为 `[视频]` |
| 47 | 表情 | 替换为 `[表情]` |
| 49 | 链接/文件 | 替换为 `[消息]` |

### 关键瓶颈

1. **`src/wechat/wcdb_backend.py:435-437`** — `_standardize()` 方法取 `message_content`，但语音消息的 `message_content` 通常是空或 XML，没有文件路径信息。

2. **`src/wechat/mac_weflow_client.py:388-389`** — 当 `localType != 1` 时，`content` 直接替换为占位符 label，原始数据被丢弃。

3. **`src/wechat/mac_weflow_client.py:765-772`** — `_message_type_label()` 函数，非文字类型一律返回占位符。

4. **`src/summarize/prompts.py:199-213`** — 格式化消息时只对 `msg_type==1` 做 XML 转义，非文字类型依赖 `content` 字段已有占位符。

### 语音消息在 WCDB 中的字段

WCDB 消息原始字段（来自 `_standardize` line 433 注释）：

```
sender_username, message_content, local_type, create_time, local_id, msg_svr_id
```

语音文件的定位依赖 `msg_svr_id`（server message ID），这是 WeChat 文件系统存储的目录名。

---

## 2. 语音文件在哪里

微信 PC 版的语音消息存储在文件系统中（不在 WCDB 数据库内），路径规律：

```
Windows: {wechat_data_dir}/{wxid_xxx}/msg/voice/{msg_svr_id}/
                                                          ├── {msg_svr_id}.silk
                                                          └── {msg_svr_id}.amr

macOS:   ~/Library/Containers/com.tencent.xinWeChat/.../msg/voice/{msg_svr_id}/
```

文件格式：
- **Windows**: `.amr` 或 `.silk`（SILK v3 编码，Skype 开发的音频编解码器，微信自定义封装）
- **macOS**: `.silk` 或 `.aud`

备选路径（旧版微信或清理后残留）：
```
{wechat_data_dir}/{wxid_xxx}/msg/attach/{msg_svr_id}/
```

---

## 3. 整体方案设计

```
┌─────────────────────────────────────────────────────────────────┐
│                    语音消息处理流程                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ① WCDB 轮询到 localType=34 的消息                              │
│       │                                                        │
│       ▼                                                        │
│  ② 根据 msg_svr_id / local_id 定位 .silk/.amr 文件               │
│       │                                                        │
│       ▼                                                        │
│  ③ SILK/AMR 解码 → PCM/WAV (pilk 纯 Python 库)                 │
│       │                                                        │
│       ▼                                                        │
│  ④ 调用 ASR 服务转文字（本地 or 云端）                           │
│       │                                                        │
│       ▼                                                        │
│  ⑤ 将识别文字替换 content（不再传 "[语音]"）                     │
│       │                                                        │
│       ▼                                                        │
│  ⑥ 标准化消息 → router → AI 总结/聊天（与文字消息相同路径）       │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 4. 新增模块架构

```
src/
├── voice/                          # 新增：语音识别模块
│   ├── __init__.py
│   ├── decoder.py                  # SILK/AMR 解码器
│   ├── asr.py                      # ASR 服务调用（抽象基类 + 多实现）
│   ├── file_locator.py             # 语音文件定位器
│   └── pipeline.py                 # 语音→文字的完整流水线
│
├── wechat/
│   ├── wcdb_backend.py             # 修改：_standardize() 中插入语音识别
│   └── mac_weflow_client.py        # 修改：同上
│
├── config.py                       # 新增 voice 相关配置项
```

---

## 5. 各模块详细设计

### 5.1 `src/voice/file_locator.py` — 语音文件定位

```python
"""根据消息元信息定位 WeChat 语音文件。

WeChat 语音文件存储路径规律：
  Windows: {db_path}/../msg/voice/{msg_svr_id}/
  macOS:   ~/Library/Containers/com.tencent.xinWeChat/.../voice/{msg_svr_id}/

目录下通常包含:
  - {msg_svr_id}.silk
  - {msg_svr_id}.amr
"""

class VoiceFileLocator:
    def __init__(self, wechat_data_dir: str, wxid: str):
        self._data_dir = Path(wechat_data_dir)
        self._wxid = wxid

    def find_voice_file(self, msg: dict) -> Path | None:
        """给定一条 WCDB 原始消息，返回语音文件路径。

        msg 包含: msgSvrId / server_id / msg_svr_id / local_id

        查找顺序:
          1. {data_dir}/{wxid}/msg/voice/{msg_svr_id}/*.silk
          2. {data_dir}/{wxid}/msg/voice/{msg_svr_id}/*.amr
          3. {data_dir}/{wxid}/msg/attach/{msg_svr_id}/*.silk
          4. {data_dir}/{wxid}/msg/attach/{msg_svr_id}/*.amr

        Returns: .silk 或 .amr 文件的绝对路径，找不到返回 None
        """
```

### 5.2 `src/voice/decoder.py` — SILK/AMR 解码

#### 格式分析

- **SILK v3**: Skype 开发的音频编解码器，微信 PC + 手机端使用。微信在 SILK 数据外层加了一层自定义封装（加了一些 header bytes），需要先剥离微信头再解码。
- **AMR**: 3GPP 标准格式，部分老版本微信使用，ffmpeg 可以直接处理。

#### 解码方案对比

| 方案 | 优点 | 缺点 |
|-----|------|-----|
| **silk-python (pysilk)** | CFFI/Cython 实现，解码功能完善，已实际验证可用 | 需 C 扩展编译（但有预编译包） |
| ffmpeg (子进程) | 支持 AMR 格式 | SILK 解码需自定义编译 |

**选用: silk-python (pysilk) + ffmpeg AMR fallback**

- `pip install silk-python` 安装 pysilk，提供 `decode()` API
- SILK 解码: `.silk → strip WeChat header → pysilk.decode() → PCM → 临时 .wav`
- AMR 解码: `.amr → ffmpeg → .wav`（fallback）

#### 解码流程伪代码

```python
class SilkDecoder:
    """SILK v3 音频解码器，基于 pilk 库。"""

    def decode(self, silk_path: Path) -> Path:
        """将 .silk 文件解码为临时 .wav 文件。

        Args:
            silk_path: .silk 文件的绝对路径

        Returns:
            解码后的 .wav 临时文件路径

        Raises:
            DecodeError: 解码失败
        """
        # 1. 读取 .silk 文件
        # 2. 剥离微信自定义头部（如有）
        # 3. pilk.decode() → PCM bytes (16kHz, mono, 16bit)
        # 4. 写入 WAV 头 + PCM data → 临时文件
        # 5. 返回临时文件路径
```

### 5.3 `src/voice/asr.py` — 语音识别服务

#### 抽象基类

```python
from dataclasses import dataclass

@dataclass
class TranscribeResult:
    text: str           # 识别出的文字
    confidence: float   # 置信度 0.0 ~ 1.0
    duration_sec: float # 音频时长（秒）

class AbstractASR(ABC):
    """语音识别抽象基类"""

    @abstractmethod
    def transcribe(self, audio_path: Path, language: str = "zh") -> TranscribeResult:
        """将音频文件转文字。"""
        ...
```

#### 两种 ASR 实现（同时实现，用户自主选择）

| 后端 | 类型 | 费用 | 离线可用 | 内存 | 准确率 |
|------|------|------|----------|------|--------|
| **LocalWhisperASR**（默认）| 本地 faster-whisper | 免费 | 是 | ~1GB（small）| 中-高 |
| OpenAIWhisperASR | 云端 API | $0.006/分钟 | 否 | 几乎为零 | 高 |

**两种同时实现**，默认用本地（省成本），用户可通过 `.env` 切换到云端。

```python
class OpenAiWhisperASR(AbstractASR):
    """OpenAI Whisper API（云端）。

    需要 VOICE_OPENAI_API_KEY（不填则复用 OPENAI_API_KEY）。
    模型: whisper-1
    费用: $0.006/分钟（无免费额度）
    """
    def transcribe(self, audio_path: Path, language: str = "zh") -> TranscribeResult:
        # POST https://api.openai.com/v1/audio/transcriptions
        # multipart/form-data: file, model=whisper-1, language=zh
        ...

class LocalWhisperASR(AbstractASR):
    """本地 Whisper 模型（faster-whisper），默认后端。

    首次运行自动下载模型（small 约 500MB）到 data/models/，
    之后完全离线，零费用。模型常驻内存避免重复加载。
    """
    def __init__(self, model_size: str = "small"):
        # model_size: tiny / base / small / medium / large
        # small 是中文最优性价比 — ~1GB 内存，3秒语音约 1-3s 识别（CPU）
        ...

def create_asr(config) -> AbstractASR:
    """工厂函数，根据 VOICE_ASR_BACKEND 配置选择 ASR 实现。"""
    backend = config.voice_asr_backend  # "local_whisper" | "openai_whisper"
    ...
```

### 5.4 `src/voice/pipeline.py` — 语音处理流水线

```python
"""语音→文字的完整流水线，对调用方就是一个函数。"""

class VoicePipeline:
    """语音识别流水线，封装 file_locator + decoder + asr + cache。

    用法:
        pipeline = VoicePipeline(config)
        text = pipeline.process(voice_msg)
        # text = "今天晚上吃什么"  ← 原来返回 "[语音]"
    """

    def __init__(self, config):
        self._enabled = config.voice_asr_enabled
        if not self._enabled:
            return
        self._locator = VoiceFileLocator(config.wechat_data_dir)
        self._decoder = SilkDecoder()
        self._asr = create_asr(config)  # 工厂函数，根据配置选择 ASR 实现
        self._cache = VoiceCache(Path("data/voice_cache.json"))
        self._stats = VoiceStats()      # 统计数据

    def process(self, msg: dict) -> str | None:
        """处理一条语音消息，返回识别文字或 None。

        Args:
            msg: WCDB 原始消息 dict

        Returns:
            识别出的文字，或 None（定位不到文件/解码失败/ASR 失败）
        """
        if not self._enabled:
            return None

        # 1. 提取 msg_svr_id
        msg_svr_id = extract_msg_svr_id(msg)
        if not msg_svr_id:
            return None

        # 2. 查缓存（同一 msg_svr_id 不重复识别）
        cached = self._cache.get(msg_svr_id)
        if cached:
            return cached

        # 3. 定位文件
        silk_path = self._locator.find_voice_file(msg)
        if not silk_path:
            self._stats.file_not_found += 1
            return None

        # 4. 解码 → WAV
        try:
            wav_path = self._decoder.decode(silk_path)
        except DecodeError:
            self._stats.decode_failed += 1
            return None

        # 5. ASR 识别
        try:
            result = self._asr.transcribe(wav_path, language="zh")
        except ASRError:
            self._stats.asr_failed += 1
            return None
        finally:
            # 清理临时 WAV 文件
            wav_path.unlink(missing_ok=True)

        # 6. 写入缓存
        self._cache.set(msg_svr_id, result.text, result.confidence)

        # 7. 低置信度标注
        if result.confidence < 0.6:
            return f"[可能不准确] {result.text}"

        return result.text
```

### 5.5 配置项新增（`.env`）

```ini
# === Voice Recognition ===
VOICE_ASR_ENABLED=false           # 总开关（默认关闭，用户手动开启）
VOICE_ASR_BACKEND=local_whisper    # local_whisper（默认，免费离线） | openai_whisper（云端付费）
VOICE_ASR_LANGUAGE=zh             # 识别语言

# OpenAI Whisper
VOICE_OPENAI_API_KEY=             # 不填则复用 OPENAI_API_KEY（如果有）
VOICE_OPENAI_BASE_URL=            # 不填则用默认 api.openai.com

# Local Whisper (faster-whisper)
VOICE_LOCAL_MODEL=small           # tiny / base / small / medium / large
                                  # small 是中文最优性价比

# Tencent Cloud ASR
VOICE_TENCENT_SECRET_ID=
VOICE_TENCENT_SECRET_KEY=
VOICE_TENCENT_REGION=ap-guangzhou
```

### 5.6 对应的 Config 数据类修改（`src/config.py`）

在 `BotConfig` dataclass 中新增字段：

```python
# === Voice Recognition ===
voice_asr_enabled: bool = False
voice_asr_backend: str = "local_whisper"
voice_asr_language: str = "zh"
voice_openai_api_key: str = ""
voice_openai_base_url: str = ""
voice_local_model: str = "small"
voice_tencent_secret_id: str = ""
voice_tencent_secret_key: str = ""
voice_tencent_region: str = "ap-guangzhou"
```

---

## 6. 消息处理流程改造

### 6.1 `src/wechat/wcdb_backend.py` — `_standardize()` 方法

**当前代码（约 line 433-437）：**

```python
# WCDB message fields: sender_username, message_content, local_type, create_time
sender = str(msg.get("sender_username", msg.get("senderUsername", msg.get("sender", ""))))
content = str(msg.get("message_content", msg.get("content", ""))).strip()
if not content:
    return None
```

**改为：**

```python
# WCDB message fields: sender_username, message_content, local_type, create_time
sender = str(msg.get("sender_username", msg.get("senderUsername", msg.get("sender", ""))))
content = str(msg.get("message_content", msg.get("content", ""))).strip()
local_type = int(msg.get("localType", msg.get("msg_type", 1)))

# ── 语音识别 ──────────────────────────────────────
if local_type == 34 and self._voice:
    voice_text = self._voice.process(msg)
    if voice_text:
        content = f"[语音] {voice_text}"
    else:
        content = "[语音]"
elif not content:
    return None
```

### 6.2 `src/wechat/mac_weflow_client.py` — `_message_to_source_row()` 方法

**当前代码（约 line 388-389）：**

```python
if local_type != 1:
    content = _message_type_label(local_type)
```

**改为：**

```python
if local_type != 1:
    if local_type == 34 and self._voice:
        voice_text = self._voice.process(row)
        if voice_text:
            content = f"[语音] {voice_text}"
        else:
            content = _message_type_label(local_type)
    else:
        content = _message_type_label(local_type)
```

---

## 7. 缓存策略

同一段语音不需要重复识别（用户在群里发了语音后，可能被多轮总结引用）。

```python
# data/voice_cache.json
{
  "7658291234567890": {
    "text": "今天晚上吃什么",
    "confidence": 0.95,
    "timestamp": 1717920000
  }
}
```

- **缓存键**: `msg_svr_id`（微信服务端消息 ID，全局唯一）
- **过期时间**: 7 天（语音文件通常也在这个时间被微信清理）
- **最大条目**: 10000（约 1MB JSON）
- **清理策略**: 写入时触发，移除超过 7 天的条目

---

## 8. 性能考量

### 各阶段耗时估算（3秒群聊语音）

| 阶段 | 耗时 | 备注 |
|------|------|------|
| 文件定位 | < 10ms | 纯文件系统操作 |
| SILK 解码 | ~50ms | pilk 纯 Python，3秒音频 |
| 云端 ASR (Whisper API) | 200-500ms | 网络 + API 处理 |
| 本地 Whisper (small, CPU) | 1-3s | 取决于 CPU 性能 |
| 本地 Whisper (small, GPU) | 0.3-1s | 如果有 CUDA |

### 对消息轮询的影响

- 现有消息处理已经在 `ThreadPoolExecutor` 中异步执行（`wcdb_backend.py:379`）
- 语音识别在同一个线程池中运行，不阻塞轮询
- 唯一影响是多占用一个线程池 worker，建议线程池大小 ≥ 4

### 内存

- pilk 解码器: ~5MB
- 本地 Whisper small 模型: ~1GB RAM（加载后常驻）
- 云端 ASR: 几乎不额外占用内存

---

## 9. 最终实施路线

| 步骤 | 内容 | 产物 | 工作量 |
|------|------|------|--------|
| **Step 1** | 环境准备 (pilk + faster-whisper) + build.spec + requirements | 依赖就绪 | 0.5h |
| **Step 2** | file_locator — 语音文件定位 | `src/voice/file_locator.py` | 半天 |
| **Step 3** | decoder — pilk SILK→WAV 解码 | `src/voice/decoder.py` | 半天 |
| **Step 4** | asr — OpenAIWhisperASR + LocalWhisperASR 两种实现 | `src/voice/asr.py` | 1天 |
| **Step 5** | pipeline — 流水线 + 缓存 + 统计 | `src/voice/pipeline.py` | 半天 |
| **Step 6** | config 改造 — BotConfig 新增字段 + load_config | `src/config.py` | 0.5h |
| **Step 7** | wcdb_backend 改造 — _standardize 插入语音识别 | `src/wechat/wcdb_backend.py` | 0.5h |
| **Step 8** | mac_weflow_client 改造 — 同上 | `src/wechat/mac_weflow_client.py` | 0.5h |

**Step 1-8 跑通 MVP 约需 3 天。**

### 配置选择指南

| 场景 | 推荐配置 |
|------|---------|
| 省钱、隐私、离线 | `VOICE_ASR_BACKEND=local_whisper`（默认）|
| 不占内存、追求准确率 | `VOICE_ASR_BACKEND=openai_whisper` + API Key |

---

## 10. 关键风险和注意事项

### 风险 1: 语音文件可能已被清理
微信会自动清理旧语音文件（通常保留 7-14 天，受微信设置影响）。
- **缓解**: 定位不到文件时，返回 `None`，保留 `[语音]` 占位符，不影响系统运行。

### 风险 2: 微信 SILK 封装格式可能变化
微信在标准 SILK 外层加了自定义 header，不同版本的 header 可能不同。
- **缓解**: pilk 库已处理常见的微信 SILK 封装，如果遇到新格式，先报错不崩溃，后续可适配。

### 风险 3: 识别准确率
微信 SILK 编码是 8kHz 采样，音质较低。中文方言、背景噪音、多人同时说话的识别准确率会下降。
- **缓解**: 低置信度结果标注 `[可能不准确]`；AI 总结 prompt 中注明语音转文字可能不完整。

### 风险 4: 隐私
云端 ASR 意味着语音内容上传到第三方（OpenAI / 腾讯）。
- **缓解**: 默认关闭，用户主动开启；提供本地 Whisper 模式完全离线；在 UI 中注明数据传输说明。

### 风险 5: 消息缺少 msg_svr_id 字段
WCDB DLL 返回的消息可能不包含 `msgSvrId`，导致无法定位语音文件。
- **缓解**: 也尝试用 `local_id` 作为备选定位键；Phase 1 优先验证 WCDB 返回的消息有哪些字段可用。

### 风险 6: 打包体积
如果使用本地 Whisper，模型文件 (~500MB for small) 会大幅增加 EXE 体积。
- **缓解**: 打包时不包含模型，首次运行时自动下载到 `data/models/`。

---

## 11. 相关文件索引

### 需要修改的文件

| 文件 | 改动内容 |
|------|----------|
| `src/wechat/wcdb_backend.py` | `__init__` 初始化 VoicePipeline; `_standardize` 对 localType=34 调用语音识别 |
| `src/wechat/mac_weflow_client.py` | `_message_to_source_row` 对 localType=34 调用语音识别 |
| `src/config.py` | 新增 voice 相关配置字段 |

### 新增的文件

| 文件 | 职责 |
|------|------|
| `src/voice/__init__.py` | 模块入口 |
| `src/voice/file_locator.py` | 根据 msg_svr_id 在文件系统中定位 .silk 文件 |
| `src/voice/decoder.py` | pilk SILK → WAV 解码 |
| `src/voice/asr.py` | ASR 抽象基类 + OpenAI/本地/腾讯 实现 |
| `src/voice/pipeline.py` | 串联定位→解码→识别→缓存的完整流水线 |

### 不需要修改但相关的文件

| 文件 | 原因 |
|------|------|
| `src/wechat/base.py` | 标准消息格式不变，content 字段自然承载识别文字 |
| `src/router.py` | 不需要改动，它只消费标准化消息 |
| `src/summarize/base.py` | 不需要改动，AI 拿到的是文字 |
| `src/summarize/prompts.py` | 不需要改动，`[语音] xxx` 作为文本正常格式化 |
