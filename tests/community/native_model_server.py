"""Pinned CPU model host for native remediation acceptance; loopback only.

Optional isolated dependencies: torch==2.9.0+cpu, transformers==4.57.1.
No remote code, fixed model revision, no canned patch or review responses.
"""
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MODEL = 'Qwen/Qwen3-4B-Instruct-2507'
REVISION = 'abcc171021d4f320b2e7f47c6f0deca67ded870c'


def main():
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    torch.set_num_threads(min(4, os.cpu_count() or 2))
    tokenizer = AutoTokenizer.from_pretrained(MODEL, revision=REVISION, trust_remote_code=False)
    model = AutoModelForCausalLM.from_pretrained(MODEL, revision=REVISION,
                                               trust_remote_code=False, use_safetensors=True,
                                               dtype=torch.bfloat16)
    model.eval()
    # Convert one Linear at a time: never materialize the entire 4B model in
    # float32 or make a full-model deepcopy. CPU int8 avoids slow bf16 emulation.
    def quantize_linears(module):
        for name, child in list(module.named_children()):
            if isinstance(child, torch.nn.Linear):
                wrapped = torch.nn.Sequential(child.float()).eval()
                converted = torch.ao.quantization.quantize_dynamic(
                    wrapped, {torch.nn.Linear}, dtype=torch.qint8)
                setattr(module, name, converted[0])
            else:
                quantize_linears(child)
    quantize_linears(model)
    model.float()
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if self.path != '/v1/chat/completions' or not 0 < size <= 131072:
                    raise ValueError('invalid request')
                request = json.loads(self.rfile.read(size))
                if request.get('model') != MODEL:
                    raise ValueError('unexpected model')
                messages = request['messages']
                if len(messages) != 1 or messages[0].get('role') != 'user':
                    raise ValueError('one user prompt required')
                inputs = tokenizer.apply_chat_template(messages, add_generation_prompt=True,
                                                       return_tensors='pt', return_dict=True)
                if inputs['input_ids'].shape[-1] > 8192:
                    raise ValueError('prompt exceeds acceptance budget')
                with lock, torch.inference_mode():
                    output = model.generate(**inputs, max_new_tokens=1024, max_time=140,
                                            do_sample=False, pad_token_id=tokenizer.eos_token_id)
                content = tokenizer.decode(output[0, inputs['input_ids'].shape[-1]:],
                                           skip_special_tokens=True)
                body = json.dumps({'choices': [{'message': {'role': 'assistant', 'content': content}}]}).encode()
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except Exception:
                self.send_error(500, 'native model request failed')

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    print(json.dumps({'port': server.server_port, 'model': MODEL, 'revision': REVISION,
                      'quantization': 'dynamic-int8-linear'}), flush=True)
    server.serve_forever()


if __name__ == '__main__':
    main()
