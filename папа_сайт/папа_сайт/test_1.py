import os
import threading
import sqlite3
import time
from flask import Flask, render_template, request, jsonify, url_for
import telebot

# === НАСТРОЙКИ ===
TOKEN = '8274106045:AAHaGP4NrGl_ogP8eWUnNWI25Q-zyycswm0'
bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# --- Авторизация пользователей ---
USERS = {
    'admin1': 'pass1',
    'admin2': 'pass2',
    'admin3': 'pass3'
}
sessions = {}  # chat_id -> {'user': login, 'last_activity': timestamp}
TIMEOUT = 600  # 10 минут

# === БАЗА ДАННЫХ ===
DB_FILE = "shop.db"
conn = sqlite3.connect(DB_FILE, check_same_thread=False)
cursor = conn.cursor()

cursor.execute('''CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    short_desc TEXT NOT NULL,
    long_desc TEXT NOT NULL,
    price_per_100 REAL NOT NULL
)''')

cursor.execute('''CREATE TABLE IF NOT EXISTS product_weights (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER,
    weight INTEGER NOT NULL,
    FOREIGN KEY(product_id) REFERENCES products(id) ON DELETE CASCADE
)''')

cursor.execute('''CREATE TABLE IF NOT EXISTS product_photos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER,
    filename TEXT NOT NULL,
    FOREIGN KEY(product_id) REFERENCES products(id) ON DELETE CASCADE
)''')

cursor.execute('''CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER,
    weight INTEGER,
    name TEXT,
    phone TEXT,
    comment TEXT,
    FOREIGN KEY(product_id) REFERENCES products(id) ON DELETE CASCADE
)''')

cursor.execute('''CREATE TABLE IF NOT EXISTS reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    text TEXT NOT NULL
)''')

conn.commit()

# === FLASK ===
@app.route('/')
def index():
    cursor.execute("SELECT * FROM products")
    products = cursor.fetchall()
    products_list = []
    for p in products:
        cursor.execute("SELECT filename FROM product_photos WHERE product_id=?", (p[0],))
        photos = [url_for('static', filename=f.split('static/')[1]) for f in [r[0] for r in cursor.fetchall()]]
        products_list.append({
            "id": p[0], "name": p[1],
            "short_desc": p[2], "long_desc": p[3],
            "price_per_100": p[4], "photos": photos
        })
    return render_template('index.html', products=products_list)

@app.route('/product/<int:pid>')
def product_page(pid):
    cursor.execute("SELECT * FROM products WHERE id=?", (pid,))
    p = cursor.fetchone()
    if not p:
        return "Товар не найден"
    cursor.execute("SELECT filename FROM product_photos WHERE product_id=?", (pid,))
    photos = [url_for('static', filename=f[0].split('static/')[1]) for f in cursor.fetchall()]
    cursor.execute("SELECT weight FROM product_weights WHERE product_id=?", (pid,))
    weights = [w[0] for w in cursor.fetchall()]
    return render_template('product.html', product={
        "id": p[0], "name": p[1],
        "short_desc": p[2], "long_desc": p[3],
        "price_per_100": p[4], "photos": photos, "weights": weights
    })

@app.route('/api/order', methods=['POST'])
def new_order():
    data = request.get_json()
    cursor.execute("INSERT INTO orders (product_id, weight, name, phone, comment) VALUES (?,?,?,?,?)",
                   (data['product_id'], data['weight'], data['name'], data['phone'], data.get('comment','')))
    conn.commit()
    return jsonify({'status':'ok'})

@app.route('/reviews')
def reviews_page():
    cursor.execute("SELECT * FROM reviews ORDER BY id DESC")
    reviews = cursor.fetchall()
    return render_template('reviews.html', reviews=reviews)

@app.route('/api/review', methods=['POST'])
def new_review():
    data = request.get_json()
    cursor.execute("INSERT INTO reviews (name, text) VALUES (?, ?)", (data['name'], data['text']))
    conn.commit()
    return jsonify({'status': 'ok'})

# === TELEGRAM БОТ ===
def check_session(chat_id):
    if chat_id in sessions:
        if time.time() - sessions[chat_id]['last_activity'] > TIMEOUT:
            del sessions[chat_id]
            return False
        sessions[chat_id]['last_activity'] = time.time()
        return True
    return False

