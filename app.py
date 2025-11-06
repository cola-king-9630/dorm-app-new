from flask import Flask, request, jsonify, render_template
import os
import pg8000
from datetime import datetime, time
import urllib.parse

app = Flask(__name__)

# 从环境变量获取 Supabase PostgreSQL 数据库连接字符串
DATABASE_URL = os.environ.get('DATABASE_URL')

def get_db_connection():
    """创建并返回数据库连接"""
    # 解析数据库连接字符串
    url = urllib.parse.urlparse(DATABASE_URL)
    # 使用 pg8000 建立连接（纯Python驱动，兼容性极佳）
    conn = pg8000.connect(
        host=url.hostname,
        port=url.port,
        user=url.username,
        password=url.password,
        database=url.path[1:],  # 去掉路径开头的 '/'
        ssl_context=True  # Supabase 要求 SSL 连接
    )
    return conn

def init_db():
    """初始化数据库表（如果不存在则创建）"""
    conn = get_db_connection()
    cur = conn.cursor()
    # 创建记录表
    cur.execute('''
        CREATE TABLE IF NOT EXISTS sleep_records (
            id SERIAL PRIMARY KEY,
            sleep_time TIME NOT NULL,
            record_date DATE NOT NULL UNIQUE, -- 确保同一天只有一条记录
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    cur.close()
    conn.close()

@app.route('/')
def index():
    """主页面，返回HTML"""
    return render_template('index.html')

@app.route('/api/records', methods=['GET', 'POST'])
def handle_records():
    """处理睡眠记录的获取和提交"""
    conn = get_db_connection()
    cur = conn.cursor()

    if request.method == 'POST':
        # 提交新记录
        data = request.json
        try:
            cur.execute(
                "INSERT INTO sleep_records (sleep_time, record_date) VALUES (%s, %s) RETURNING id, sleep_time, record_date",
                (data['sleep_time'], data['record_date'])
            )
            conn.commit()
            record = cur.fetchone()
            return jsonify({"status": "记录成功！", "record": {"id": record[0], "sleep_time": str(record[1]), "record_date": record[2].isoformat()}})
        except pg8000.IntegrityError:
            # 处理同一天重复提交的情况
            return jsonify({"status": "错误", "message": "今日记录已存在！"}), 400
        finally:
            cur.close()
            conn.close()

    else:
        # 获取所有记录
        cur.execute("SELECT id, sleep_time, record_date FROM sleep_records ORDER BY record_date DESC")
        records = cur.fetchall()
        cur.close()
        conn.close()
        
        records_list = [{"id": r[0], "sleep_time": str(r[1]), "record_date": r[2].isoformat()} for r in records]
        return jsonify(records_list)

@app.route('/api/stats')
def get_stats():
    """获取统计信息（总记录数、总熬夜时间）"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute("SELECT COUNT(*) as total_count FROM sleep_records")
    total_count = cur.fetchone()[0]
    
    cur.execute("SELECT sleep_time FROM sleep_records")
    times = [row[0] for row in cur.fetchall()]
    
    # 计算总熬夜时间（假设23:00后睡觉算熬夜）
    total_late_minutes = 0
    for t in times:
        if t.hour >= 23:
            total_late_minutes += (t.hour - 23) * 60 + t.minute
    
    cur.close()
    conn.close()
    return jsonify({
        "total_records": total_count,
        "total_late_minutes": total_late_minutes
    })

# 应用启动时初始化数据库
init_db()

if __name__ == '__main__':
    app.run(debug=True)
