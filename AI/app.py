# app.py
from flask import Flask, request, jsonify
from PIL import Image
import torch, base64, io, json
from transformers import AutoModelForImageTextToText, AutoTokenizer

app = Flask(__name__)

# ===== 1. 启动时一次性加载模型 =====
model_path = r"D:\grauateDesign\AI\Qwen3-VL-4B-Instruct"
device = "cuda" if torch.cuda.is_available() else "cpu"

if torch.cuda.is_available():
    print("使用 GPU 进行推理")
    # 尝试使用4-bit量化加载（更节省显存）
    try:
        from transformers import BitsAndBytesConfig
        print("正在使用 4-bit 量化加载模型...")
        
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
        print("4-bit 量化模型加载完成！")
    except Exception as e:
        print(f"4-bit量化加载失败，使用默认float16: {e}")
        tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)
        model = AutoModelForImageTextToText.from_pretrained(
            model_path,
            dtype=torch.float16,
            device_map="auto",
            trust_remote_code=True
        )
        print("模型加载完成！")
else:
    print("使用 CPU 进行推理，可能较慢")
    tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)
    model = AutoModelForImageTextToText.from_pretrained(
        model_path,
        dtype=torch.float16,
        device_map="auto",
        trust_remote_code=True
    )
    print("模型加载完成！")

@app.route("/")
def index():
    return jsonify(msg="Qwen3-VL-4B-Instruct 服务已启动（4-bit量化），请用 POST /chat 调用")

@app.route("/chat", methods=["POST"])
def chat():
    # ===== 2. 调试：先打印原始请求 =====
    print("Headers:", request.headers)
    print("Body raw:", request.get_data(as_text=True))

    # ===== 3. 解析 JSON =====
    try:
        data = request.get_json(force=True)
    except Exception as e:
        return jsonify(error="JSON 解析失败", detail=str(e)), 400

    print("解析后 data:", data)
    prompt = data.get("prompt", "")
    b64_img = data.get("image", None)
    if not prompt:
        return jsonify(error="字段 'prompt' 不能为空"), 400

    # ===== 4. 构造多模态输入 =====
    if b64_img:
        try:
            img = Image.open(io.BytesIO(base64.b64decode(b64_img))).convert("RGB")
        except Exception as e:
            return jsonify(error="image 解码失败", detail=str(e)), 400
        messages = [{"role": "user", "content": [{"type": "image", "image": img},
                                                {"type": "text",  "text":  prompt}]}]
    else:
        messages = [{"role": "user", "content": [{"type": "text", "text": prompt}]}]

    # ===== 5. 推理 =====
    prompt_txt = tokenizer.apply_chat_template(messages, add_generation_prompt=True, tokenize=False)
    inputs = tokenizer(prompt_txt, return_tensors="pt").to(model.device)

    with torch.no_grad():
        outputs = model.generate(**inputs,
                                 max_new_tokens=512,
                                 do_sample=True,
                                 temperature=0.7,
                                 top_p=0.95)
    reply = tokenizer.decode(outputs[0][inputs.input_ids.shape[1]:], skip_special_tokens=True)
    return app.response_class(
        json.dumps({"reply": reply.strip()}, ensure_ascii=False),
        mimetype='application/json'
    )

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=False)