def require_login(func):
    def wrapper(message):
        if not check_session(message.chat.id):
            msg = bot.send_message(message.chat.id, "Введите логин:")
            bot.register_next_step_handler(msg, login_step)
        else:
            func(message)
    return wrapper

def login_step(message):
    chat_id = message.chat.id
    login = message.text
    if login not in USERS:
        bot.send_message(chat_id, "Неверный логин, попробуй ещё раз.")
        return
    msg = bot.send_message(chat_id, "Введите пароль:")
    bot.register_next_step_handler(msg, lambda m: password_step(m, login))

def password_step(message, login):
    chat_id = message.chat.id
    if message.text != USERS[login]:
        bot.send_message(chat_id, "Неверный пароль.")
        return
    sessions[chat_id] = {'user': login, 'last_activity': time.time()}
    bot.send_message(chat_id, f"Привет, {login}! Можно работать с товарами и заказами.")

@bot.message_handler(commands=['start'])
def start(message):
    if not check_session(message.chat.id):
        msg = bot.send_message(message.chat.id, "Введите логин:")
        bot.register_next_step_handler(msg, login_step)
        return
    bot.send_message(message.chat.id, "Привет! Команды:\n/add — добавить товар\n/del — удалить товар\n/orders — список заказов")

# === ДОБАВЛЕНИЕ ТОВАРА ===
admin_add_state = {}

@bot.message_handler(commands=['add'])
@require_login
def add_product_start(message):
    bot.send_message(message.chat.id, "Введите название товара:")
    admin_add_state[message.chat.id] = {'step': 'name'}

