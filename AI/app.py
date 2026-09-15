# app.py
import logging
from threading import Thread
from flask import Flask, request, jsonify, Response
from PIL import Image
import torch, base64, io, json
from transformers import (
    AutoModelForImageTextToText,
    AutoTokenizer,
    TextIteratorStreamer,
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)
logger = logging.getLogger('ai-service')

app = Flask(__name__)

# ===== 1. 启动时一次性加载模型 =====
model_path = r"D:\grauateDesign\AI\Qwen3-VL-4B-Instruct"
device = "cuda" if torch.cuda.is_available() else "cpu"

if torch.cuda.is_available():
    logger.info("使用 GPU 进行推理")
    # 尝试使用4-bit量化加载（更节省显存）
    try:
        from transformers import BitsAndBytesConfig
        logger.info("正在使用 4-bit 量化加载模型...")
        
        # 配置4-bit量化，启用CPU offload
        quantization_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_compute_dtype=torch.float16,
            bnb_4bit_use_double_quant=True,
            bnb_4bit_quant_type="nf4",
            llm_int8_enable_fp32_cpu_offload=True  # 启用CPU offload
        )
        
        # 自定义device_map，允许部分层在CPU上
        device_map = "auto"
        
        tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)
        model = AutoModelForImageTextToText.from_pretrained(
            model_path,
            quantization_config=quantization_config,
            device_map=device_map,
            trust_remote_code=True,
            low_cpu_mem_usage=True
        )
        logger.info("4-bit 量化模型加载完成！")
    except Exception as e:
        logger.error("4-bit量化加载失败，使用默认float16: %s", e)
        tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)
        model = AutoModelForImageTextToText.from_pretrained(
            model_path,
            dtype=torch.float16,
            device_map="auto",
            trust_remote_code=True
        )
        logger.info("模型加载完成！")
else:
    logger.info("使用 CPU 进行推理，可能较慢")
    tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)
    model = AutoModelForImageTextToText.from_pretrained(
        model_path,
        dtype=torch.float16,
        device_map="auto",
        trust_remote_code=True
    )
    logger.info("模型加载完成！")

@app.route("/")
def index():
    return jsonify(msg="Qwen3-VL-4B-Instruct 服务已启动（4-bit量化），请用 POST /chat 调用")

# 生成参数（/chat 与 /chat/stream 共用）
GENERATE_KWARGS = dict(
    max_new_tokens=512,
    do_sample=True,
    temperature=0.7,
    top_p=0.95,
)


def _parse_chat_request():
    """解析请求，返回 (prompt, b64_img, 错误响应或 None)"""
    # 注意：请求体含 base64 图像，可能达数 MB，只记录长度不转储内容
    logger.debug("请求体长度: %d 字符", len(request.get_data(as_text=True)))

    try:
        data = request.get_json(force=True)
    except Exception as e:
        logger.error("JSON 解析失败: %s", e)
        return None, None, (jsonify(error="JSON 解析失败", detail=str(e)), 400)

    prompt = data.get("prompt", "")
    b64_img = data.get("image", None)
    if not prompt:
        return None, None, (jsonify(error="字段 'prompt' 不能为空"), 400)
    return prompt, b64_img, None


def _build_messages(prompt, b64_img):
    """构造多模态输入；图片解码失败时抛出异常"""
    if not b64_img:
        return [{"role": "user", "content": [{"type": "text", "text": prompt}]}]
    img = Image.open(io.BytesIO(base64.b64decode(b64_img))).convert("RGB")
    return [{"role": "user", "content": [{"type": "image", "image": img},
                                         {"type": "text", "text": prompt}]}]


def _prepare_inputs(messages):
    prompt_txt = tokenizer.apply_chat_template(
        messages, add_generation_prompt=True, tokenize=False)
    return tokenizer(prompt_txt, return_tensors="pt").to(model.device)


@app.route("/chat", methods=["POST"])
def chat():
    """非流式推理，一次性返回完整文本"""
    prompt, b64_img, err = _parse_chat_request()
    if err:
        return err

    try:
        messages = _build_messages(prompt, b64_img)
    except Exception as e:
        logger.error("image 解码失败: %s", e)
        return jsonify(error="image 解码失败", detail=str(e)), 400

    inputs = _prepare_inputs(messages)
    with torch.no_grad():
        outputs = model.generate(**inputs, **GENERATE_KWARGS)

    reply = tokenizer.decode(outputs[0][inputs.input_ids.shape[1]:],
                             skip_special_tokens=True)
    return app.response_class(
        json.dumps({"reply": reply.strip()}, ensure_ascii=False),
        mimetype='application/json'
    )


@app.route("/chat/stream", methods=["POST"])
def chat_stream():
    """流式推理（SSE）

    事件格式：data: {"delta": "增量文本"}
    结束标记：data: [DONE]

    注意与 OpenAI 兼容接口的格式差异：后者为
    data: {"choices":[{"delta":{"content":"..."}}]}
    """
    prompt, b64_img, err = _parse_chat_request()
    if err:
        return err

    try:
        messages = _build_messages(prompt, b64_img)
    except Exception as e:
        logger.error("image 解码失败: %s", e)
        return jsonify(error="image 解码失败", detail=str(e)), 400

    inputs = _prepare_inputs(messages)
    streamer = TextIteratorStreamer(tokenizer, skip_prompt=True,
                                    skip_special_tokens=True)
    # 生成必须放到子线程，主线程同时消费 streamer 才能实现逐块输出
    Thread(
        target=model.generate,
        kwargs={**inputs, **GENERATE_KWARGS, "streamer": streamer},
        daemon=True,
    ).start()

    def generate():
        try:
            for chunk in streamer:
                if chunk:
                    yield f'data: {json.dumps({"delta": chunk}, ensure_ascii=False)}\n\n'
        except Exception as e:
            logger.error("流式推理失败: %s", e, exc_info=True)
            yield f'data: {json.dumps({"error": str(e)}, ensure_ascii=False)}\n\n'
        finally:
            yield 'data: [DONE]\n\n'

    return Response(
        generate(),
        mimetype='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'},
    )

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=False)
