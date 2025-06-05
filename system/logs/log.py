import sqlite3
from flask import Blueprint, request, jsonify
import time
import json

# 创建蓝图
log_bp = Blueprint('log', __name__)

# 获取数据库连接
def get_db_connection():
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    return conn

# 下面两个函数记录习惯
@log_bp.route('/update_habit', methods=['POST'])
def update_habit():
    data = request.json
    username = data.get('username')
    temperature = data.get('temperature')
    music = data.get('music')
    
    if not username:
        print(000)
        return jsonify({'error': 'Missing required fields'}), 400
    
    if temperature is None and music is None:
        return jsonify({'error': 'Missing temperature and music'}), 400
    
    
    conn = get_db_connection()
    cursor = conn.cursor()
    # 查询是否已有记录
    cursor.execute("SELECT * FROM habit WHERE username = ?", (username,))
    result = cursor.fetchone()

    if result:
        # 记录已存在，根据字段进行更新
        if temperature is not None:
            print(111)
            cursor.execute(
                "UPDATE habit SET temperature = ? WHERE username = ?",
                (temperature, username)
            )
        if music is not None:
            cursor.execute(
                "UPDATE habit SET music = ? WHERE username = ?",
                (music, username)
            )
    else:
        # 记录不存在，插入新行，未提供的字段使用默认值
        cursor.execute(
            "INSERT INTO habit (username, temperature, music) VALUES (?, ?, ?)",
            (
                username,
                temperature if temperature is not None else 24,
                music if music is not None else 50
            )
        )
        print(222)

    conn.commit()
    conn.close()
    
    return jsonify({'success': True})

# ✅ 插入日志
def insert_log(username, role,type, action):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        # cursor.execute("INSERT INTO logs (username, role, action) VALUES (?, ?, ?)", 
        #                (username, role, action))
        cursor.execute("INSERT INTO log (username, role, type, action) VALUES (?, ?, ?, ?)", 
                       (username, role, type, action))
        conn.commit()
        conn.close()
        print("[日志写入]")
    except Exception as e:
        print(f"[日志写入失败] {e}")


# 获取日志数据
@log_bp.route('/get_logs', methods=['GET'])
def get_logs():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 获取查询参数
    search = request.args.get('search', '')
    search_by = request.args.get('search_by', 'all')  # 指定搜索的字段
    page = int(request.args.get('page', 1))
    per_page = 10
    
    # 构建查询
    query = 'SELECT * FROM log'
    params = []
    
    if search:
        if search_by == 'id':
            query += ' WHERE id LIKE ?'
            params.append(f'%{search}%')
        elif search_by == 'action':
            query += ' WHERE action LIKE ?'
            params.append(f'%{search}%')
        elif search_by == 'username':
            query += ' WHERE username LIKE ?'
            params.append(f'%{search}%')
        else:  # 默认搜索所有字段
            query += ' WHERE action LIKE ? OR username LIKE ? OR role LIKE ? OR type LIKE ?'
            search_param = f'%{search}%'
            params.extend([search_param] * 4)
    
    # 分页
    offset = (page - 1) * per_page
    query += ' ORDER BY timestamp DESC LIMIT ? OFFSET ?'
    params.extend([per_page, offset])
    
    cursor.execute(query, params)
    logs = cursor.fetchall()
    
    # 获取总数
    count_query = 'SELECT COUNT(*) FROM log'
    if search:
        if search_by == 'id':
            count_query += ' WHERE id LIKE ?'
            cursor.execute(count_query, [f'%{search}%'])
        elif search_by == 'action':
            count_query += ' WHERE action LIKE ?'
            cursor.execute(count_query, [f'%{search}%'])
        elif search_by == 'username':
            count_query += ' WHERE username LIKE ?'
            cursor.execute(count_query, [f'%{search}%'])
        else:
            count_query += ' WHERE action LIKE ? OR username LIKE ? OR role LIKE ? OR type LIKE ?'
            cursor.execute(count_query, [f'%{search}%' for _ in range(4)])
    else:
        cursor.execute(count_query)
    
    total = cursor.fetchone()[0]
    total_pages = (total + per_page - 1) // per_page
    
    conn.close()
    
    # 转换为字典列表
    logs_list = [dict(log) for log in logs]
    
    return jsonify({
        'logs': logs_list,
        'total': total,
        'total_pages': total_pages,
        'current_page': page
    })

# 获取单个日志
@log_bp.route('/get_logs/<int:log_id>', methods=['GET'])
def get_log(log_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM log WHERE id = ?', (log_id,))
    log = cursor.fetchone()
    conn.close()
    
    if log:
        return jsonify(dict(log))
    else:
        return jsonify({'error': 'Log not found'}), 404

# 添加日志
@log_bp.route('/add_logs', methods=['POST'])
def add_log():
    data = request.json
    username = data.get('username')
    role = data.get('role')
    type = data.get('type')
    action = data.get('action')
    
    if not username or not role or not type or not action:
        return jsonify({'error': 'Missing required fields'}), 400
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        'INSERT INTO log (username, role, type, action) VALUES (?, ?, ?, ?)',
        (username, role, type, action)
    )
    conn.commit()
    log_id = cursor.lastrowid
    conn.close()
    
    return jsonify({'id': log_id}), 201

# 更新日志
@log_bp.route('/up_logs/<int:log_id>', methods=['PUT'])
def update_log(log_id):
    data = request.json
    username = data.get('username')
    role = data.get('role')
    type = data.get('type')
    action = data.get('action')
    
    if not username or not role or not type or not action:
        return jsonify({'error': 'Missing required fields'}), 400
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        'UPDATE log SET username = ?, role = ?, type = ?, action = ? WHERE id = ?',
        (username, role, type, action, log_id)
    )
    conn.commit()
    conn.close()
    
    return jsonify({'success': True})

# 删除日志
@log_bp.route('/de_logs/<int:log_id>', methods=['DELETE'])
def delete_log(log_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM log WHERE id = ?', (log_id,))
    conn.commit()
    conn.close()
    
    return jsonify({'success': True})

# 获取统计信息
@log_bp.route('/stats', methods=['GET'])
def get_stats():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 获取总日志数
    cursor.execute('SELECT COUNT(*) FROM log')
    total_logs = cursor.fetchone()[0]
    
    # 获取按角色统计的日志数
    cursor.execute('SELECT role, COUNT(*) FROM log GROUP BY role')
    role_stats = cursor.fetchall()
    
    # 获取按动作统计的日志数
    cursor.execute('SELECT action, COUNT(*) FROM log GROUP BY action')
    action_stats = cursor.fetchall()

    # 获取按类型统计的日志数
    cursor.execute('SELECT type, COUNT(*) FROM log GROUP BY type')
    type_stats = cursor.fetchall()
    
    conn.close()
    
    roles = {row['role']: row[1] for row in role_stats}
    actions = {row['action']: row[1] for row in action_stats}
    types = {row['type']: row[1] for row in type_stats}
    
    return jsonify({
        'total_logs': total_logs,
        'role_stats': roles,
        'action_stats': actions,
        'type_stats': types
    })