import sqlite3

# ✅ 插入日志
def insert_log(username, role, action):
    try:
        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()
        cursor.execute("INSERT INTO logs (username, role, action) VALUES (?, ?, ?)", 
                       (username, role, action))
        conn.commit()
        conn.close()
        print("[日志写入]")
    except Exception as e:
        print(f"[日志写入失败] {e}")

# # ✅ 获取日志（全部、按用户名、按类型）
# @app.route('/get_logs', methods=['GET'])
# def get_logs():
#     if 'username' not in session or session['role'] != 'admin':
#         return redirect('/login')

#     conn = sqlite3.connect('database.db')
#     cursor = conn.cursor()
#     query = "SELECT id, username, role, action, timestamp FROM logs WHERE 1=1"
#     params = []

#     username = request.args.get("username")
#     action = request.args.get("action")

#     if username:
#         query += " AND username=?"
#         params.append(username)
#     if action:
#         query += " AND action LIKE ?"
#         params.append(f"%{action}%")

#     query += " ORDER BY timestamp DESC"
#     cursor.execute(query, params)
#     logs = cursor.fetchall()
#     conn.close()
#     return render_template('logs.html', logs=logs)

# # ✅ 删除所有日志
# @app.route('/logs/delete_all', methods=['POST'])
# def delete_all_logs():
#     if 'username' not in session or session['role'] != 'admin':
#         return jsonify(success=False, message="无权限")

#     conn = sqlite3.connect('database.db')
#     cursor = conn.cursor()
#     cursor.execute("DELETE FROM logs")
#     conn.commit()
#     conn.close()
#     return jsonify(success=True, message="已删除所有日志")

# # ✅ 删除指定用户的所有日志
# @app.route('/logs/delete_user', methods=['POST'])
# def delete_logs_by_username():
#     if 'username' not in session or session['role'] != 'admin':
#         return jsonify(success=False, message="无权限")
    
#     data = request.get_json()
#     username = data.get('username')
#     if not username:
#         return jsonify(success=False, message="用户名不能为空")

#     conn = sqlite3.connect('database.db')
#     cursor = conn.cursor()
#     cursor.execute("DELETE FROM logs WHERE username=?", (username,))
#     conn.commit()
#     conn.close()
#     return jsonify(success=True, message=f"已删除用户 {username} 的所有日志")

# # ✅ 删除单条日志
# @app.route('/logs/delete/<int:log_id>', methods=['POST'])
# def delete_log(log_id):
#     if 'username' not in session or session['role'] != 'admin':
#         return jsonify(success=False, message="无权限")

#     conn = sqlite3.connect('database.db')
#     cursor = conn.cursor()
#     cursor.execute("DELETE FROM logs WHERE id=?", (log_id,))
#     conn.commit()
#     conn.close()
#     return jsonify(success=True, message="日志删除成功")

# # ✅ 更新日志内容
# @app.route('/logs/update/<int:log_id>', methods=['POST'])
# def update_log(log_id):
#     if 'username' not in session or session['role'] != 'admin':
#         return jsonify(success=False, message="无权限")

#     data = request.get_json()
#     new_action = data.get('action')
#     if not new_action:
#         return jsonify(success=False, message="操作内容不能为空")

#     conn = sqlite3.connect('database.db')
#     cursor = conn.cursor()
#     cursor.execute("UPDATE logs SET action=? WHERE id=?", (new_action, log_id))
#     conn.commit()
#     conn.close()
#     return jsonify(success=True, message="日志内容已更新")