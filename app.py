import os
import tempfile
from flask import Flask, render_template, request, session, jsonify, send_file
import requests
from collections import Counter, defaultdict
from io import BytesIO
from PIL import Image
from fpdf import FPDF
import base64

app = Flask(__name__)
app.secret_key = 'your_secret_key'

# Главная страница с формой для ввода API-ключа и supply_id
@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        api_key = request.form['api_key']
        supply_id = request.form['supply_id']
        
        # Сохраняем API-ключ в сессии
        session['api_key'] = api_key
        
        # Формируем URL для запроса
        url = f"https://marketplace-api.wildberries.ru/api/v3/supplies/{supply_id}/orders"
        
        # Заголовки для авторизации
        headers = {
            "Authorization": api_key
        }

        # Отправляем GET-запрос к API
        try:
            response = requests.get(url, headers=headers)
            
            # Если ответ успешный, парсим JSON
            if response.status_code == 200:
                orders_data = response.json()
                
                # Извлекаем список заказов из ключа "orders"
                if 'orders' in orders_data:
                    orders_list = orders_data['orders']
                    
                    # Считаем количество заказов для каждого артикула
                    article_counter = Counter(order['article'] for order in orders_list)
                    
                    # Сортируем артикулы по количеству заказов в порядке убывания
                    sorted_articles = sorted(article_counter.items(), key=lambda x: x[1], reverse=True)
                    
                    # Для каждого артикула добавляем его заказы
                    filtered_orders = []
                    order_ids = []  # Список для ID заказов
                    order_no = 1  # Порядковый номер заказа
                    for article, count in sorted_articles:
                        article_orders = [order for order in orders_list if order['article'] == article]
                        
                        # Добавляем заказы для каждого артикула с порядковыми номерами
                        for order in article_orders:
                            filtered_order = {
                                "no": order_no,  # Порядковый номер заказа
                                "article": order.get("article"),
                                "id": order.get("id"),
                                "skus": order.get("skus")
                            }
                            filtered_orders.append(filtered_order)
                            order_ids.append(order.get("id"))  # Добавляем ID в список
                            order_no += 1
                        
                        # Добавляем строку с количеством заказов для артикула
                        filtered_orders.append({
                            "no": "",  # Пустая ячейка для номера
                            "article": f"Количество заказов для артикула {article}: {count}",
                            "id": "",
                            "skus": ""
                        })
                    
                    # Сохраняем список всех ID заказов и данные в сессии
                    session['order_ids'] = order_ids
                    session['orders_data'] = filtered_orders
                    
                    # Передаем отсортированные данные в шаблон для отображения
                    return render_template('result.html', orders_data=filtered_orders)
                else:
                    error_message = "Ответ не содержит ключа 'orders'."
                    return render_template('result.html', error_message=error_message)
            else:
                # Обрабатываем ошибку
                error_message = f"Ошибка {response.status_code}: {response.text}"
                return render_template('result.html', error_message=error_message)
        except Exception as e:
            error_message = f"Произошла ошибка: {str(e)}"
            return render_template('result.html', error_message=error_message)

    return render_template('index.html')

# Страница для отображения сохраненных данных (таблицы) на другой странице
@app.route('/saved_orders')
def saved_orders():
    # Извлекаем заказы из сессии
    orders_data = session.get('orders_data')

    if not orders_data:
        return "Нет данных для отображения", 400

    # Проверяем, есть ли у нас данные с ID заказов и сохраняем их в сессии
    order_ids = [order['id'] for order in orders_data if order.get('id')]
    if order_ids:
        session['saved_order_ids'] = order_ids  # Сохраняем порядок order_ids в сессии
    else:
        session['saved_order_ids'] = []  # Если нет данных, сохраняем пустой список

    # Рендерим шаблон с сохраненными заказами
    return render_template('saved_orders.html', orders_data=orders_data)


