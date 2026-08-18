from flask import Flask, render_template, request, jsonify, Response
import uuid
import json
import threading
import subprocess
import os
import signal
import time
from typing import Dict, Any

# 导入处理器（替代原来的 ai_processor）
from processor import (
    TaskAgent, load_backend, get_available_backends, preheat_backend,
    get_current_backend_info, get_system_status, load_conversation,
    save_conversation, list_sessions, delete_session, agent_queues
)

# 导入命令执行引擎（工具工厂）
from toolexecute import execute_command_stream

app = Flask(__name__)
app.secret_key = 'change-this-secret-key'

# 存储活跃的 TaskAgent 实例
agents: Dict[str, TaskAgent] = {}

# 端口配置
PORT = 59123

def start_float_assistant():
    """启动悬浮窗（可选）"""
    try:
        subprocess.Popen(["python", "float_assistant.py", str(PORT)])
    except Exception as e:
        print(f"悬浮窗启动失败: {e}")

# ------------------- 页面路由 -------------------
@app.route('/')
def index():
    return render_template('index.html')

# ------------------- 后端管理 API -------------------
@app.route('/api/backends', methods=['GET'])
def api_list_backends():
    """获取所有可用后端列表"""
    backends = get_available_backends()
    return jsonify(backends)

@app.route('/api/load_backend', methods=['POST'])
def api_load_backend():
    """加载指定后端"""
    data = request.get_json()
    backend_name = data.get('name')
    if not backend_name:
        return jsonify({'error': '缺少后端名称'}), 400
    try:
        load_backend(backend_name)
        return jsonify({'status': 'ok', 'message': f'已切换到 {backend_name}'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/preheat', methods=['POST'])
def api_preheat():
    """预热当前后端（仅本地模型有效）"""
    try:
        preheat_backend()
        return jsonify({'status': 'ok', 'message': '预热完成'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

# ------------------- 会话管理 API -------------------
@app.route('/api/sessions', methods=['GET'])
def api_get_sessions():
    """获取所有会话列表"""
    sessions = list_sessions()
    return jsonify(sessions)

@app.route('/api/session/<session_id>', methods=['GET'])
def api_get_session(session_id):
    """获取特定会话的消息记录"""
    messages = load_conversation(session_id)
    return jsonify(messages)

@app.route('/api/session/new', methods=['POST'])
def api_new_session():
    """创建新会话"""
    data = request.get_json() or {}
    first_msg = data.get('message', '新对话')
    session_id = f"{int(time.time())}_{uuid.uuid4().hex[:8]}"
    save_conversation(session_id, [])
    return jsonify({'session_id': session_id})

@app.route('/api/session/<session_id>', methods=['DELETE'])
def api_delete_session(session_id):
    """删除会话"""
    try:
        if session_id in agents:
            agents[session_id].stop()
            del agents[session_id]
        if session_id in agent_queues:
            del agent_queues[session_id]
        delete_session(session_id)
        return jsonify({'status': 'ok'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

# ------------------- 任务执行 API -------------------
@app.route('/execute/message', methods=['POST'])
def execute_message():
    """发送用户消息，创建或继续任务"""
    data = request.get_json()
    message = data.get('message', '').strip()
    session_id = data.get('session_id')
    
    if not message:
        return jsonify({'error': '消息不能为空'}), 400
    
    if not session_id or session_id not in agents:
        if not session_id:
            session_id = f"{int(time.time())}_{uuid.uuid4().hex[:8]}"
        agents[session_id] = TaskAgent(message, session_id)
    else:
        agents[session_id].receive_input(message)
    
    return jsonify({'session_id': session_id, 'status': 'accepted'})

@app.route('/api/generate_command/<session_id>', methods=['GET'])
def generate_command(session_id):
    agent = agents.get(session_id)
    if not agent:
        return Response("data: {\"type\":\"error\",\"message\":\"无效会话\"}\n\n", 
                       mimetype='text/event-stream')

    enable_thinking = request.args.get('thinking', 'false').lower() == 'true'

    def generate():
        try:
            # 直接迭代生成器，yield 每个事件
            for event in agent.generate_next_command(enable_thinking=enable_thinking):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except Exception as e:
            yield f"data: {{\"type\":\"error\",\"message\":\"{str(e)}\"}}\n\n"
        finally:
            # 无论如何都发送结束标记
            yield "data: [DONE]\n\n"
            #time.sleep(1)

    return Response(generate(), mimetype='text/event-stream')

@app.route('/api/execute_command', methods=['POST'])
def api_execute_command():
    """流式执行命令，返回 SSE 流"""
    data = request.get_json()
    command_obj = data.get('command')
    if not command_obj:
        return jsonify({'success': False, 'output': '缺少命令对象'}), 400

    def generate():
        for event in execute_command_stream(command_obj):
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    return Response(generate(), mimetype='text/event-stream')

@app.route('/api/add_result', methods=['POST'])
def api_add_result():
    """将命令执行结果添加到会话历史中"""
    data = request.get_json()
    session_id = data.get('session_id')
    command = data.get('command')
    success = data.get('success', False)
    output = data.get('output', '')
    agent = agents.get(session_id)
    if agent:
        agent.add_command_result(command, success, output)
        return jsonify({'status': 'ok'})
    return jsonify({'status': 'error', 'message': '会话不存在'}), 404

@app.route('/api/generate_summary/<session_id>', methods=['GET'])
def generate_summary(session_id):
    """流式生成最终总结"""
    agent = agents.get(session_id)
    if not agent:
        return Response("data: {\"type\":\"error\",\"message\":\"无效会话\"}\n\n", 
                       mimetype='text/event-stream')
    
    def generate():
        try:
            for chunk in agent.generate_summary():
                yield f"data: {json.dumps({'type': 'chunk', 'content': chunk}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:
            yield f"data: {{\"type\":\"error\",\"message\":\"{str(e)}\"}}\n\n"
        finally:
            if session_id in agents:
                del agents[session_id]
    
    return Response(generate(), mimetype='text/event-stream')

@app.route('/execute/stop/<session_id>', methods=['POST'])
def execute_stop(session_id):
    """停止当前任务"""
    agent = agents.get(session_id)
    if agent:
        agent.stop()
    return jsonify({'status': 'stopped'})

# ------------------- 状态 API -------------------
@app.route('/status')
def system_status():
    status = get_system_status()
    return jsonify(status)

@app.route('/shutdown', methods=['POST'])
def shutdown():
    os.kill(os.getpid(), signal.SIGINT)
    return jsonify({'status': 'shutting_down'})

# ------------------- 启动 -------------------
if __name__ == '__main__':
    print(f"AI 助手服务启动在 http://127.0.0.1:{PORT}")
    app.run(host='0.0.0.0', port=PORT, debug=False, threaded=False)