@bot.message_handler(func=lambda m: m.chat.id in admin_add_state, content_types=['text', 'photo'])
def add_product_step(message):
    chat_id = message.chat.id
    state = admin_add_state[chat_id]

    # 1. Название
    if state['step'] == 'name':
        state['name'] = message.text
        state['step'] = 'short_desc'
        bot.send_message(chat_id, "Введите короткое описание (до 100 символов):")

    # 2. Короткое описание
    elif state['step'] == 'short_desc':
        if len(message.text) > 100:
            bot.send_message(chat_id, "Короткое описание слишком длинное, максимум 100 символов.")
            return
        state['short_desc'] = message.text
        state['step'] = 'long_desc'
        bot.send_message(chat_id, "Введите длинное описание (170–350 символов):")

    # 3. Длинное описание
    elif state['step'] == 'long_desc':
        if not (170 <= len(message.text) <= 350):
            bot.send_message(chat_id, "Описание должно быть от 170 до 350 символов.")
            return
        state['long_desc'] = message.text
        state['step'] = 'weight_count'
        bot.send_message(chat_id, "Сколько вариантов веса (1–10)?")

    # 4. Количество весов
    elif state['step'] == 'weight_count':
        try:
            count = int(message.text)
            if not 1 <= count <= 10:
                raise ValueError
            state['weight_count'] = count
            state['weights'] = []
            state['step'] = 'weights'
            bot.send_message(chat_id, "Введите вес №1 (в граммах):")
        except ValueError:
            bot.send_message(chat_id, "Введите число от 1 до 10.")

    # 5. Ввод весов
    elif state['step'] == 'weights':
        try:
            w = int(message.text)
            state['weights'].append(w)
            if len(state['weights']) < state['weight_count']:
                bot.send_message(chat_id, f"Введите вес №{len(state['weights']) + 1}:")
            else:
                state['step'] = 'price'
                bot.send_message(chat_id, "Введите цену за 100 грамм:")
        except ValueError:
            bot.send_message(chat_id, "Введите число в граммах.")

    # 6. Цена
    elif state['step'] == 'price':
        try:
            state['price_per_100'] = float(message.text)
            state['photos'] = []
            state['step'] = 'photos'
            bot.send_message(chat_id, "Отправьте 1–3 фото товара:")
        except ValueError:
            bot.send_message(chat_id, "Введите число (например 120.50).")

    # 7. Фото
    elif state['step'] == 'photos':
        # проверка на "готово"
        if message.content_type == 'text' and message.text.lower() == 'готово':
            if len(state['photos']) == 0:
                bot.send_message(chat_id, "Ты не добавил ни одной фотки, брат. Отправь хотя бы одну.")
                return

            # добавляем товар в базу
            cursor.execute("INSERT INTO products (name, short_desc, long_desc, price_per_100) VALUES (?,?,?,?)",
                           (state['name'], state['short_desc'], state['long_desc'], state['price_per_100']))
            pid = cursor.lastrowid
            for w in state['weights']:
                cursor.execute("INSERT INTO product_weights (product_id, weight) VALUES (?,?)", (pid, w))
            for ph in state['photos']:
                cursor.execute("INSERT INTO product_photos (product_id, filename) VALUES (?,?)", (pid, ph))
            conn.commit()

            bot.send_message(chat_id, f"✅ Товар '{state['name']}' успешно добавлен!")
            del admin_add_state[chat_id]
            return

        # если это не фото
        if message.content_type != 'photo':
            bot.send_message(chat_id, "Это не фото. Отправь фотографию или напиши 'готово'.")
            return

        # сохраняем фото
        file_id = message.photo[-1].file_id
        file_info = bot.get_file(file_id)
        downloaded = bot.download_file(file_info.file_path)
        os.makedirs('static/uploads', exist_ok=True)
        filename = f'static/uploads/{file_id}.jpg'
        with open(filename, 'wb') as f:
            f.write(downloaded)
        state['photos'].append(filename)

        if len(state['photos']) < 3:
            bot.send_message(chat_id, f"Фото добавлено! Можно ещё {3 - len(state['photos'])} фото или напиши 'готово'.")
        else:
            bot.send_message(chat_id, "Все фото добавлены. Напиши 'готово' для завершения.")



    #elif state['step'] == 'photos' and message.text.lower() == 'готово':
        cursor.execute("INSERT INTO products (name, short_desc, long_desc, price_per_100) VALUES (?,?,?,?)",
                       (state['name'], state['short_desc'], state['long_desc'], state['price_per_100']))
        pid = cursor.lastrowid
        for w in state['weights']:
            cursor.execute("INSERT INTO product_weights (product_id, weight) VALUES (?,?)", (pid, w))
        for ph in state['photos']:
            cursor.execute("INSERT INTO product_photos (product_id, filename) VALUES (?,?)", (pid, ph))
        conn.commit()
        bot.send_message(chat_id, f"✅ Товар '{state['name']}' успешно добавлен!")
        del admin_add_state[chat_id]

# === УДАЛЕНИЕ ТОВАРА ===
bot_del_state = {}

@bot.message_handler(commands=['del'])
@require_login
def del_start(message):
    bot.send_message(message.chat.id, "Введите ID товара для удаления:")
    bot_del_state[message.chat.id] = True

@bot.message_handler(func=lambda m: m.chat.id in bot_del_state)
def del_step(message):
    try:
        pid = int(message.text)
        cursor.execute("DELETE FROM products WHERE id=?", (pid,))
        conn.commit()
        bot.send_message(message.chat.id, f"🗑️ Товар {pid} удалён.")
        del bot_del_state[message.chat.id]
    except:
        bot.send_message(message.chat.id, "Ошибка: введите корректный ID.")

# === ЗАКАЗЫ ===
@bot.message_handler(commands=['orders'])
@require_login
def show_orders(message):
    cursor.execute("SELECT * FROM orders")
    orders = cursor.fetchall()
    if not orders:
        bot.send_message(message.chat.id, "Заказов нет.")
        return
    msg = ""
    for o in orders:
        cursor.execute("SELECT name FROM products WHERE id=?", (o[1],))
        prod_name = cursor.fetchone()[0]
        msg += f"📦 {prod_name}\n⚖️ {o[2]}г\n👤 {o[3]}\n📞 {o[4]}\n💬 {o[5] or '-'}\n———\n"
    bot.send_message(message.chat.id, msg)

# === ЗАПУСК ===
def run_bot():
    bot.infinity_polling()

if __name__ == '__main__':
    threading.Thread(target=run_bot).start()
    app.run(host='0.0.0.0', port=5000)