@app.route('/get_all_stickers', methods=['POST'])
def get_all_stickers():
    try:
        api_key = session.get('api_key')  # Берём сохранённый API-ключ
        order_ids = session.get('order_ids')  # Берём сохранённые ID заказов
        saved_order_ids = session.get('saved_order_ids')  # Получаем порядок из saved_orders
        orders_data = session.get('orders_data')  # Данные из /saved_orders

        if not order_ids or not api_key:
            return jsonify({"error": "invalid_data", "message": "Не указаны заказы или API-ключ"}), 400

        if not saved_order_ids:
            return jsonify({"error": "invalid_data", "message": "Порядок заказов отсутствует"}), 400

        # URL для запроса
        url = "https://marketplace-api.wildberries.ru/api/v3/orders/stickers"

        # Заголовки запроса
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        # Параметры запроса
        params = {
            "type": "png",
            "width": 58,
            "height": 40
        }

        # Тело запроса (ID сборочных заданий)
        data = {
            "orders": order_ids  # Используем все ID заказов
        }

        # Выполняем POST-запрос
        response = requests.post(url, headers=headers, params=params, json=data)

        # Обработка ответа
        if response.status_code == 200:
            stickers_data = response.json()

            # Сортируем стикеры в соответствии с saved_order_ids
            sorted_stickers = sorted(stickers_data['stickers'], key=lambda x: saved_order_ids.index(x['orderId']))

            # Добавляем артикулы из orders_data для каждого стикера
            for sticker in sorted_stickers:
                for order in orders_data:
                    if sticker['orderId'] == order['id']:
                        sticker['article'] = order['article']
                        break

            # Группируем стикеры по артикулам
            grouped_stickers = defaultdict(list)
            for sticker in sorted_stickers:
                grouped_stickers[sticker['article']].append(sticker)

            # Создаем временные файлы для каждого изображения и сохраняем пути к ним
            stickers_paths = []
            for article, stickers in grouped_stickers.items():
                for sticker in stickers:
                    # Декодируем изображение из base64
                    image_data = BytesIO(base64.b64decode(sticker['file']))
                    image = Image.open(image_data)

                    # Сохраняем изображение во временный файл
                    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.png')
                    image.save(temp_file.name)
                    stickers_paths.append(temp_file.name)

            # Сохраняем пути к изображениям в сессии
            session['stickers_paths'] = stickers_paths

            # Передаем сгруппированные стикеры в шаблон
            return render_template('stickers_result.html', grouped_stickers=grouped_stickers)
        else:
            return jsonify({"error": response.status_code, "message": response.text}), response.status_code
    except Exception as e:
        return jsonify({"error": "exception", "message": str(e)}), 500

@app.route('/download_stickers_pdf', methods=['POST'])
def download_stickers_pdf():
    try:
        stickers_paths = session.get('stickers_paths')  # Получаем пути к стикерам из сессии
        orders_data = session.get('orders_data')  # Получаем данные о заказах из сессии

        if not stickers_paths or not orders_data:
            return jsonify({"error": "no_stickers", "message": "Нет стикеров для генерации PDF"}), 400

        # Создаем словарь {order_id: article} для быстрого доступа к артикулам по ID заказа
        order_to_article = {order['id']: order['article'] for order in orders_data if order.get('id') and order.get('article')}

        # Создаем PDF-файл с помощью FPDF
        pdf = FPDF(orientation='P', unit='mm', format=[58, 40])  # Устанавливаем формат 58x40 мм

        # Регистрация шрифта DejaVuSans, поддерживающего кириллицу
        pdf.add_font('DejaVu', '', 'DejaVuSansCondensed.ttf', uni=True)
        pdf.set_font('DejaVu', '', 10)  # Размер шрифта уменьшен до 10

        last_article = None  # Переменная для отслеживания последнего артикула
        for sticker_path, order_id in zip(stickers_paths, session.get('saved_order_ids', [])):
            # Получаем артикул для текущего order_id
            article = order_to_article.get(order_id, "Артикул не найден")

            # Если артикул отличается от предыдущего, выводим его в PDF
            if article != last_article:
                pdf.add_page()
                # Рисуем текст по центру страницы с уменьшенным размером шрифта
                pdf.set_xy(0, 15)  # Центрируем текст по вертикали и горизонтали
                pdf.cell(58, 10, f'Артикул: {article}', 0, 1, 'C')
                last_article = article  # Обновляем последний артикул

            # Добавляем страницу с изображением стикера
            pdf.add_page()
            pdf.image(sticker_path, x=0, y=0, w=58, h=40)

        # Сохраняем PDF во временный файл
        temp_pdf = tempfile.NamedTemporaryFile(delete=False, suffix='.pdf')
        pdf.output(temp_pdf.name)
        
        # Отправляем PDF файл пользователю
        return send_file(temp_pdf.name, as_attachment=True, download_name='stickers.pdf', mimetype='application/pdf')

    except Exception as e:
        return jsonify({"error": "exception", "message": str(e)}), 500


if __name__ == '__main__':
    app.run(debug=True)
