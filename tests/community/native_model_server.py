"""Pinned CPU models for owned native acceptance; loopback only, no remote code."""
import gc
import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

GENERATOR = 'Qwen/Qwen2.5-Coder-1.5B-Instruct'
REVIEWER = 'Qwen/Qwen3-4B-Instruct-2507'
REVISIONS = {GENERATOR: 'd18ecad881a290f0c792f1c2b5dbee1820d4a424',
             REVIEWER: 'abcc171021d4f320b2e7f47c6f0deca67ded870c'}


def main():
    import torch
    from huggingface_hub import snapshot_download
    from transformers import AutoModelForCausalLM, AutoTokenizer
    torch.set_num_threads(min(4, os.cpu_count() or 2))
    # Downloads are bounded by the harness startup deadline, before inference
    # requests begin. Only fixed safetensors/tokenizer/config files are allowed.
    for name, revision in REVISIONS.items():
        snapshot_download(name, revision=revision, allow_patterns=['*.json', '*.txt', '*.safetensors'])
    model = tokenizer = active = None

    def load_model(name):
        nonlocal model, tokenizer, active
        if active == name:
            return
        model = tokenizer = active = None
        gc.collect()
        tokenizer = AutoTokenizer.from_pretrained(name, revision=REVISIONS[name],
                                                 trust_remote_code=False, local_files_only=True)
        model = AutoModelForCausalLM.from_pretrained(name, revision=REVISIONS[name],
                    trust_remote_code=False, local_files_only=True,
                    use_safetensors=True, dtype=torch.bfloat16)
        model.eval()
        if name == REVIEWER:
            # Replace one Linear at a time; no full-model float32 deepcopy.
            def quantize_linears(module):
                for child_name, child in list(module.named_children()):
                    if isinstance(child, torch.nn.Linear):
                        wrapped = torch.nn.Sequential(child.float()).eval()
                        converted = torch.ao.quantization.quantize_dynamic(
                            wrapped, {torch.nn.Linear: torch.ao.quantization.per_channel_dynamic_qconfig})
                        setattr(module, child_name, converted[0])
                    else:
                        quantize_linears(child)
            quantize_linears(model)
            model.float()
        active = name

    load_model(GENERATOR)
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
                name = request.get('model')
                if name not in REVISIONS:
                    raise ValueError('unexpected model')
                messages = request['messages']
                if len(messages) != 1 or messages[0].get('role') != 'user':
                    raise ValueError('one user prompt required')
                with lock, torch.inference_mode():
                    load_model(name)
                    inputs = tokenizer.apply_chat_template(messages, add_generation_prompt=True,
                                                           return_tensors='pt', return_dict=True)
                    if inputs['input_ids'].shape[-1] > 8192:
                        raise ValueError('prompt exceeds acceptance budget')
                    output = model.generate(**inputs, max_new_tokens=1024, max_time=140,
                                            do_sample=False, pad_token_id=tokenizer.eos_token_id)
                    content = tokenizer.decode(output[0, inputs['input_ids'].shape[-1]:],
                                               skip_special_tokens=True)
                if os.environ.get('DARKMOON_NATIVE_MODEL_TRACE') == '1':
                    # Enabled only by the fixed synthetic harness, never by default.
                    print(json.dumps({'native_model_response': name, 'content': content[:16384]}),
                          file=sys.stderr, flush=True)
                body = json.dumps({'choices': [{'message': {'role': 'assistant', 'content': content}}]}).encode()
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except Exception as error:
                print('native model failure: ' + type(error).__name__, file=sys.stderr, flush=True)
                self.send_error(500, 'native model request failed')

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    print(json.dumps({'port': server.server_port, 'model': GENERATOR, 'revision': REVISIONS[GENERATOR],
                      'review_model': REVIEWER, 'review_revision': REVISIONS[REVIEWER],
                      'quantization': {'generation': 'bfloat16', 'review': 'dynamic-int8-linear-per-channel'}}), flush=True)
    server.serve_forever()


if __name__ == '__main__':
    main()
